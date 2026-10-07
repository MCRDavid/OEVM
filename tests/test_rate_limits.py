"""Tests that this project never breaks a rate limit.

Two rules apply to every operator:

1. Project policy: at least 1 second between any two requests (MIN_SECONDS_BETWEEN_REQUESTS).
2. Every limit the operator publishes (rate_limit.limits in its registry file).

The Public Charge Point Regulations 2023 set no limit for data users (see the transparency
page), so the registry checks and these simulations cover all the limits that apply.

The simulations use a fake clock that only moves when the client waits. Responses take no
time at all, which is the worst case: a faster server can never make the client send
requests faster than these tests allow.
"""

import contextlib
from itertools import pairwise

import httpx
import pytest
from pydantic import ValidationError

from adapters.http import FeedError, PoliteClient
from adapters.ocpi_221.client import fetch_module
from pipeline.registry import load_registry
from schema.operator import MIN_SECONDS_BETWEEN_REQUESTS, Auth, OperatorConfig, RateLimit

EXAMPLE = "https://example.invalid/ocpi"
OPERATORS = load_registry()


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        assert seconds >= 0
        self.now += seconds


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


def assert_within_limits(config: OperatorConfig, times: list[float]) -> None:
    gap = config.rate_limit.min_seconds_between_requests
    for earlier, later in pairwise(times):
        assert later - earlier >= gap - 1e-9, f"requests {later - earlier:g} s apart"
    for documented in config.rate_limit.limits:
        for start in times:
            window = [t for t in times if start <= t < start + documented.per_seconds]
            assert len(window) <= documented.requests, (
                f"{len(window)} requests in {documented.per_seconds:g} s, "
                f"limit {documented.requests}"
            )


def without_keys(config: OperatorConfig) -> OperatorConfig:
    """The same operator with no key, so the client can start; keys do not affect timing."""
    return config.model_copy(update={"auth": Auth(method="none")})


def simulate(config: OperatorConfig, responses) -> list[float]:
    """Send requests until the response list runs out; return the time of each request."""
    config = without_keys(config)
    clock, times, queue = FakeClock(), [], list(responses)

    def handler(request: httpx.Request) -> httpx.Response:
        times.append(clock())
        return queue.pop(0)

    with PoliteClient(
        config, transport=httpx.MockTransport(handler), sleep=clock.sleep, clock=clock
    ) as client:
        while queue:
            with contextlib.suppress(FeedError):
                client.get(f"{EXAMPLE}/locations")
    return times


def busy_responses() -> list[httpx.Response]:
    """Successes mixed with retryable failures, including a Retry-After shorter than any gap."""
    pattern = [
        httpx.Response(200, json={}),
        httpx.Response(503),
        httpx.Response(429, headers={"Retry-After": "0"}),
        httpx.Response(200, json={}),
        httpx.Response(500),
        httpx.Response(200, json={}),
    ]
    return pattern * 12


# The registry


def test_every_operator_keeps_the_project_minimum_gap():
    for config in OPERATORS.values():
        assert config.rate_limit.min_seconds_between_requests >= MIN_SECONDS_BETWEEN_REQUESTS


def test_every_operator_gap_satisfies_its_published_limits():
    for config in OPERATORS.values():
        for documented in config.rate_limit.limits:
            assert config.rate_limit.min_seconds_between_requests >= documented.min_interval, (
                config.id
            )


def test_a_gap_that_breaks_a_published_limit_is_rejected():
    with pytest.raises(ValidationError, match="would break the documented limit"):
        RateLimit.model_validate(
            {"min_seconds_between_requests": 60, "limits": [limit(30, 3600, "tariffs")]}
        )


def test_a_gap_below_the_project_minimum_is_rejected():
    with pytest.raises(ValidationError):
        RateLimit.model_validate({"min_seconds_between_requests": 0.5})


# The client, simulated for every operator in the registry


@pytest.mark.parametrize("operator_id", sorted(OPERATORS))
def test_client_never_breaks_an_operators_limits(operator_id):
    config = OPERATORS[operator_id]
    times = simulate(config, busy_responses())
    assert len(times) == len(busy_responses())
    assert_within_limits(config, times)


def test_client_keeps_a_strict_hourly_limit_across_retries():
    config = make_config(120, [limit(30, 3600, "tariffs"), limit(1, 30, "statuses")])
    times = simulate(config, busy_responses())
    assert_within_limits(config, times)
    assert len([t for t in times if t < 3600]) == 30


def test_a_long_retry_after_is_honoured():
    config = make_config(2)
    times = simulate(
        config, [httpx.Response(503, headers={"Retry-After": "90"}), httpx.Response(200, json={})]
    )
    assert times[1] - times[0] >= 90


def test_a_retry_after_longer_than_we_wait_is_never_cut_short():
    config = make_config(2)
    clock, times = FakeClock(), []
    responses = [httpx.Response(429, headers={"Retry-After": "3600"}), httpx.Response(200)]

    def handler(request: httpx.Request) -> httpx.Response:
        times.append(clock())
        return responses.pop(0)

    with PoliteClient(
        config, transport=httpx.MockTransport(handler), sleep=clock.sleep, clock=clock
    ) as client:
        with pytest.raises(FeedError, match="asked to wait 3600 s"):
            client.get(f"{EXAMPLE}/locations")
        clock.sleep(1800)
        with pytest.raises(FeedError, match="asked this project to wait"):
            client.get(f"{EXAMPLE}/tariffs")  # nothing is sent during the wait
        assert len(times) == 1
        clock.sleep(1800)
        assert client.get(f"{EXAMPLE}/tariffs").status_code == 200
    assert times[1] - times[0] >= 3600


def test_paging_through_a_whole_feed_stays_within_limits():
    config = make_config(120, [limit(30, 3600)])
    clock, times = FakeClock(), []
    pages = 75

    def handler(request: httpx.Request) -> httpx.Response:
        times.append(clock())
        offset = int(request.url.params.get("offset", 0))
        headers = {"X-Total-Count": str(pages)}
        if offset + 1 < pages:
            headers["Link"] = f'<{EXAMPLE}/tariffs?offset={offset + 1}>; rel="next"'
        body = {"status_code": 1000, "data": [{"id": str(offset)}]}
        return httpx.Response(200, headers=headers, json=body)

    with PoliteClient(
        config, transport=httpx.MockTransport(handler), sleep=clock.sleep, clock=clock
    ) as client:
        result = fetch_module(client, "tariffs", f"{EXAMPLE}/tariffs")
    assert result.complete and len(result.records) == pages
    assert_within_limits(config, times)
