"""Urban Fox's OCPI 2.2.1 open data, read by the ocpi_221 adapter with offset paging and a
Link header to the next page (no network)."""

from collections import Counter
from pathlib import Path

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.health import in_uk
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry
from pipeline.tariffs import price_locations, withheld_free_tariffs

FIXTURES = Path(__file__).parent / "fixtures" / "urban_fox"
FEED = "https://api.urbanfox.network/api/opendata"


def replay():
    config = load_registry()["urban_fox"]
    transport = ReplayTransport(FIXTURES)
    with PoliteClient(config, transport=transport, sleep=lambda _s: None) as client:
        return fetch(config, client), transport


def test_the_next_page_link_is_followed():
    result, transport = replay()
    assert transport.requested == [
        f"{FEED}/locations",
        f"{FEED}/locations?limit=50&offset=50",
        f"{FEED}/tariffs",
    ]
    assert result.complete
    assert result.issues == []


def test_recorded_locations_convert_faithfully():
    result, _ = replay()
    assert len(result.locations) == 6
    assert all(loc.id.startswith("urban_fox:GB:UFX:") for loc in result.locations)
    assert all(in_uk(loc) for loc in result.locations)
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert set(statuses) == {"available", "charging", "out_of_order"}
    power = {c.power_type for loc in result.locations for e in loc.evses for c in e.connectors}
    assert power == {"ac_1_phase", "ac_3_phase"}


def test_every_connector_names_a_tariff_in_the_feed():
    result, _ = replay()
    referenced = {
        t for loc in result.locations for e in loc.evses for c in e.connectors for t in c.tariff_ids
    }
    assert referenced == {tariff.id for tariff in result.tariffs}


def test_prices_state_vat_0_and_show_as_including_vat():
    result, _ = replay()
    priced = [t for t in result.tariffs if t.price_state == "priced"]
    assert {describe_tariff(t).text for t in priced} == {
        "36p per kWh including VAT",
        "50p per kWh including VAT",
    }
    assert all(c.vat == 0 for t in result.tariffs for e in t.elements for c in e.price_components)


def test_tariffs_priced_at_zero_show_price_unknown_by_the_owners_decision():
    config = load_registry()["urban_fox"]
    result, _ = replay()
    ids = config.zero_price_tariffs.tariff_ids
    withheld = withheld_free_tariffs(result.tariffs, ids)
    zero = [t for t in result.tariffs if t.price_state == "free_confirmed"]
    assert len(zero) == 3 and {t.id for t in zero} == withheld
    for tariff in zero:
        assert describe_tariff(tariff, zero_price_withheld=True).text == "Price unknown"
    prices = price_locations(result.locations, result.tariffs, {}, withheld)
    assert "free_confirmed" not in {p.state for p in prices}


def test_urban_fox_records_its_terms_and_its_own_feed_decision():
    config = load_registry()["urban_fox"]
    assert config.enabled and config.licence.checked
    assert config.rate_limit.limits == []
    assert config.rate_limit.min_seconds_between_requests >= 2
    assert config.own_feed_over_copies.operators == ["monta"]
    assert any("Monta" in finding.summary for finding in config.findings)
