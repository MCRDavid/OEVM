"""Tests for the eco_movement_pcpr adapter (adapters/eco_movement.py). No test touches the
network: made-up responses (httpx.MockTransport) cover paging and the adapter's rules.
"""

from datetime import UTC, datetime

import httpx
import pytest

from adapters import eco_movement
from adapters.http import FeedError, PoliteClient
from pipeline import run
from pipeline.registry import load_registry

NOW = datetime(2026, 10, 26, 19, 30, tzinfo=UTC)
LOCATIONS = "https://open-chargepoints.com/api/ocpi/cpo/2.2.1/locations/"
TARIFFS = "https://open-chargepoints.com/api/ocpi/cpo/2.2.1/tariffs/"
FAKE_TOKEN = "made-up-token-for-tests"
OPERATORS = load_registry()
SHARED = sorted(i for i, c in OPERATORS.items() if c.adapter == "eco_movement_pcpr")


def ocpi_body(data: list) -> dict:
    return {"data": data, "status_code": 1000, "status_message": "Success", "timestamp": "x"}


def location(location_id: str) -> dict:
    return {
        "country_code": "GB",
        "party_id": "UBI",
        "id": location_id,
        "publish": True,
        "address": "1 Example Street",
        "city": "Exampletown",
        "country": "GBR",
        "coordinates": {"latitude": "51.50000", "longitude": "-0.10000"},
        "time_zone": "Europe/London",
        "evses": [],
        "last_updated": "2026-10-26T10:00:00Z",
    }


class Server:
    """Serves fixed responses by URL and records each request."""

    def __init__(self, pages: dict[str, httpx.Response]) -> None:
        self.pages = pages
        self.requests: list[httpx.Request] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        url = str(request.url)
        assert url in self.pages, f"unexpected request {url}"
        return self.pages[url]


def fetch_with(server: Server, operator_id: str = "ubitricity", **kwargs):
    config = OPERATORS[operator_id]
    with PoliteClient(
        config,
        transport=httpx.MockTransport(server),
        sleep=lambda _seconds: None,
        clock=lambda: 0,
        key=FAKE_TOKEN,
    ) as client:
        return eco_movement.fetch(config, client, now=NOW, **kwargs)


def test_asks_for_pages_of_1000_and_follows_the_link_header():
    second = f"{LOCATIONS}?offset=1000&limit=1000"
    server = Server(
        {
            f"{LOCATIONS}?limit=1000": httpx.Response(
                200,
                json=ocpi_body([location("A"), location("B")]),
                headers={"Link": f'<{second}>; rel="next"'},
            ),
            second: httpx.Response(200, json=ocpi_body([location("C")])),
            f"{TARIFFS}?limit=1000": httpx.Response(200, json=ocpi_body([])),
        }
    )
    result = fetch_with(server)

    assert [str(r.url) for r in server.requests] == [
        f"{LOCATIONS}?limit=1000",
        second,
        f"{TARIFFS}?limit=1000",
    ]
    assert {r.headers["Authorization"] for r in server.requests} == {f"Token {FAKE_TOKEN}"}
    assert result.complete
    assert [loc.id for loc in result.locations] == [
        "ubitricity:GB:UBI:A",
        "ubitricity:GB:UBI:B",
        "ubitricity:GB:UBI:C",
    ]


@pytest.mark.parametrize(("asked", "sent"), [(50, 50), (5000, 1000)])
def test_a_page_size_is_kept_up_to_the_documented_largest(asked, sent):
    server = Server(
        {
            f"{LOCATIONS}?limit={sent}": httpx.Response(200, json=ocpi_body([])),
            f"{TARIFFS}?limit={sent}": httpx.Response(200, json=ocpi_body([])),
        }
    )
    fetch_with(server, page_size=asked)
    assert len(server.requests) == 2


def test_date_from_is_refused_before_any_request():
    server = Server({})
    with pytest.raises(FeedError, match="date_from"):
        fetch_with(server, date_from=NOW)
    assert server.requests == []


def test_an_operator_on_another_adapter_is_refused():
    server = Server({})
    with pytest.raises(FeedError, match="not eco_movement_pcpr"):
        fetch_with(server, operator_id="chargy")
    assert server.requests == []


def test_the_daily_run_uses_this_adapter():
    assert run.ADAPTERS["eco_movement_pcpr"] is eco_movement.fetch


@pytest.mark.parametrize("operator_id", SHARED)
def test_every_eco_movement_network_uses_the_same_host_gap_and_its_own_token(operator_id):
    config, ubitricity = OPERATORS[operator_id], OPERATORS["ubitricity"]
    assert config.endpoints == ubitricity.endpoints
    assert config.rate_limit == ubitricity.rate_limit
    assert config.rate_limit.min_seconds_between_requests == 125
    assert (config.auth.method, config.auth.name, config.auth.scheme) == (
        "header",
        "Authorization",
        "Token",
    )
    assert config.auth.secret_name == f"{operator_id.upper()}_TOKEN"
    others = {OPERATORS[i].auth.secret_name for i in SHARED if i != operator_id}
    assert config.auth.secret_name not in others
