"""Tests that this project never breaks a rate limit.

Rules for every request, enforced per host:

1. Project floor: at least 1 second between requests (MIN_SECONDS_BETWEEN_REQUESTS).
2. Every limit the operator publishes, plus a 1 second safety margin (LIMIT_MARGIN_SECONDS).
3. Never contact a server sooner than a Retry-After it sent.

The Public Charge Point Regulations 2023 set no limit for data users (see the transparency
page), so these cover every limit that applies.

The simulations use a fake clock that only moves when the client waits or when a request
is "on the wire". Gaps are checked at the server's end, using the time each request
arrives, with uneven network delays, and windows are counted inclusively at both ends.
"""

import time
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from itertools import cycle, pairwise
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from adapters.http import FeedError, PoliteClient, required_gap
from adapters.ocpi_221.client import fetch_module
from adapters.replay import ReplayTransport
from pipeline import run
from pipeline.registry import load_registry
from schema.operator import (
    LIMIT_MARGIN_SECONDS,
    MIN_SECONDS_BETWEEN_REQUESTS,
    Auth,
    OperatorConfig,
    RateLimit,
)

EXAMPLE = "https://example.invalid/ocpi"
OPERATORS = load_registry()
WALL_START = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
CHARGY_FIXTURES = Path(__file__).parent / "fixtures" / "chargy"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        assert seconds >= 0
        self.now += seconds

    def wall(self) -> datetime:
        return WALL_START + timedelta(seconds=self.now)


def make_config(gap: float, limits: list[dict] | None = None) -> OperatorConfig:
    return OperatorConfig.model_validate(
        {
            "id": "example_operator",
            "display_name": "Example Operator",
            "ocpi_country_code": "GB",
            "ocpi_party_id": "EXA",
            "adapter": "ocpi_221",
            "base_url": EXAMPLE,
            "auth": {"method": "none"},
            "rate_limit": {"min_seconds_between_requests": gap, "limits": limits or []},
            "supports_single_location": "unknown",
            "cors": "unknown",
            "engagement": {"status": "unknown"},
            "enabled": False,
        }
    )


def limit(requests: int, per_seconds: float, endpoint: str = "all") -> dict:
    return {
        "requests": requests,
        "per_seconds": per_seconds,
        "endpoint": endpoint,
        "quote": "test limit",
        "source_url": "https://example.invalid/terms",
        "checked": "2026-10-07",
    }


def without_keys(config: OperatorConfig) -> OperatorConfig:
    """The same operator with no key, so the client can start; keys do not affect timing."""
    return config.model_copy(update={"auth": Auth(method="none")})


def assert_within_limits(config: OperatorConfig, arrivals: list[float]) -> None:
    """Check request arrival times at the server against the gap and every limit."""
    gap = config.rate_limit.min_seconds_between_requests
    for earlier, later in pairwise(arrivals):
        assert later - earlier >= gap - 1e-9, f"requests arrived {later - earlier:g} s apart"
    for documented in config.rate_limit.limits:
        for start in arrivals:
            window = [t for t in arrivals if start <= t <= start + documented.per_seconds]
            assert len(window) <= documented.requests, (
                f"{len(window)} requests in {documented.per_seconds:g} s, "
                f"limit {documented.requests}"
            )


class Server:
    """A fake server: each request spends time on the wire, and arrival times are kept."""

    def __init__(self, clock: FakeClock, responses, delays=(0.0,)):
        self.clock = clock
        self.responses = list(responses)
        self.delays = cycle(delays)
        self.arrivals: list[float] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.clock.sleep(next(self.delays))  # on the way to the server
        self.arrivals.append(self.clock())
        response = self.responses.pop(0)
        self.clock.sleep(next(self.delays))  # on the way back
        return response


def client_for(config, clock, server, **kwargs) -> PoliteClient:
    return PoliteClient(
        without_keys(config),
        transport=httpx.MockTransport(server),
        sleep=clock.sleep,
        clock=clock,
        wall_clock=clock.wall,
        **kwargs,
    )


def simulate(config, responses, delays=(0.0,), url=f"{EXAMPLE}/locations") -> list[float]:
    """Keep requesting until the responses run out; return arrival times at the server."""
    clock = FakeClock()
    server = Server(clock, responses, delays)
    with client_for(config, clock, server) as client:
        while server.responses:
            sent_before = len(server.arrivals)
            try:
                client.get(url)
            except FeedError:
                if len(server.arrivals) == sent_before:
                    clock.sleep(60)  # held back by a long Retry-After; let time pass
    return server.arrivals


def busy_responses() -> list[httpx.Response]:
    """Successes mixed with retryable failures and Retry-After values of several kinds."""
    pattern = [
        httpx.Response(200, json={}),
        httpx.Response(503),
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json={}),
        httpx.Response(500),
        httpx.Response(429, headers={"Retry-After": "45"}),
        httpx.Response(200, json={}),
    ]
    return pattern * 10


UNEVEN_DELAYS = (1.5, 0.05, 0.4, 0.0, 0.9, 0.01)


# The registry


def test_project_floor_and_margin_are_pinned():
    assert MIN_SECONDS_BETWEEN_REQUESTS == 1.0
    assert LIMIT_MARGIN_SECONDS == 1.0


def test_every_operator_keeps_the_floor_and_the_margin():
    for config in OPERATORS.values():
        gap = config.rate_limit.min_seconds_between_requests
        assert gap >= 1.0, config.id
        for documented in config.rate_limit.limits:
            assert gap >= documented.per_seconds / documented.requests + 1.0, config.id


@pytest.mark.parametrize(
    ("gap", "limits", "valid"),
    [
        (0.999, [], False),
        (1.0, [], True),
        (120.99, [limit(30, 3600)], False),
        (121, [limit(30, 3600)], True),
        (30.99, [limit(1, 30)], False),
        (31, [limit(1, 30)], True),
    ],
    ids=["below-floor", "at-floor", "hourly-short", "hourly-ok", "per-30s-short", "per-30s-ok"],
)
def test_validator_boundaries(gap, limits, valid):
    data = {"min_seconds_between_requests": gap, "limits": limits}
    if valid:
        RateLimit.model_validate(data)
    else:
        with pytest.raises(ValidationError):
            RateLimit.model_validate(data)


def test_client_does_not_trust_a_gap_that_skipped_validation():
    unchecked = RateLimit.model_construct(
        min_seconds_between_requests=0.1,
        limits=make_config(121, [limit(30, 3600)]).rate_limit.limits,
        limits_checked="unknown",
        notes=None,
    )
    config = make_config(2).model_copy(update={"rate_limit": unchecked})
    assert required_gap(config) == 121
    clock = FakeClock()
    server = Server(clock, [httpx.Response(200, json={})] * 40, UNEVEN_DELAYS)
    with client_for(config, clock, server) as client:
        assert client.min_interval == 121
        for _ in range(40):
            client.get(f"{EXAMPLE}/locations")
    assert_within_limits(make_config(121, [limit(30, 3600)]), server.arrivals)


# The client, simulated for every operator in the registry


@pytest.mark.parametrize("operator_id", sorted(OPERATORS))
def test_client_never_breaks_an_operators_limits(operator_id):
    config = OPERATORS[operator_id]
    arrivals = simulate(config, busy_responses(), UNEVEN_DELAYS)
    assert len(arrivals) == len(busy_responses())
    assert_within_limits(config, arrivals)


def test_operators_on_one_host_share_one_gap():
    """bp pulse, Shell Recharge, ubitricity and Community by Shell Recharge share a host."""
    shared = [c for c in OPERATORS.values() if c.adapter == "eco_movement_pcpr"]
    assert len(shared) == 4
    clock = FakeClock()
    server = Server(clock, [httpx.Response(200, json={})] * 40, UNEVEN_DELAYS)
    for config in shared:
        with client_for(config, clock, server) as client:
            for _ in range(10):
                client.get(config.endpoints["tariffs"].url)
    for config in shared:
        assert_within_limits(config, server.arrivals)


def test_a_strict_hourly_limit_holds_at_the_boundary_with_network_delays():
    config = make_config(121, [limit(30, 3600, "tariffs"), limit(1, 30, "statuses")])
    arrivals = simulate(config, busy_responses(), UNEVEN_DELAYS)
    assert_within_limits(config, arrivals)


def test_paging_through_a_whole_feed_stays_within_limits():
    config = make_config(121, [limit(30, 3600)])
    clock, arrivals, delays = FakeClock(), [], cycle(UNEVEN_DELAYS)
    pages = 75

    def handler(request: httpx.Request) -> httpx.Response:
        clock.sleep(next(delays))
        arrivals.append(clock())
        offset = int(request.url.params.get("offset", 0))
        headers = {"X-Total-Count": str(pages)}
        if offset + 1 < pages:
            headers["Link"] = f'<{EXAMPLE}/tariffs?offset={offset + 1}>; rel="next"'
        clock.sleep(next(delays))
        return httpx.Response(200, headers=headers, json={"status_code": 1000, "data": [{}]})

    with PoliteClient(
        config, transport=httpx.MockTransport(handler), sleep=clock.sleep, clock=clock
    ) as client:
        result = fetch_module(client, "tariffs", f"{EXAMPLE}/tariffs")
    assert result.complete and len(result.records) == pages
    assert_within_limits(config, arrivals)


# Retry-After


def test_a_retry_after_within_our_wait_is_honoured():
    arrivals = simulate(
        make_config(2),
        [httpx.Response(503, headers={"Retry-After": "90"}), httpx.Response(200, json={})],
    )
    assert arrivals[1] - arrivals[0] >= 90


def test_a_retry_after_on_the_final_attempt_is_honoured():
    config = make_config(2)
    clock = FakeClock()
    responses = [httpx.Response(503)] * 3 + [
        httpx.Response(429, headers={"Retry-After": "300"}),
        httpx.Response(200, json={}),
    ]
    server = Server(clock, responses)
    with client_for(config, clock, server) as client:
        with pytest.raises(FeedError, match="the server asked to wait 300 s"):
            client.get(f"{EXAMPLE}/locations")
        client.get(f"{EXAMPLE}/tariffs")
    assert server.arrivals[4] - server.arrivals[3] >= 300


def test_a_retry_after_given_as_a_date_is_honoured():
    config = make_config(2)
    clock = FakeClock()
    when = format_datetime(WALL_START + timedelta(seconds=240), usegmt=True)
    responses = [httpx.Response(503, headers={"Retry-After": when}), httpx.Response(200)]
    server = Server(clock, responses)
    with client_for(config, clock, server) as client:
        client.get(f"{EXAMPLE}/locations")
    assert server.arrivals[1] - server.arrivals[0] >= 240


@pytest.mark.parametrize("value", ["soon", "120.0", b"\xb2", "9" * 400])
def test_an_unreadable_or_huge_retry_after_is_treated_as_a_long_wait(value):
    config = make_config(2)
    clock = FakeClock()
    responses = [httpx.Response(429, headers={"Retry-After": value}), httpx.Response(200)]
    server = Server(clock, responses)
    with client_for(config, clock, server) as client, pytest.raises(FeedError):
        client.get(f"{EXAMPLE}/locations")
    assert len(server.arrivals) == 1  # nothing more is sent


def test_a_long_retry_after_holds_back_every_client_for_that_host():
    config = make_config(2)
    clock = FakeClock()
    server = Server(
        clock, [httpx.Response(429, headers={"Retry-After": "3600"}), httpx.Response(200)]
    )
    with (
        client_for(config, clock, server) as first,
        pytest.raises(FeedError, match="asked this project to wait"),
    ):
        first.get(f"{EXAMPLE}/locations")
    clock.sleep(1800)
    with client_for(config, clock, server) as second:
        with pytest.raises(FeedError, match="asked this project to wait"):
            second.get(f"{EXAMPLE}/tariffs")  # nothing is sent during the wait
        assert len(server.arrivals) == 1
        clock.sleep(1800)
        assert second.get(f"{EXAMPLE}/tariffs").status_code == 200
    assert server.arrivals[1] - server.arrivals[0] >= 3600


# The runner used by --live


class TimedReplay(ReplayTransport):
    def __init__(self, directory: Path, clock: FakeClock):
        super().__init__(directory)
        self.clock = clock
        self.arrivals: list[float] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.arrivals.append(self.clock())
        return super().handle_request(request)


def test_the_live_runner_spaces_requests_across_modules():
    config = OPERATORS["chargy"]
    clock = FakeClock()
    transport = TimedReplay(CHARGY_FIXTURES, clock)
    result = run.run_operator(
        config, transport=transport, sleep=clock.sleep, clock=clock, page_size=2, max_pages=2
    )
    assert result.requests == 4
    assert_within_limits(config, transport.arrivals)


def test_live_mode_uses_the_real_clock(monkeypatch):
    captured = {}

    class Capture:
        def __init__(self, config, **kwargs):
            captured.update(kwargs)
            raise run.FeedError("stopped by the test")

    monkeypatch.setattr(run, "PoliteClient", Capture)
    assert run.main(["--live", "chargy"]) == 1
    assert captured["sleep"] is time.sleep
    assert captured["clock"] is time.monotonic
