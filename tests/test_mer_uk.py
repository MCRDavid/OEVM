"""Mer UK publishes OCPI 2.2.1 locations and tariffs in one response, read by the ocpi_221
adapter with response_envelope set to by_module (no network)."""

from collections import Counter
from pathlib import Path

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.health import in_uk
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry

FIXTURES = Path(__file__).parent / "fixtures" / "mer_uk"
FEED = "https://uk.mer.eco/wp-json/ozev/v1/data"


def replay():
    config = load_registry()["mer_uk"]
    transport = ReplayTransport(FIXTURES)
    with PoliteClient(config, transport=transport, sleep=lambda _s: None) as client:
        return fetch(config, client), transport


def test_one_request_reads_both_modules():
    result, transport = replay()
    assert transport.requested == [FEED]
    assert result.complete
    assert result.modules["locations"].total_reported is None
    assert result.issues == []


def test_the_shared_url_is_an_opt_in_setting():
    config = load_registry()["mer_uk"]
    assert config.response_envelope == "by_module"
    assert config.endpoints["locations"].url == config.endpoints["tariffs"].url == FEED
    others = [c for c in load_registry().values() if c.id != "mer_uk"]
    assert all(c.response_envelope != "by_module" for c in others)
    assert any('"tariffs"' in finding.summary for finding in config.findings)


def test_recorded_locations_convert_faithfully():
    result, _ = replay()
    assert len(result.locations) == 6
    assert all(loc.id.startswith("mer_uk:GB:MER:") for loc in result.locations)
    assert all(in_uk(loc) for loc in result.locations)
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert {"available", "charging", "blocked", "out_of_order", "unknown"} <= set(statuses)
    power = {c.power_type for loc in result.locations for e in loc.evses for c in e.connectors}
    assert power == {"ac_1_phase", "ac_3_phase", "dc"}
    hours = {loc.opening_hours.twenty_four_seven for loc in result.locations}
    assert hours == {True, False}
    assert {loc.operator.name for loc in result.locations} == {"Mer"}


def test_every_connector_has_a_gbp_price():
    result, _ = replay()
    tariffs = {tariff.id: tariff for tariff in result.tariffs}
    referenced = {
        t for loc in result.locations for e in loc.evses for c in e.connectors for t in c.tariff_ids
    }
    assert referenced == set(tariffs)
    assert len(tariffs) == 4
    for tariff in tariffs.values():
        assert tariff.currency == "GBP"
        assert describe_tariff(tariff).state == "priced"


def test_mer_uk_records_its_source_and_terms():
    config = load_registry()["mer_uk"]
    assert config.adapter == "ocpi_221" and config.auth.method == "none"
    assert config.licence.checked.isoformat() == "2026-10-10"
    assert "terms and conditions" in config.licence.basis
    assert any(
        source.url == "https://uk.mer.eco/live-charge-point-data/" for source in config.sources
    )
