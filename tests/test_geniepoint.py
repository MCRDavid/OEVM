"""GeniePoint's open data files are OCPI 2.2.1, read by the ocpi_221 adapter (no network)."""

from collections import Counter
from pathlib import Path

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry

FIXTURES = Path(__file__).parent / "fixtures" / "geniepoint"


def replay():
    config = load_registry()["geniepoint"]
    transport = ReplayTransport(FIXTURES)
    with PoliteClient(config, transport=transport, sleep=lambda _s: None) as client:
        return fetch(config, client), transport


def test_each_file_is_read_in_one_request():
    result, transport = replay()
    assert transport.requested == [
        "https://opendata.geniepoint.co.uk/locations",
        "https://opendata.geniepoint.co.uk/tariffs",
    ]
    assert result.complete
    assert result.modules["locations"].total_reported == 5


def test_recorded_locations_convert_faithfully():
    result, _ = replay()
    assert len(result.locations) == 5
    assert all(location.id.startswith("geniepoint:GB:GPT:") for location in result.locations)
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert {"available", "charging", "blocked", "inoperative", "out_of_order", "unknown"} <= set(
        statuses
    )
    power = {c.power_type for loc in result.locations for e in loc.evses for c in e.connectors}
    assert power == {"ac_1_phase", "ac_3_phase", "dc"}
    hours = {
        None if loc.opening_hours is None else loc.opening_hours.twenty_four_seven
        for loc in result.locations
    }
    assert hours == {None, True, False}


def test_repeated_tariffs_are_kept_once_and_logged():
    result, _ = replay()
    assert len(result.tariffs) == 11  # 12 records, one repeated
    assert result.issues == ["duplicate tariff record; kept the last copy"]
    referenced = {
        t for loc in result.locations for e in loc.evses for c in e.connectors for t in c.tariff_ids
    }
    assert referenced <= {tariff.id for tariff in result.tariffs}


def test_prices_show_in_pounds_and_pence_including_vat():
    result, _ = replay()
    for tariff in result.tariffs:
        shown = describe_tariff(tariff)
        assert shown.state in ("priced", "free_confirmed")
        assert "including VAT" in shown.text or shown.text == "Free"


def test_geniepoint_stays_off_until_its_terms_of_use_are_read():
    config = load_registry()["geniepoint"]
    assert config.adapter == "ocpi_221" and not config.enabled
    assert "terms of use" in config.licence.basis
