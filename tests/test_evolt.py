"""Evolt Network's open data feeds on info.smartcharging.uk are OCPI 2.2.1 responses read by
the ocpi_221 adapter (no network)."""

from collections import Counter
from pathlib import Path

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline import run
from pipeline.health import in_uk
from pipeline.pricing import describe_tariff
from pipeline.publish import corrected_coordinates
from pipeline.registry import load_registry
from pipeline.tariffs import price_connector, price_locations, related_tariffs

FIXTURES = Path(__file__).parent / "fixtures" / "evolt"
FEED = "https://info.smartcharging.uk/public_feed/locations/3666"
SMARTCHARGING = ["pogo_charge", "evolt", "chargeplace_scotland"]


def replay(operator_id="evolt"):
    config = load_registry()[operator_id]
    transport = ReplayTransport(FIXTURES.parent / operator_id)
    with PoliteClient(config, transport=transport, sleep=lambda _s: None) as client:
        return fetch(config, client), transport


def by_name(result):
    return {loc.name: loc for loc in result.locations}


def prices(result, location):
    tariffs = {tariff.id: tariff for tariff in result.tariffs}
    return [
        price_connector(c, tariffs, location_id=location.id, evse_uid=e.uid)
        for e in location.evses
        for c in e.connectors
    ]


def test_each_feed_is_read_in_one_request():
    result, transport = replay()
    assert transport.requested == [FEED, f"{FEED}/tariffs"]
    assert result.complete
    assert result.modules["locations"].total_reported == 8
    assert result.issues == [
        "connector id is a number, not a string; read as its digits (36 times)",
        "connector power not calculated for power_type 'ac_3_phase' (3 times)",
        "location id is a number, not a string; read as its digits (8 times)",
    ]


def test_recorded_locations_convert_faithfully():
    result, _ = replay()
    assert len(result.locations) == 8
    assert all(
        loc.id.split(":")[:3] in (["evolt", "GB", "SSM"], ["evolt", "AU", "SSM"])
        for loc in result.locations
    )
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert {"available", "charging", "inoperative", "unknown"} <= set(statuses)
    power = {c.power_type for loc in result.locations for e in loc.evses for c in e.connectors}
    assert power == {"ac_1_phase", "ac_3_phase", "dc"}
    assert all(loc.opening_hours is None for loc in result.locations)


def test_isle_of_man_and_australia_stay_off_and_the_missing_minus_sign_is_restored():
    result, _ = replay()
    outside = {loc.name for loc in result.locations if not in_uk(loc)}
    assert outside == {
        "Medical Centre Jurby",
        "Gemtek",
        "Cadworks Castle Building Services",
    }
    config = load_registry()["evolt"]
    assert config.swapped_coordinates is not None
    assert config.swapped_coordinates.decided.isoformat() == "2026-10-10"
    corrections = {
        loc.name: corrected_coordinates(loc, config) for loc in result.locations if not in_uk(loc)
    }
    # Only the Glasgow location (G2 7LP, longitude 4.26275) is an obvious mistake.
    assert corrections["Medical Centre Jurby"] is None
    assert corrections["Gemtek"] is None
    moved, note = corrections["Cadworks Castle Building Services"]
    assert (moved.coordinates.latitude, moved.coordinates.longitude) == (55.86005, -4.26275)
    assert (note.published.latitude, note.published.longitude) == (55.86005, 4.26275)
    assert in_uk(moved)


def test_prices_show_in_gbp_and_free_only_when_confirmed():
    result, _ = replay()
    assert {t.currency for t in result.tariffs} == {"GBP"}
    free = [t for t in result.tariffs if describe_tariff(t).text == "Free"]
    assert len(free) == 1 and free[0].price_state == "free_confirmed"
    shown = {name: {p.text for p in prices(result, loc)} for name, loc in by_name(result).items()}
    assert shown["Elm Street Car Park, Ipswich"] == {"Free"}
    assert shown["Daresbury Laboratory"] == {"24p per kWh including VAT"}
    session_fee = shown["All Saints Road Car Park"].pop()
    assert session_fee.startswith("79p per kWh, plus £20.00 per session after 135 minutes")


def test_a_tariff_only_chargeplace_scotlands_feed_holds_is_priced_from_it():
    result, _ = replay()
    location = by_name(result)["Granton Western Village"]
    granton = prices(result, location)
    assert {p.text for p in granton} == {"Price unknown"}
    assert {p.state for p in granton} == {"unknown"}
    assert all(p.unresolved_ids for p in granton)
    # By the owner's decision (tariffs_from), the one ChargePlace Scotland tariff with that
    # exact id is used when both feeds are fetched.
    cps, _ = replay("chargeplace_scotland")
    found = related_tariffs(result.locations, result.tariffs, {"chargeplace_scotland": cps.tariffs})
    assert set(found) == {i for p in granton for i in p.unresolved_ids}
    priced = price_locations([location], result.tariffs, found)
    assert {p.state for p in priced} == {"priced"}
    assert {i.split(":")[0] for p in priced for i in p.tariff_ids} == {"chargeplace_scotland"}


def test_connectors_with_zero_power_figures_have_unknown_power():
    result, _ = replay()
    daresbury = by_name(result)["Daresbury Laboratory"]
    unknown = [c.id for e in daresbury.evses for c in e.connectors if c.max_kw is None]
    assert sorted(unknown) == ["16", "17", "18"]


def test_the_three_feeds_on_one_host_are_fetched_in_turn_with_one_gap():
    registry = load_registry()
    configs = [registry[operator_id] for operator_id in SMARTCHARGING]
    assert {c.rate_limit.min_seconds_between_requests for c in configs} == {2}
    groups = run.host_groups(list(registry.values()))
    assert [g for g in groups if registry["evolt"] in g] == [
        [c for c in registry.values() if c.id in SMARTCHARGING]
    ]


def test_evolt_records_its_source_and_terms():
    config = load_registry()["evolt"]
    assert config.adapter == "ocpi_221" and config.auth.method == "none"
    assert config.licence.checked.isoformat() == "2026-10-10"
    assert "standing rule" in config.licence.basis
    assert any(source.url == "https://evoltnetwork.co.uk/faqs/" for source in config.sources)
    assert any("minus sign" in finding.summary for finding in config.findings)
