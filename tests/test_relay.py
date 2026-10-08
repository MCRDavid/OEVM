"""The relay for feeds that refuse the daily run's requests (adapters/http.py, ADR 0010).

No test touches the network: requests go to httpx.MockTransport.
"""

import httpx
import pytest

from adapters import http
from adapters.http import RELAY_TOKEN_HEADER, FeedError, PoliteClient, relay_route
from pipeline import run
from pipeline.registry import load_registry
from schema.operator import OperatorConfig

TOKEN = "test-relay-token-not-real"
RELAY = "https://oevm-relay.example.workers.dev"


@pytest.fixture
def geniepoint() -> OperatorConfig:
    return load_registry()["geniepoint"]


@pytest.fixture
def relay_env(monkeypatch):
    monkeypatch.setenv("GENIEPOINT_RELAY_URL", RELAY)
    monkeypatch.setenv("GENIEPOINT_RELAY_TOKEN", TOKEN)


def recorder(status: int = 200):
    seen = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(status, json={"data": []})

    return seen, httpx.MockTransport(handler)


def test_requests_go_direct_when_the_relay_is_not_set(geniepoint, monkeypatch):
    monkeypatch.delenv("GENIEPOINT_RELAY_URL", raising=False)
    monkeypatch.delenv("GENIEPOINT_RELAY_TOKEN", raising=False)
    assert relay_route(geniepoint) is None
    seen, transport = recorder()
    with PoliteClient(geniepoint, transport=transport, sleep=lambda _: None) as client:
        client.get("https://opendata.geniepoint.co.uk/locations")
    assert str(seen[0].url) == "https://opendata.geniepoint.co.uk/locations"
    assert RELAY_TOKEN_HEADER not in seen[0].headers


def test_requests_go_through_the_relay_with_the_same_path_and_user_agent(geniepoint, relay_env):
    seen, transport = recorder()
    with PoliteClient(geniepoint, transport=transport, sleep=lambda _: None) as client:
        client.get("https://opendata.geniepoint.co.uk/tariffs?offset=0&limit=50")
    request = seen[0]
    assert str(request.url) == f"{RELAY}/geniepoint/tariffs?offset=0&limit=50"
    assert request.headers[RELAY_TOKEN_HEADER] == TOKEN
    assert request.headers["User-Agent"] == http.USER_AGENT


def test_the_gap_is_kept_on_the_operators_own_host(geniepoint, relay_env):
    _seen, transport = recorder()
    ticks = iter(range(0, 1000))
    waits = []
    with PoliteClient(
        geniepoint, transport=transport, sleep=waits.append, clock=lambda: float(next(ticks))
    ) as client:
        client.get("https://opendata.geniepoint.co.uk/locations")
        client.get("https://opendata.geniepoint.co.uk/tariffs")
    assert waits and waits[0] > 0
    # One timer, for the operator's own host; none for the relay.
    assert set(http._HOST_TIMERS) == {"opendata.geniepoint.co.uk"}


def test_messages_name_the_operators_url_and_never_the_token(geniepoint, relay_env):
    _seen, transport = recorder(status=403)
    with PoliteClient(geniepoint, transport=transport, sleep=lambda _: None) as client:
        response = client.get("https://opendata.geniepoint.co.uk/locations")
        message = client.describe("https://opendata.geniepoint.co.uk/locations")
        assert response.status_code == 403
        assert message == "https://opendata.geniepoint.co.uk/locations (through the relay)"
        assert client.redact(f"echo {TOKEN}") == "echo REDACTED"
        assert client.describe("https://example.org/x") == "https://example.org/x"


def test_other_hosts_are_never_relayed(geniepoint, relay_env):
    seen, transport = recorder()
    with PoliteClient(geniepoint, transport=transport, sleep=lambda _: None) as client:
        client.get("https://example.org/data")
    assert str(seen[0].url) == "https://example.org/data"
    assert RELAY_TOKEN_HEADER not in seen[0].headers


@pytest.mark.parametrize(
    ("url", "token", "problem"),
    [
        (RELAY, "", "needs GENIEPOINT_RELAY_TOKEN"),
        ("", TOKEN, "needs GENIEPOINT_RELAY_URL"),
        ("http://relay.example.org", TOKEN, "must be an https address"),
    ],
)
def test_half_set_or_plain_http_relays_stop_the_run(geniepoint, monkeypatch, url, token, problem):
    monkeypatch.setenv("GENIEPOINT_RELAY_URL", url)
    monkeypatch.setenv("GENIEPOINT_RELAY_TOKEN", token)
    with pytest.raises(FeedError, match=problem):
        relay_route(geniepoint)


def test_a_relay_on_a_sub_path_keeps_its_path(geniepoint, monkeypatch):
    monkeypatch.setenv("GENIEPOINT_RELAY_URL", "https://relay.example.org/oevm/")
    monkeypatch.setenv("GENIEPOINT_RELAY_TOKEN", TOKEN)
    route = relay_route(geniepoint)
    assert route.url("https://opendata.geniepoint.co.uk/locations?a=1") == (
        "https://relay.example.org/oevm/geniepoint/locations?a=1"
    )


def test_feeds_that_need_a_key_can_never_be_relayed(geniepoint):
    jolt = load_registry()["jolt"].model_dump()
    jolt["relay"] = geniepoint.relay.model_dump()
    with pytest.raises(ValueError, match="only a feed that needs no key may be relayed"):
        OperatorConfig.model_validate(jolt)
    same = geniepoint.model_dump()
    same["relay"]["secret_name"] = same["relay"]["url_variable"]
    with pytest.raises(ValueError, match="must differ"):
        OperatorConfig.model_validate(same)


def test_fixture_replays_never_use_the_relay(relay_env):
    results = run.run_fixtures(load_registry())
    assert any(result.operator_id == "geniepoint" for result in results)
