"""Clenergy EV's files are OCPI 2.2.1 records in a different wrapper, read by the ocpi_221
adapter with response_envelope set to data_list (no network)."""

from collections import Counter
from pathlib import Path

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.health import in_uk
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry

FIXTURES = Path(__file__).parent / "fixtures" / "clenergy_ev"
FEED = "https://api.clenergy.online/development/pcpr"


def replay():
    config = load_registry()["clenergy_ev"]
    transport = ReplayTransport(FIXTURES)
    with PoliteClient(config, transport=transport, sleep=lambda _s: None) as client:
        return fetch(config, client), transport


def test_each_file_is_read_in_one_request():
    result, transport = replay()
    assert transport.requested == [f"{FEED}/locations", f"{FEED}/tariffs"]
    assert result.complete
    assert result.issues == []


def test_the_plain_wrapper_is_an_opt_in_setting():
    config = load_registry()["clenergy_ev"]
    assert config.response_envelope == "data_list"
    others = [c for c in load_registry().values() if c.id != "clenergy_ev"]
    assert all(c.response_envelope == "ocpi" for c in others)
    assert any("status_code" in finding.summary for finding in config.findings)


def test_recorded_locations_convert_faithfully():
    result, _ = replay()
    assert len(result.locations) == 9
    assert all(loc.id.startswith("clenergy_ev:GB:CEV:") for loc in result.locations)
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert {"available", "charging", "out_of_order", "unknown"} <= set(statuses)
    power = {c.power_type for loc in result.locations for e in loc.evses for c in e.connectors}
    assert power == {"ac_1_phase", "ac_3_phase", "dc"}
    hours = {
        None if loc.opening_hours is None else loc.opening_hours.twenty_four_seven
        for loc in result.locations
    }
    assert hours == {None, True, False}


def test_locations_with_no_operator_show_the_publishing_operator():
    result, _ = replay()
    assert {loc.operator.name for loc in result.locations} == {"Clenergy EV"}


def test_tariffs_without_a_party_use_the_operator_files_party():
    result, _ = replay()
    assert all(tariff.id.startswith("clenergy_ev:GB:CEV:") for tariff in result.tariffs)
    referenced = {
        t for loc in result.locations for e in loc.evses for c in e.connectors for t in c.tariff_ids
    }
    assert referenced == {tariff.id for tariff in result.tariffs}


def test_coordinates_outside_the_uk_are_kept_as_published_and_left_off_the_map():
    # Green Isle 1 is in Dublin: inside the old latitude and longitude limits, not in the UK.
    result, _ = replay()
    outside = {loc.name for loc in result.locations if not in_uk(loc)}
    assert outside == {"MedCare0001", "UBI 98 Southwell Road (98)", "Green Isle 1"}
    swapped = next(loc for loc in result.locations if loc.name == "UBI 98 Southwell Road (98)")
    assert (swapped.coordinates.latitude, swapped.coordinates.longitude) == (-0.09703, 51.467819)


def test_prices_show_in_gbp_only_and_free_only_when_confirmed():
    result, _ = replay()
    shown = {tariff.currency: describe_tariff(tariff) for tariff in result.tariffs}
    assert shown["USD"].state == "unknown" and shown["USD"].text == "Price unknown"
    free = [t for t in result.tariffs if describe_tariff(t).text == "Free"]
    assert free
    assert all(t.currency == "GBP" and t.price_state == "free_confirmed" for t in free)
    gbp = [t for t in result.tariffs if t.currency == "GBP"]
    assert all(describe_tariff(t).state in ("priced", "free") for t in gbp)


def test_clenergy_records_its_terms_and_rate_limit_header():
    config = load_registry()["clenergy_ev"]
    assert config.enabled and config.licence.checked
    assert config.rate_limit.limits == []
    assert config.rate_limit.min_seconds_between_requests >= 60 / 6 + 1
    assert any("X-RateLimit-Limit" in finding.summary for finding in config.findings)
