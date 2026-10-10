"""PoGo Charge's open data feeds on info.smartcharging.uk are OCPI 2.2.1 responses read by
the ocpi_221 adapter (no network)."""

from collections import Counter
from pathlib import Path

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.health import in_uk
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry
from pipeline.tariffs import price_connector

FIXTURES = Path(__file__).parent / "fixtures" / "pogo_charge"
FEED = "https://info.smartcharging.uk/public_feed/locations/4009"


def replay():
    config = load_registry()["pogo_charge"]
    transport = ReplayTransport(FIXTURES)
    with PoliteClient(config, transport=transport, sleep=lambda _s: None) as client:
        return fetch(config, client), transport


def test_each_feed_is_read_in_one_request():
    result, transport = replay()
    assert transport.requested == [FEED, f"{FEED}/tariffs"]
    assert result.complete
    assert result.modules["locations"].total_reported == 5
    assert result.issues == [
        "connector id is a number, not a string; read as its digits (16 times)",
        "location id is a number, not a string; read as its digits (5 times)",
    ]


def test_recorded_locations_convert_faithfully():
    result, _ = replay()
    assert len(result.locations) == 5
    assert all(loc.id.startswith("pogo_charge:GB:POG:") for loc in result.locations)
    assert "pogo_charge:GB:POG:241228" in {loc.id for loc in result.locations}
    assert all(in_uk(loc) for loc in result.locations)
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert {"available", "charging", "inoperative", "unknown"} <= set(statuses)
    power = {c.power_type for loc in result.locations for e in loc.evses for c in e.connectors}
    assert power == {"ac_1_phase", "ac_3_phase", "dc"}
    # No location gives opening_times, so the hours are unknown.
    assert all(loc.opening_hours is None for loc in result.locations)


def test_connectors_naming_another_operators_tariffs_show_price_unknown():
    result, _ = replay()
    tariffs = {tariff.id: tariff for tariff in result.tariffs}
    assert len(tariffs) == 13
    assert {t.currency for t in tariffs.values()} == {"GBP"}
    assert {describe_tariff(t).state for t in tariffs.values()} == {"priced", "free"}
    prices = [
        price_connector(c, tariffs, location_id=loc.id, evse_uid=e.uid)
        for loc in result.locations
        for e in loc.evses
        for c in e.connectors
    ]
    assert {p.text for p in prices} == {"Price unknown"}
    assert {p.state for p in prices} == {"unknown"}
    # The tariffs named are not in PoGo Charge's own response, and none is borrowed.
    named = {t for p in prices for t in p.unresolved_ids}
    assert len(named) == 5 and not named & set(tariffs)
    assert sum(1 for p in prices if not p.unresolved_ids) == 3  # these name no tariff


def test_pogo_charge_records_its_source_and_terms():
    config = load_registry()["pogo_charge"]
    assert config.adapter == "ocpi_221" and config.auth.method == "none"
    assert config.licence.checked.isoformat() == "2026-10-10"
    assert "standing rule" in config.licence.basis
    assert any(source.url == "https://pogocharge.com/faqs/" for source in config.sources)
    assert any("Evolt Network" in finding.summary for finding in config.findings)
