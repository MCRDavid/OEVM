"""Enfield Council's open data files, hosted by Fuuse, are OCPI 2.2.1 responses read by the
ocpi_221 adapter (no network)."""

from collections import Counter
from pathlib import Path

from adapters.http import PoliteClient, operator_hosts
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.health import in_uk
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry

FIXTURES = Path(__file__).parent / "fixtures" / "enfield_council"
FEED = "https://api.fuuse.io/opendata/d73a73f9-d063-456c-9f25-b51765e5747f/"
PAGE = "https://www.enfield.gov.uk/services/roads-and-transport/electric-vehicle-charging"


def replay():
    config = load_registry()["enfield_council"]
    transport = ReplayTransport(FIXTURES)
    with PoliteClient(config, transport=transport, sleep=lambda _s: None) as client:
        return fetch(config, client), transport


def connectors(result):
    return [
        (loc, connector)
        for loc in result.locations
        for evse in loc.evses
        for connector in evse.connectors
    ]


def test_each_file_is_read_in_one_request():
    result, transport = replay()
    assert transport.requested == [f"{FEED}location", f"{FEED}tariff"]
    assert result.complete
    assert result.modules["locations"].total_reported == 7
    assert result.issues == []


def test_recorded_locations_convert_faithfully():
    result, _ = replay()
    assert len(result.locations) == 7
    # The records carry no country_code or party_id, so the ids say unknown.
    assert all(loc.id.startswith("enfield_council:unknown:unknown:") for loc in result.locations)
    assert all(in_uk(loc) for loc in result.locations)
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert statuses == {"available": 17, "charging": 5, "inoperative": 10}
    kinds = Counter((c.standard, c.power_type, c.max_kw) for _loc, c in connectors(result))
    assert kinds == {
        ("IEC_62196_T2", "ac_1_phase", 7.36): 23,
        ("IEC_62196_T2", "ac_1_phase", 7.0): 9,
    }
    assert all(loc.opening_hours.twenty_four_seven for loc in result.locations)


def test_prices_given_as_strings_are_read_and_include_vat():
    """Finding of 2026-10-23: prices, VAT and minimum kWh are sent as strings."""
    result, _ = replay()
    (tariff,) = result.tariffs
    assert tariff.alt_text == "London Borough of Enfield - Public Tariff DAY"
    assert tariff.currency == "GBP"
    shown = describe_tariff(tariff)
    assert shown.state == "priced"
    assert shown.text.startswith("53p per kWh") and shown.text.endswith("including VAT")


def test_connectors_that_name_no_tariff_stay_price_unknown():
    """Finding of 2026-10-23: only the 2 connectors at Palace Gardens name the tariff."""
    result, _ = replay()
    (tariff,) = result.tariffs
    linked = {loc.name for loc, c in connectors(result) if c.tariff_ids}
    assert linked == {"Palace Gardens - Multi-storey"}
    assert all(c.tariff_ids == [tariff.id] for _loc, c in connectors(result) if c.tariff_ids)
    assert sum(1 for _loc, c in connectors(result) if not c.tariff_ids) == 30


def test_requests_to_the_shared_host_are_31_seconds_apart():
    registry = load_registry()
    assert operator_hosts(registry["enfield_council"]) == {"api.fuuse.io"}
    on_host = [c for c in registry.values() if operator_hosts(c) == {"api.fuuse.io"}]
    assert {c.rate_limit.min_seconds_between_requests for c in on_host} == {31}


def test_enfield_council_records_its_source_and_terms():
    config = load_registry()["enfield_council"]
    assert config.adapter == "ocpi_221" and config.auth.method == "none"
    assert config.enabled
    assert config.licence.checked.isoformat() == "2026-10-23"
    assert "standing rule" in config.licence.basis
    assert {name: e.url for name, e in config.endpoints.items()} == {
        "locations": f"{FEED}location",
        "tariffs": f"{FEED}tariff",
    }
    assert any(source.url == PAGE for source in config.sources)
    assert config.engagement.log[-1].date.isoformat() == "2026-10-23"
