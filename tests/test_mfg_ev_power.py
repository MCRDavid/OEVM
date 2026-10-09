"""MFG EV Power's open data files are OCPI 2.2.1, read by the ocpi_221 adapter (no network)."""

from collections import Counter
from pathlib import Path

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry

FIXTURES = Path(__file__).parent / "fixtures" / "mfg_ev_power"


def replay():
    config = load_registry()["mfg_ev_power"]
    transport = ReplayTransport(FIXTURES)
    with PoliteClient(config, transport=transport, sleep=lambda _s: None) as client:
        return fetch(config, client), transport


def test_each_file_is_read_in_one_request_without_paging_headers():
    result, transport = replay()
    assert transport.requested == [
        "https://opendata.motorfuelgroup.net/locations",
        "https://opendata.motorfuelgroup.net/tariffs",
    ]
    assert result.complete
    assert result.modules["locations"].total_reported is None
    assert result.issues == []


def test_recorded_locations_convert_faithfully():
    result, _ = replay()
    assert len(result.locations) == 4
    assert all(location.id.startswith("mfg_ev_power:GB:MFL:") for location in result.locations)
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert {"available", "charging", "inoperative", "out_of_order", "unknown"} <= set(statuses)
    power = {c.power_type for loc in result.locations for e in loc.evses for c in e.connectors}
    assert power == {"dc"}
    hours = {loc.opening_hours.twenty_four_seven for loc in result.locations}
    assert hours == {True, False}


def test_every_connector_has_a_gbp_price_including_vat():
    result, _ = replay()
    tariffs = {tariff.id: tariff for tariff in result.tariffs}
    referenced = {
        t for loc in result.locations for e in loc.evses for c in e.connectors for t in c.tariff_ids
    }
    assert referenced == set(tariffs) == {"mfg_ev_power:GB:MFL:13", "mfg_ev_power:GB:MFL:21"}
    for tariff in tariffs.values():
        shown = describe_tariff(tariff)
        assert shown.state == "priced"
        assert "including VAT" in shown.text


def test_mfg_ev_power_records_its_source_and_terms():
    config = load_registry()["mfg_ev_power"]
    assert config.adapter == "ocpi_221" and config.enabled
    assert config.licence.checked.isoformat() == "2026-10-09"
    assert any(
        source.url == "https://www.motorfuelgroup.com/ev-power/" for source in config.sources
    )
