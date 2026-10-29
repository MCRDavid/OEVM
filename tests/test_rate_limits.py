"""Tests that this project never breaks a rate limit.

Rules for every request, enforced per host:

1. Project floor: at least 1 second between requests (MIN_SECONDS_BETWEEN_REQUESTS).
2. Every limit the operator publishes, plus a 1 second safety margin (LIMIT_MARGIN_SECONDS),
   or, where the owner reads the limits as an allowance for each key, one request in hand
   in each limit's period plus that margin, at most at_once requests at once at the host.
3. Never contact a server sooner than a Retry-After it sent.

The Public Charge Point Regulations 2023 set no limit for data users (see the transparency
page), so these cover every limit that applies.

The simulations use a fake clock that only moves when the client waits or when a request
is "on the wire". Gaps are checked at the server's end, using the time each request
arrives, with uneven network delays, and windows are counted inclusively at both ends.
"""

import threading
import time
from datetime import UTC, datetime, timedelta
from email.utils import format_datetime
from itertools import combinations, cycle, pairwise
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from adapters import http
from adapters.http import (
    SHARED_HOST_SECONDS,
    FeedError,
    PoliteClient,
    operator_hosts,
    required_gap,
)
from adapters.ocpi_221.client import fetch_module
from adapters.replay import ReplayTransport
from pipeline import registry, run
from pipeline.registry import load_registry
from schema.operator import (
    LIMIT_MARGIN_SECONDS,
    MIN_SECONDS_BETWEEN_REQUESTS,
    Auth,
    LimitsAsAllowance,
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
        "publisher": "Example Operator",
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


def reads_an_allowance(config: OperatorConfig) -> bool:
    return config.limits_per_key is not None and config.limits_as_allowance is not None


def assert_within_limits(
    config: OperatorConfig, arrivals: list[float], endpoint: str | None = None
) -> None:
    """Check request arrival times at the server against the gap and every limit.

    Limits read as an allowance (limits_as_allowance) keep SHARED_HOST_SECONDS between one
    key's requests rather than the gap; with endpoint given, every request was to that
    endpoint, so only the limits that name it, or all endpoints, are checked."""
    gap = config.rate_limit.min_seconds_between_requests
    if reads_an_allowance(config):
        gap = SHARED_HOST_SECONDS
    for earlier, later in pairwise(arrivals):
        assert later - earlier >= gap - 1e-9, f"requests arrived {later - earlier:g} s apart"
    for documented in config.rate_limit.limits:
        if endpoint is not None and documented.endpoint not in ("all", endpoint):
            continue
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
    """Without the owner's limits_per_key decision, operators on one host share its gap."""
    shared = [
        c.model_copy(update={"limits_per_key": None})
        for c in OPERATORS.values()
        if c.adapter == "eco_movement_pcpr"
    ]
    assert len(shared) == 24
    clock = FakeClock()
    server = Server(clock, [httpx.Response(200, json={})] * 10 * len(shared), UNEVEN_DELAYS)
    for config in shared:
        with keyed_client_for(config, clock, server) as client:
            for _ in range(10):
                client.get(config.endpoints["tariffs"].url)
    for config in shared:
        assert_within_limits(config, server.arrivals)


class KeyServer(Server):
    """A fake server that also keeps which key each request used."""

    def __init__(self, clock: FakeClock, responses, delays=(0.0,)):
        super().__init__(clock, responses, delays)
        self.keys: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.keys.append(request.headers.get("authorization", ""))
        return super().__call__(request)

    def arrivals_for(self, key: str) -> list[float]:
        return [t for t, k in zip(self.arrivals, self.keys, strict=True) if k == f"Token {key}"]


def keyed_client_for(config, clock, server) -> PoliteClient:
    """A client with a made-up key named after the operator, so the key shapes the timing."""
    return PoliteClient(
        config,
        transport=httpx.MockTransport(server),
        sleep=clock.sleep,
        clock=clock,
        wall_clock=clock.wall,
        key=f"made-up-{config.id}",
    )


ECO = [c for c in OPERATORS.values() if c.adapter == "eco_movement_pcpr"]
# The same networks with their limits read per key but kept as a spacing, as before the
# owner's allowance decision, and as every key falls back to after any sign of trouble.
PER_KEY = [c.model_copy(update={"limits_as_allowance": None}) for c in ECO]


def test_every_eco_movement_network_reads_its_limits_per_token_by_the_owners_decision():
    assert {str(c.limits_per_key.decided) for c in ECO if c.limits_per_key} == {"2026-10-29"}
    assert all(c.limits_per_key is not None for c in ECO)


def test_per_key_limits_keep_each_tokens_gap_and_the_host_one_request_at_a_time():
    clock = FakeClock()
    server = KeyServer(clock, [httpx.Response(200, json={})] * 5 * len(PER_KEY), UNEVEN_DELAYS)
    for config in PER_KEY:
        with keyed_client_for(config, clock, server) as client:
            for _ in range(5):
                client.get(config.endpoints["tariffs"].url)
    for config in PER_KEY:
        own = server.arrivals_for(f"made-up-{config.id}")
        assert len(own) == 5
        assert_within_limits(config, own)
    for earlier, later in pairwise(server.arrivals):
        assert later - earlier >= SHARED_HOST_SECONDS - 1e-9
    # Each network waits only for its own gap: 4 gaps each, one network after another.
    assert server.arrivals[-1] < len(PER_KEY) * 4 * 125 + len(PER_KEY) * 10


def test_per_key_clients_used_in_turn_still_keep_the_host_floor_and_each_gap():
    first, second = PER_KEY[0], PER_KEY[1]
    clock = FakeClock()
    server = KeyServer(clock, [httpx.Response(200, json={})] * 6)
    with keyed_client_for(first, clock, server) as a, keyed_client_for(second, clock, server) as b:
        for _ in range(3):
            a.get(first.endpoints["locations"].url)
            b.get(second.endpoints["locations"].url)
    assert server.arrivals[1] - server.arrivals[0] == pytest.approx(SHARED_HOST_SECONDS)
    for config in (first, second):
        assert_within_limits(config, server.arrivals_for(f"made-up-{config.id}"))


def test_a_wait_the_server_asks_of_one_key_holds_back_every_key_on_the_host():
    first, second = ECO[0], ECO[1]
    clock = FakeClock()
    server = KeyServer(clock, [httpx.Response(429, headers={"Retry-After": "3600"})])
    with keyed_client_for(first, clock, server) as a, keyed_client_for(second, clock, server) as b:
        with pytest.raises(FeedError, match="asked this project to wait"):
            a.get(first.endpoints["locations"].url)
        with pytest.raises(FeedError, match="asked this project to wait"):
            b.get(second.endpoints["locations"].url)
    assert len(server.arrivals) == 1


def test_keys_fetched_together_take_turns_at_the_host(monkeypatch):
    """Real threads, one per key, as pipeline.run fetches per-key operators together.

    Gaps are scaled down so the test is quick: requests never overlap, each starts at least
    the host floor after the last one finished, each key keeps its own gap, and the keys
    interleave rather than waiting for one another to finish."""
    monkeypatch.setattr(http, "SHARED_HOST_SECONDS", 0.02)
    gap, keys, per_key = 0.3, PER_KEY[:4], 3
    lock, seen = threading.Lock(), []

    def answer(request: httpx.Request) -> httpx.Response:
        start = time.monotonic()
        time.sleep(0.005)
        with lock:
            seen.append((start, time.monotonic(), request.headers["authorization"]))
        return httpx.Response(200, json={})

    def fetch(config):
        with PoliteClient(
            config, transport=httpx.MockTransport(answer), key=f"made-up-{config.id}"
        ) as client:
            client.min_interval = gap
            for _ in range(per_key):
                client.get(config.endpoints["locations"].url)

    began = time.monotonic()
    threads = [threading.Thread(target=fetch, args=(config,)) for config in keys]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    took = time.monotonic() - began
    seen.sort()
    assert len(seen) == len(keys) * per_key
    for (_, finished, _), (started, _, _) in pairwise(seen):
        assert started >= finished + 0.02 - 1e-3
    for config in keys:
        own = [(s, f) for s, f, k in seen if k == f"Token made-up-{config.id}"]
        assert len(own) == per_key
        for (_, finished), (started, _) in pairwise(own):
            assert started >= finished + gap - 1e-3
    # One key after another would take at least len(keys) * (per_key - 1) gaps.
    assert took < len(keys) * (per_key - 1) * gap


def test_only_groups_whose_every_operator_reads_limits_per_key_take_turns():
    eco = [c for c in ECO if c.enabled]
    assert run.takes_turns(eco)
    assert not run.takes_turns(eco[:1])
    mixed = [eco[0].model_copy(update={"limits_per_key": None}), *eco[1:]]
    assert not run.takes_turns(mixed)
    groups = run.host_groups([c for c in OPERATORS.values() if c.enabled])
    assert [sorted(c.id for c in g) for g in groups if run.takes_turns(g)] == [
        sorted(c.id for c in eco)
    ]


def test_per_key_limits_need_a_key_and_every_operator_on_the_host_to_agree():
    config = OPERATORS["ubitricity"]
    with pytest.raises(ValidationError, match="limits_per_key needs a key"):
        OperatorConfig.model_validate(config.model_dump(mode="json") | {"auth": {"method": "none"}})
    operators = load_registry()
    operators["pod"] = operators["pod"].model_copy(update={"limits_per_key": None})
    assert registry._per_key_problems(load_registry()) == []
    assert registry._per_key_problems(operators) == [
        "operators on open-chargepoints.com must all record limits_per_key, or none of them"
    ]


def test_every_eco_movement_network_reads_its_limits_as_an_allowance_by_the_owners_decision():
    assert all(c.limits_as_allowance is not None for c in ECO)
    assert {(str(c.limits_as_allowance.decided), c.limits_as_allowance.at_once) for c in ECO} == {
        ("2026-10-29", 5)
    }


def test_an_allowance_lets_a_key_send_its_pages_close_together_but_no_more_than_it_allows():
    config = OPERATORS["ubitricity"]
    clock = FakeClock()
    server = KeyServer(clock, [httpx.Response(200, json={})] * 40, UNEVEN_DELAYS)
    with keyed_client_for(config, clock, server) as client:
        for _ in range(40):
            client.get(config.endpoints["locations"].url)
    arrivals = server.arrivals
    assert_within_limits(config, arrivals, "locations")
    # 29 of the 30 an hour come close together; the 30th waits for the hour to pass.
    assert arrivals[28] < 29 * 5
    assert arrivals[29] - arrivals[0] > 3600


def test_an_allowance_is_counted_for_each_endpoint_its_limit_names():
    config = OPERATORS["ubitricity"]
    clock = FakeClock()
    server = KeyServer(clock, [httpx.Response(200, json={})] * 32)
    with keyed_client_for(config, clock, server) as client:
        for _ in range(29):
            client.get(config.endpoints["locations"].url)
        client.get(config.endpoints["tariffs"].url)
        client.get(config.endpoints["statuses"].url)
        # A request to none of the operator file's endpoints counts towards every limit.
        client.get("https://open-chargepoints.com/api/other")
    arrivals = server.arrivals
    assert arrivals[29] - arrivals[28] == pytest.approx(SHARED_HOST_SECONDS)
    assert arrivals[30] - arrivals[29] == pytest.approx(SHARED_HOST_SECONDS)
    assert arrivals[31] - arrivals[0] > 3600


def test_a_key_reading_its_limits_as_an_allowance_keeps_them_through_errors_and_waits():
    config = OPERATORS["ubitricity"]
    clock = FakeClock()
    server = KeyServer(clock, busy_responses(), UNEVEN_DELAYS)
    with keyed_client_for(config, clock, server) as client:
        while server.responses:
            sent_before = len(server.arrivals)
            try:
                client.get(config.endpoints["locations"].url)
            except FeedError:
                if len(server.arrivals) == sent_before:
                    clock.sleep(60)
    assert len(server.arrivals) == len(busy_responses())
    assert_within_limits(config, server.arrivals, "locations")


def test_any_sign_of_trouble_puts_every_key_back_to_its_gap_for_the_rest_of_the_run():
    first, second = ECO[0], ECO[1]
    clock = FakeClock()
    ok = httpx.Response(200, json={})
    server = KeyServer(clock, [ok, httpx.Response(503), ok, ok, ok, ok])
    with keyed_client_for(first, clock, server) as a, keyed_client_for(second, clock, server) as b:
        a.get(first.endpoints["locations"].url)
        a.get(first.endpoints["locations"].url)  # HTTP 503, then a retry
        b.get(second.endpoints["locations"].url)
        b.get(second.endpoints["locations"].url)
        a.get(first.endpoints["locations"].url)
    own_a = server.arrivals_for(f"made-up-{first.id}")
    own_b = server.arrivals_for(f"made-up-{second.id}")
    assert own_a[1] - own_a[0] == pytest.approx(SHARED_HOST_SECONDS)
    assert own_a[2] - own_a[1] >= 125 - 1e-9
    assert own_a[3] - own_a[2] >= 125 - 1e-9
    assert own_b[1] - own_b[0] >= 125 - 1e-9
    for earlier, later in pairwise(server.arrivals):
        assert later - earlier >= SHARED_HOST_SECONDS - 1e-9


def test_keys_fetched_together_within_their_allowance_send_at_most_five_at_once(monkeypatch):
    """Real threads, one per key, as pipeline.run fetches them. Floors are scaled down so
    the test is quick: requests overlap, never more than five at once, their starts at
    least the floor apart, and each key's next request waits for its last one to finish."""
    monkeypatch.setattr(http, "SHARED_HOST_SECONDS", 0.02)
    monkeypatch.setattr(http, "MIN_SECONDS_BETWEEN_REQUESTS", 0.005)
    keys, per_key, answer_seconds = ECO[:8], 3, 0.1
    lock, seen, busy, most = threading.Lock(), [], [0], [0]

    def answer(request: httpx.Request) -> httpx.Response:
        start = time.monotonic()
        with lock:
            busy[0] += 1
            most[0] = max(most[0], busy[0])
        time.sleep(answer_seconds)
        with lock:
            busy[0] -= 1
            seen.append((start, time.monotonic(), request.headers["authorization"]))
        return httpx.Response(200, json={})

    def fetch(config):
        with PoliteClient(
            config, transport=httpx.MockTransport(answer), key=f"made-up-{config.id}"
        ) as client:
            for _ in range(per_key):
                client.get(config.endpoints["locations"].url)

    began = time.monotonic()
    threads = [threading.Thread(target=fetch, args=(config,)) for config in keys]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join()
    took = time.monotonic() - began
    assert len(seen) == len(keys) * per_key
    assert 1 < most[0] <= 5
    starts = sorted(start for start, _, _ in seen)
    for earlier, later in pairwise(starts):
        assert later - earlier >= 0.005 - 1e-3
    for config in keys:
        own = sorted((s, f) for s, f, k in seen if k == f"Token made-up-{config.id}")
        assert len(own) == per_key
        for (_, finished), (started, _) in pairwise(own):
            assert started >= finished + 0.02 - 1e-3
    # One request at a time would take at least every answer's time, one after another.
    assert took < len(keys) * per_key * answer_seconds


def test_an_allowance_needs_limits_per_key_and_every_operator_on_the_host_to_agree():
    config = OPERATORS["ubitricity"]
    with pytest.raises(ValidationError, match="limits_as_allowance needs limits_per_key"):
        OperatorConfig.model_validate(config.model_dump(mode="json") | {"limits_per_key": None})
    with pytest.raises(ValidationError, match="less than or equal to 5"):
        LimitsAsAllowance.model_validate(
            config.limits_as_allowance.model_dump(mode="json") | {"at_once": 6}
        )
    operators = load_registry()
    assert registry._per_key_problems(operators) == []
    problem = (
        "operators on open-chargepoints.com must all record limits_as_allowance with the "
        "same at_once, or none of them"
    )
    operators["pod"] = operators["pod"].model_copy(update={"limits_as_allowance": None})
    assert registry._per_key_problems(operators) == [problem]
    four = config.limits_as_allowance.model_copy(update={"at_once": 4})
    operators["pod"] = operators["pod"].model_copy(update={"limits_as_allowance": four})
    assert registry._per_key_problems(operators) == [problem]


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


# Fetching operators on different hosts at the same time (pipeline.run.host_groups)


def test_operators_that_share_a_host_are_in_one_group():
    groups = run.host_groups([OPERATORS[i] for i in sorted(OPERATORS)])
    ids = [[config.id for config in group] for group in groups]
    shared = sorted(i for i, c in OPERATORS.items() if c.adapter == "eco_movement_pcpr")
    assert shared in ids
    assert ["chargy"] in ids and ["jolt"] in ids
    # Every host is in exactly one group.
    hosts = [set().union(*(operator_hosts(c) for c in group)) for group in groups]
    assert all(not (a & b) for a, b in combinations(hosts, 2))


def test_relayed_operators_share_the_relay_and_are_grouped():
    relay = OPERATORS["geniepoint"].relay
    one = make_config(2, []).model_copy(update={"id": "one", "relay": relay})
    other = OPERATORS["chargy"].model_copy(update={"relay": relay})
    groups = run.host_groups([one, OPERATORS["jolt"], other])
    assert [[c.id for c in group] for group in groups] == [["one", "chargy"], ["jolt"]]


def test_a_host_shared_through_a_third_operator_joins_the_groups():
    def on(operator_id, *hosts):
        data = make_config(2, []).model_dump()
        data.update(id=operator_id, base_url="unknown")
        data["endpoints"] = {
            module: {"url": f"https://{host}/ocpi", "status": "documented"}
            for module, host in zip(("locations", "tariffs"), hosts, strict=False)
        }
        return OperatorConfig.model_validate(data)

    a, b, c = on("a", "one.example"), on("b", "two.example"), on("c", "two.example", "one.example")
    assert [[x.id for x in g] for g in run.host_groups([a, b, c])] == [["a", "b", "c"]]
    assert len(run.host_groups([a, b])) == 2


def test_the_live_run_never_fetches_one_host_twice_at_once(monkeypatch, capsys):
    """Every operator in the registry switched on, with each fetch taking a little while.

    Operators whose limits the owner reads per key are the one exception: they are
    fetched together, and their client sends the host one request at a time (tested
    below with real threads)."""
    everyone = {i: c.model_copy(update={"enabled": True}) for i, c in OPERATORS.items()}
    monkeypatch.setattr(run, "load_registry", lambda: everyone)
    lock, busy, most, together = threading.Lock(), set(), [0], [0, 0]
    replayed = {r.operator_id: r for r in run.run_fixtures(OPERATORS)}

    def fake(config, **kwargs):
        hosts = operator_hosts(config)
        per_key = config.limits_per_key is not None
        with lock:
            if per_key:
                together[0] += 1
                together[1] = max(together[1], together[0])
            else:
                assert not busy & hosts, f"{config.id} started while its host was in use"
                busy.update(hosts)
            most[0] = max(most[0], len(busy))
        time.sleep(0.02)
        with lock:
            if per_key:
                together[0] -= 1
            else:
                busy.difference_update(hosts)
        if config.id in replayed:
            return replayed[config.id]
        raise FeedError(f"{config.id}: not recorded")

    monkeypatch.setattr(run, "run_operator", fake)
    assert run.main(["--live", "all"]) == run.EXIT_SOME_FAILED
    # Groups really did run at the same time, and the per-key operators together.
    assert most[0] > len(operator_hosts(OPERATORS["chargy"]))
    assert together[1] > 1
    shown = capsys.readouterr()
    # Results are reported in registry order, whatever order the groups finish in.
    reported = [line.split(":")[0] for line in shown.out.splitlines() if ": fetched " in line]
    assert reported == sorted(replayed)
