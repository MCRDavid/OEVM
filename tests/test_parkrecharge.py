"""ParkRecharge's reference data files, hosted by Hubeleon, are OCPI 2.2.1 responses read by
the ocpi_221 adapter past the host's expired certificate (no network)."""

from collections import Counter
from pathlib import Path

from adapters.http import PoliteClient, certificate_fingerprint
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.health import in_uk
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry

FIXTURES = Path(__file__).parent / "fixtures" / "parkrecharge"
FEED = "https://ocpi-pcpr.hubeleon.net/2.2.1/"
PREFIX = "parkrecharge:GB:HUB:"
TEST_SITES = {"3166": "UK-HBN-PAYTERTEST", "1183": "TR0047 Hubeleon Test Centre"}


def replay(config=None):
    config = config or load_registry()["parkrecharge"]
    transport = ReplayTransport(FIXTURES)
    with PoliteClient(config, transport=transport, sleep=lambda _s: None) as client:
        return fetch(config, client), transport


def test_each_file_is_read_in_one_request():
    result, transport = replay()
    assert transport.requested == [f"{FEED}reference", f"{FEED}referencetariffs"]
    assert result.complete


def test_recorded_locations_convert_faithfully():
    result, _ = replay()
    assert len(result.locations) == 8
    assert all(loc.id.startswith(PREFIX) for loc in result.locations)
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert set(statuses) == {"available", "charging", "unknown"}
    connectors = [c for loc in result.locations for e in loc.evses for c in e.connectors]
    assert {c.power_type for c in connectors} == {"ac_1_phase", "ac_3_phase", "dc"}
    assert {"IEC_62196_T2_COMBO", "CHADEMO"} <= {c.standard for c in connectors}


def test_an_invalid_location_date_is_unknown_and_the_evse_keeps_its_own():
    result, _ = replay()
    locations = {loc.id.removeprefix(PREFIX): loc for loc in result.locations}
    geberit = locations["610"]
    assert geberit.last_updated is None
    assert [(e.status, e.status_at.isoformat()) for e in geberit.evses] == [
        ("available", "2026-04-27T14:23:33+00:00")
    ]


def test_tariff_elements_sent_as_one_object_are_priced():
    result, _ = replay()
    shown = {t.id.removeprefix(PREFIX): describe_tariff(t) for t in result.tariffs}
    assert len(shown) == 8
    assert all(len(t.elements) == 1 for t in result.tariffs)
    assert (shown["460"].state, shown["460"].text) == ("priced", "26.4p per kWh including VAT")
    # Every price in this tariff is zero, so it is free as published.
    assert next(t for t in result.tariffs if t.id == PREFIX + "610").price_state == (
        "free_confirmed"
    )
    assert (shown["610"].state, shown["610"].text) == ("free", "Free")
    # Argentine pesos are never converted.
    assert (shown["3421"].state, shown["3421"].text) == ("unknown", "Price unknown")


def test_connectors_whose_tariff_is_missing_name_it_and_are_left_unpriced():
    result, _ = replay()
    found = {t.id for t in result.tariffs}
    missing = {
        loc.id.removeprefix(PREFIX)
        for loc in result.locations
        for e in loc.evses
        for c in e.connectors
        if not set(c.tariff_ids) <= found
    }
    assert missing == {"2645", "3802"}


def test_only_the_argentine_location_is_outside_the_uk():
    result, _ = replay()
    outside = [loc.id.removeprefix(PREFIX) for loc in result.locations if not in_uk(loc)]
    assert outside == ["3421"]


def test_the_test_sites_are_left_off_by_the_owners_decision():
    config = load_registry()["parkrecharge"]
    decision = config.excluded_locations
    assert decision.decided.isoformat() == "2026-10-11"
    assert {item.id: item.name for item in decision.locations} == TEST_SITES

    result, _ = replay(config)
    kept = {loc.id.removeprefix(PREFIX) for loc in result.locations}
    assert len(kept) == 8 and not kept & set(TEST_SITES)
    assert sorted(result.dropped_location_ids) == sorted(PREFIX + key for key in TEST_SITES)
    assert result.issues == [
        "connector power not calculated for power_type 'ac_1_phase'",
        "location '1183' not kept: left off under the decision recorded in the operator file",
        "location '3166' not kept: left off under the decision recorded in the operator file",
        "location last_updated '0000-00-00T00:00:00Z' is not a valid date and time; "
        "recorded as unknown (3 times)",
        "tariff elements is one object, not a list; read as a list of one (8 times)",
    ]

    # Without the decision, every location the feed marks for publishing is kept.
    result, _ = replay(config.model_copy(update={"excluded_locations": None}))
    assert set(TEST_SITES) <= {loc.id.removeprefix(PREFIX) for loc in result.locations}


def test_parkrecharge_records_its_source_terms_and_certificate_decision():
    config = load_registry()["parkrecharge"]
    assert config.adapter == "ocpi_221" and config.auth.method == "none"
    assert config.licence.checked.isoformat() == "2026-10-11"
    assert "terms and conditions" in config.licence.basis
    decision = config.expired_certificate
    assert decision.host == "ocpi-pcpr.hubeleon.net"
    assert decision.expired.isoformat() == "2026-10-07"
    assert decision.decided.isoformat() == "2026-10-11"
    assert len(decision.sha256) == len(certificate_fingerprint(b"")) == 95
    assert any(f.kind == "access" and "Go Daddy" in f.summary for f in config.findings)
