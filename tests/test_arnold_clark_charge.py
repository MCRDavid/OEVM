"""Arnold Clark Charge's open access files, hosted by Fuuse, are OCPI 2.2.1 responses read
by the ocpi_221 adapter (no network)."""

from collections import Counter
from pathlib import Path

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.health import in_uk
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry

FIXTURES = Path(__file__).parent / "fixtures" / "arnold_clark_charge"
FEED = "https://api.fuuse.io/opendata/e6397b95-1624-49cd-824d-ab2f9dfe7294"


def replay():
    config = load_registry()["arnold_clark_charge"]
    transport = ReplayTransport(FIXTURES)
    with PoliteClient(config, transport=transport, sleep=lambda _s: None) as client:
        return fetch(config, client), transport


def test_each_file_is_read_in_one_request():
    result, transport = replay()
    assert transport.requested == [f"{FEED}/location", f"{FEED}/tariff"]
    assert result.complete
    assert result.modules["locations"].total_reported == 5
    assert result.issues == []


def test_recorded_locations_convert_faithfully():
    result, _ = replay()
    assert len(result.locations) == 5
    # The records carry no country_code or party_id, so the ids say unknown.
    assert all(
        loc.id.startswith("arnold_clark_charge:unknown:unknown:") for loc in result.locations
    )
    assert all(in_uk(loc) for loc in result.locations)
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert {"available", "charging", "out_of_order"} <= set(statuses)
    power = {c.power_type for loc in result.locations for e in loc.evses for c in e.connectors}
    assert power == {"dc"}
    hours = {loc.opening_hours.twenty_four_seven for loc in result.locations}
    assert hours == {True, False}


def test_prices_given_as_strings_are_read_and_unlinked_connectors_are_unknown():
    result, _ = replay()
    tariffs = {tariff.id: tariff for tariff in result.tariffs}
    assert len(tariffs) == 2
    for tariff in tariffs.values():
        shown = describe_tariff(tariff)
        assert shown.state == "priced" and "55p per kWh" in shown.text
    connectors = [c for loc in result.locations for e in loc.evses for c in e.connectors]
    linked = [c for c in connectors if c.tariff_ids]
    assert {t for c in linked for t in c.tariff_ids} == set(tariffs)
    assert len(linked) == 2 < len(connectors)


def test_arnold_clark_charge_records_its_source_and_terms():
    config = load_registry()["arnold_clark_charge"]
    assert config.adapter == "ocpi_221" and config.auth.method == "none"
    assert config.licence.checked.isoformat() == "2026-10-10"
    assert "terms of use" in config.licence.basis
    assert any(source.url == "https://www.arnoldclark.com/charge" for source in config.sources)
