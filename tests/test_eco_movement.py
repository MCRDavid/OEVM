"""Tests for the eco_movement_pcpr adapter (adapters/eco_movement.py). No test touches the
network: made-up responses (httpx.MockTransport) cover paging and the adapter's rules, and
each network's fixtures, trimmed from responses recorded on 29 October 2026, are replayed.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from adapters import eco_movement
from adapters.http import FeedError, PoliteClient
from adapters.replay import ReplayTransport
from pipeline import publish, run
from pipeline.registry import load_registry

NOW = datetime(2026, 10, 26, 19, 30, tzinfo=UTC)
LOCATIONS = "https://open-chargepoints.com/api/ocpi/cpo/2.2.1/locations/"
TARIFFS = "https://open-chargepoints.com/api/ocpi/cpo/2.2.1/tariffs/"
FAKE_TOKEN = "made-up-token-for-tests"
OPERATORS = load_registry()
SHARED = sorted(i for i, c in OPERATORS.items() if c.adapter == "eco_movement_pcpr")
SWITCHED_ON = [i for i in SHARED if OPERATORS[i].enabled]
FIXTURES = Path(__file__).parent / "fixtures"


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


def test_paging_stops_once_x_total_count_records_have_arrived():
    # As recorded on 2026-10-29: the last page still links to an offset past the end.
    past_the_end = f"{LOCATIONS}?offset=2&limit=1000"
    server = Server(
        {
            f"{LOCATIONS}?limit=1000": httpx.Response(
                200,
                json=ocpi_body([location("A"), location("B")]),
                headers={"Link": f'<{past_the_end}>; rel="next"', "X-Total-Count": "2"},
            ),
            f"{TARIFFS}?limit=1000": httpx.Response(
                200,
                json=ocpi_body([]),
                headers={
                    "Link": f'<{TARIFFS}?offset=0&limit=1000>; rel="next"',
                    "X-Total-Count": "0",
                },
            ),
        }
    )
    result = fetch_with(server)

    assert [str(r.url) for r in server.requests] == [
        f"{LOCATIONS}?limit=1000",
        f"{TARIFFS}?limit=1000",
    ]
    assert result.complete
    assert len(result.locations) == 2


def test_paging_follows_the_link_while_records_are_still_to_come():
    second = f"{LOCATIONS}?offset=1&limit=1000"
    server = Server(
        {
            f"{LOCATIONS}?limit=1000": httpx.Response(
                200,
                json=ocpi_body([location("A")]),
                headers={"Link": f'<{second}>; rel="next"', "X-Total-Count": "2"},
            ),
            second: httpx.Response(
                200, json=ocpi_body([location("B")]), headers={"X-Total-Count": "2"}
            ),
            f"{TARIFFS}?limit=1000": httpx.Response(200, json=ocpi_body([])),
        }
    )
    result = fetch_with(server)

    assert len(server.requests) == 3
    assert [loc.id for loc in result.locations] == ["ubitricity:GB:UBI:A", "ubitricity:GB:UBI:B"]


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


class TokenRecorder(ReplayTransport):
    """Replays a network's fixtures and keeps the Authorization header of each request."""

    def __init__(self, directory: Path):
        super().__init__(directory)
        self.authorization: list[str | None] = []

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        self.authorization.append(request.headers.get("authorization"))
        return super().handle_request(request)


def replay(operator_id: str):
    transport = TokenRecorder(FIXTURES / operator_id)
    result = run.run_operator(
        OPERATORS[operator_id], transport=transport, sleep=lambda _s: None, key=FAKE_TOKEN
    )
    return result, transport


def prices_shown(operator_id: str, out: Path) -> list[str]:
    """The price texts of every tariff option on the network's published locations."""
    result, _ = replay(operator_id)
    publish.publish([result], OPERATORS, out, mode="fixtures", generated_at=NOW)
    return [
        option["text"]
        for path in sorted((out / "data" / "loc").rglob("*.json"))
        for option in json.loads(path.read_text(encoding="utf-8"))["tariff_options"]
    ]


def test_the_thirteen_networks_with_tokens_are_switched_on():
    assert SWITCHED_ON == [
        "allego",
        "blink_charging_uk",
        "chargepoint",
        "esb_ecars",
        "esb_energy",
        "ev_point",
        "evyve",
        "ionity",
        "lidl",
        "pod",
        "raw_charging",
        "source_ev",
        "ubitricity",
    ]


@pytest.mark.parametrize("operator_id", SWITCHED_ON)
def test_each_network_is_read_in_one_request_per_module_with_its_own_token(operator_id):
    result, transport = replay(operator_id)
    # Each recorded page still links past the last record; the adapter does not follow it.
    assert transport.requested == [f"{LOCATIONS}?limit=1000", f"{TARIFFS}?limit=1000"]
    assert transport.authorization == [f"Token {FAKE_TOKEN}"] * 2
    assert result.complete
    config = OPERATORS[operator_id]
    prefix = f"{operator_id}:{config.ocpi_country_code}:{config.ocpi_party_id}:"
    assert result.locations and all(loc.id.startswith(prefix) for loc in result.locations)
    assert result.modules["locations"].total_reported == len(result.locations)


@pytest.mark.parametrize("operator_id", SWITCHED_ON)
def test_the_fixtures_hold_no_token(operator_id):
    for path in (FIXTURES / operator_id).glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        assert "authorization" not in text and FAKE_TOKEN not in text, path.name


def test_vat_is_added_where_the_owner_decided_the_prices_give_none(tmp_path):
    shown = prices_shown("allego", tmp_path)
    added = "including VAT, with VAT at 20% added by this project"
    assert any(text.startswith(f"63p per kWh {added}") for text in shown)
    assert all(added in text for text in shown)


def test_stated_vat_is_read_as_in_the_price_where_the_owner_decided(tmp_path):
    shown = prices_shown("esb_energy", tmp_path)
    assert any(text.startswith("80p per kWh") for text in shown)
    assert not any("96p" in text for text in shown)
    assert all(
        "reading the VAT rate the feed states as already in the price" in text for text in shown
    )


def test_pods_isle_of_man_site_is_left_off_and_its_zero_tariff_shows_free(tmp_path):
    shown = prices_shown("pod", tmp_path)
    assert "Free" in shown
    assert any(text.startswith("38p per kWh including VAT, reading") for text in shown)
    layer = json.loads((tmp_path / "data" / "locations.geojson").read_text())
    names = {f["properties"]["name"] for f in layer["features"]}
    assert len(names) == 3 and not any("IOM" in name for name in names)


def test_chargepoints_dollar_tariffs_and_unstated_vat_are_never_guessed(tmp_path):
    shown = prices_shown("chargepoint", tmp_path)
    assert "Price unknown" in shown
    assert all("VAT not stated" in text for text in shown if text != "Price unknown")


def test_source_evs_vat_of_0_2_is_shown_as_published(tmp_path):
    shown = prices_shown("source_ev", tmp_path)
    assert any(text.startswith("45.1p per kWh") for text in shown)
    assert any(text.startswith("90p per kWh") for text in shown)
