"""ChargePlace Scotland's open data feeds on info.smartcharging.uk are OCPI 2.2.1 responses
read by the ocpi_221 adapter (no network)."""

from collections import Counter
from pathlib import Path

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.health import in_uk
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry
from pipeline.tariffs import price_connector, price_locations, related_tariffs

FIXTURES = Path(__file__).parent / "fixtures" / "chargeplace_scotland"
FEED = "https://info.smartcharging.uk/public_feed/locations/2463"


def replay(operator_id="chargeplace_scotland"):
    config = load_registry()[operator_id]
    transport = ReplayTransport(FIXTURES.parent / operator_id)
    with PoliteClient(config, transport=transport, sleep=lambda _s: None) as client:
        return fetch(config, client), transport


def shown_prices(result):
    tariffs = {tariff.id: tariff for tariff in result.tariffs}
    return {
        loc.name: {
            price_connector(c, tariffs, location_id=loc.id, evse_uid=e.uid).text
            for e in loc.evses
            for c in e.connectors
        }
        for loc in result.locations
    }


def test_each_feed_is_read_in_one_request():
    result, transport = replay()
    assert transport.requested == [FEED, f"{FEED}/tariffs"]
    assert result.complete
    assert result.modules["locations"].total_reported == 6
    assert result.issues == [
        "connector id is a number, not a string; read as its digits (14 times)",
        "connector power not calculated for power_type 'ac_3_phase'",
        "location id is a number, not a string; read as its digits (6 times)",
    ]


def test_recorded_locations_convert_faithfully():
    result, _ = replay()
    assert len(result.locations) == 6
    assert all(loc.id.startswith("chargeplace_scotland:GB:CPS:") for loc in result.locations)
    assert all(in_uk(loc) for loc in result.locations)
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert {"available", "charging", "inoperative", "unknown"} <= set(statuses)
    power = {c.power_type for loc in result.locations for e in loc.evses for c in e.connectors}
    assert power == {"ac_1_phase", "ac_3_phase", "dc"}
    assert all(loc.opening_hours is None for loc in result.locations)
    dornoch = next(loc for loc in result.locations if loc.name == "Dornoch Castle Hotel")
    assert [c.max_kw for e in dornoch.evses for c in e.connectors].count(None) == 1


def test_prices_show_in_gbp_and_free_only_when_confirmed():
    result, _ = replay()
    assert {t.currency for t in result.tariffs} == {"GBP"}
    free = [t for t in result.tariffs if describe_tariff(t).text == "Free"]
    assert len(free) == 1 and free[0].price_state == "free_confirmed"
    shown = shown_prices(result)
    assert shown["Atlantic Quay"] == {"Free"}
    assert shown["Rosslyn Chapel"] == {
        "42p per kWh including VAT; minimum charge £0.83 excluding VAT"
    }
    assert len(shown["Mar Place"]) == 2  # AC and DC tariffs, each with an hourly price


def test_missing_and_other_operators_tariffs_show_price_unknown():
    result, _ = replay()
    shown = shown_prices(result)
    # Names a tariff that is only in Evolt Network's response.
    assert shown["Herbertshire Castle Car Park, Dunipace"] == {"Price unknown"}
    # Names no tariff at all.
    assert shown["Broomburn Shops Car Park, Renfrewshire"] == {"Price unknown"}


def test_a_tariff_only_evolt_networks_feed_holds_is_priced_from_it():
    # By the owner's decision (tariffs_from), the one Evolt Network tariff with that exact
    # id is used when both feeds are fetched. A connector that names no tariff stays unknown.
    result, _ = replay()
    evolt, _ = replay("evolt")
    found = related_tariffs(result.locations, result.tariffs, {"evolt": evolt.tariffs})
    assert len(found) == 1
    priced = price_locations(result.locations, result.tariffs, found)
    by_location = {}
    for price in priced:
        by_location.setdefault(price.location_id, set()).add(price.state)
    names = {loc.id: loc.name for loc in result.locations}
    shown = {names[i]: states for i, states in by_location.items()}
    assert shown["Herbertshire Castle Car Park, Dunipace"] == {"priced"}
    assert shown["Broomburn Shops Car Park, Renfrewshire"] == {"unknown"}


def test_chargeplace_scotland_records_its_source_and_terms():
    config = load_registry()["chargeplace_scotland"]
    assert config.adapter == "ocpi_221" and config.auth.method == "none"
    assert config.licence.checked.isoformat() == "2026-10-10"
    assert "standing rule" in config.licence.basis
    assert any(
        source.url == "https://chargeplacescotland.org/network-performance-2/"
        for source in config.sources
    )
