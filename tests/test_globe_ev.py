"""Globe EV's files are on Clenergy's platform, in the same wrapper as Clenergy EV's, read by
the ocpi_221 adapter with response_envelope set to data_list (no network)."""

from collections import Counter
from pathlib import Path

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.health import in_uk
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry

FIXTURES = Path(__file__).parent / "fixtures" / "globe_ev"
FEED = "https://api.evdot.clenergy.online/development/pcpr"


def replay():
    config = load_registry()["globe_ev"]
    transport = ReplayTransport(FIXTURES)
    with PoliteClient(config, transport=transport, sleep=lambda _s: None) as client:
        return fetch(config, client), transport


def test_each_file_is_read_in_one_request():
    result, transport = replay()
    assert transport.requested == [f"{FEED}/locations", f"{FEED}/tariffs"]
    assert result.complete
    # Every location gives parking_type "UNKNOWN", which OCPI 2.2.1 does not have.
    assert result.issues == [
        "location parking_type 'UNKNOWN' is not an OCPI 2.2.1 value; recorded as unknown (6 times)"
    ]


def test_recorded_locations_convert_faithfully():
    result, _ = replay()
    assert len(result.locations) == 6
    assert all(loc.id.startswith("globe_ev:GB:CEV:") for loc in result.locations)
    assert all(in_uk(loc) for loc in result.locations)
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert {"available", "charging", "out_of_order", "unknown"} <= set(statuses)
    power = {c.power_type for loc in result.locations for e in loc.evses for c in e.connectors}
    assert power == {"ac_1_phase", "ac_3_phase", "dc"}
    assert all(loc.opening_hours.twenty_four_seven for loc in result.locations)


def test_locations_with_no_operator_show_the_publishing_operator():
    result, _ = replay()
    assert {loc.operator.name for loc in result.locations} == {"Globe EV"}


def test_tariffs_without_a_party_use_the_operator_files_party():
    result, _ = replay()
    assert all(tariff.id.startswith("globe_ev:GB:CEV:") for tariff in result.tariffs)
    referenced = {
        t for loc in result.locations for e in loc.evses for c in e.connectors for t in c.tariff_ids
    }
    assert referenced == {tariff.id for tariff in result.tariffs}


def test_prices_without_vat_have_the_owners_rate_added_and_say_so():
    # The owner's vat_not_stated decision of 2026-10-23 adds 20% where no rate is given.
    config = load_registry()["globe_ev"]
    assert config.vat_not_stated.add_percent == 20
    result, _ = replay()
    shown = [describe_tariff(tariff, added_vat=20) for tariff in result.tariffs]
    assert all(d.state == "priced" for d in shown)
    assert all("added by this project" in d.text for d in shown)
    assert any("per session" in d.text for d in shown)
    assert not any(d.text == "Free" for d in shown)
    as_published = [describe_tariff(tariff) for tariff in result.tariffs]
    assert all("excluding VAT, VAT not stated" in d.text for d in as_published)


def test_globe_ev_records_its_terms_and_rate_limit_header():
    config = load_registry()["globe_ev"]
    assert config.enabled and config.licence.checked
    assert config.response_envelope == "data_list"
    assert config.rate_limit.limits == []
    assert config.rate_limit.min_seconds_between_requests >= 60 / 6 + 1
    assert any("X-RateLimit-Limit" in finding.summary for finding in config.findings)
