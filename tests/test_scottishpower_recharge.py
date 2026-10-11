"""ScottishPower Recharge's open data files, hosted by Fuuse, are OCPI 2.2.1 responses read
by the ocpi_221 adapter (no network)."""

from collections import Counter
from pathlib import Path

from adapters.http import PoliteClient, operator_hosts
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.health import in_uk
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry

FIXTURES = Path(__file__).parent / "fixtures" / "scottishpower_recharge"
FEED = "https://api.fuuse.io/opendata/e11a667d-c56a-468f-b8d3-a50b41628292/"


def replay():
    config = load_registry()["scottishpower_recharge"]
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
    assert all(
        loc.id.startswith("scottishpower_recharge:unknown:unknown:") for loc in result.locations
    )
    assert all(in_uk(loc) for loc in result.locations)
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert {"available", "charging", "inoperative"} <= set(statuses)
    kinds = {(c.standard, c.power_type) for _loc, c in connectors(result)}
    assert {
        ("IEC_62196_T2", "ac_3_phase"),
        ("IEC_62196_T2_COMBO", "dc"),
        ("CHADEMO", "dc"),
    } <= kinds
    hours = {loc.opening_hours.twenty_four_seven for loc in result.locations}
    assert hours == {True, False}


def test_prices_given_as_strings_are_read_and_unlinked_connectors_are_unknown():
    result, _ = replay()
    tariffs = {tariff.alt_text: tariff for tariff in result.tariffs}
    assert len(tariffs) == 8
    assert all(tariff.currency == "GBP" for tariff in tariffs.values())
    shown = {name: describe_tariff(tariff) for name, tariff in tariffs.items()}
    assert "75p per kWh" in shown["Guest Rapid charging 051223"].text
    assert {s.state for name, s in shown.items() if name != "Harbour test"} == {"priced"}
    linked = [c for _loc, c in connectors(result) if c.tariff_ids]
    assert {t for c in linked for t in c.tariff_ids} <= {t.id for t in result.tariffs}
    assert len(connectors(result)) - len(linked) == 2


def test_the_zero_priced_tariff_is_shown_as_published():
    """Finding of 2026-10-11: every price zero, described as "Harbour test"."""
    result, _ = replay()
    zero = next(t for t in result.tariffs if t.alt_text == "Harbour test")
    assert zero.price_state == "free_confirmed"
    assert describe_tariff(zero).text == "Free"
    users = {loc.name for loc, c in connectors(result) if zero.id in c.tariff_ids}
    assert users == {"Glengarry"}


def test_a_type_2_cable_sent_as_dc_is_kept_as_published():
    result, _ = replay()
    odd = [
        loc.name
        for loc, c in connectors(result)
        if c.standard == "IEC_62196_T2" and c.power_type == "dc"
    ]
    assert odd == ["Storage Vault - Hamilton"]


def test_requests_to_the_shared_host_are_31_seconds_apart():
    """The host asked for 30 seconds with HTTP 429 after a 2 second gap (2026-10-11)."""
    registry = load_registry()
    on_host = [c for c in registry.values() if "api.fuuse.io" in operator_hosts(c)]
    assert {c.id for c in on_host} >= {"arnold_clark_charge", "scottishpower_recharge"}
    assert {c.rate_limit.min_seconds_between_requests for c in on_host} == {31}


def test_scottishpower_recharge_records_its_source_and_terms():
    config = load_registry()["scottishpower_recharge"]
    assert config.adapter == "ocpi_221" and config.auth.method == "none"
    assert config.licence.checked.isoformat() == "2026-10-11"
    assert "standing rule" in config.licence.basis
    assert any(
        source.url == "https://www.scottishpower.co.uk/blog/public-ev-charging"
        for source in config.sources
    )
