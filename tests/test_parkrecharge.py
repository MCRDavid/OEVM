"""ParkRecharge's reference data, hosted by Hubeleon, is a standard paged OCPI 2.2.1 feed
read by the ocpi_221 adapter (no network)."""

from collections import Counter
from pathlib import Path

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline.health import in_uk
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry

FIXTURES = Path(__file__).parent / "fixtures" / "parkrecharge"
FEED = "https://ocpi.hubeleon.net/ocpi/public/2.2.1/"
OLD_HOST = "ocpi-pcpr.hubeleon.net"
PREFIX = "parkrecharge:GB:HUB:"
TEST_SITES = {"3166": "PR06767 H19 Test Unit", "1183": "TR0047 Hubeleon Test Centre"}


def replay(config=None):
    config = config or load_registry()["parkrecharge"]
    transport = ReplayTransport(FIXTURES)
    with PoliteClient(config, transport=transport, sleep=lambda _s: None) as client:
        return fetch(config, client), transport


def test_the_feed_is_read_page_by_page_from_the_new_host():
    result, transport = replay()
    assert transport.requested == [
        f"{FEED}locations",
        f"{FEED}locations?offset=100",
        f"{FEED}tariffs",
    ]
    assert result.complete


def test_recorded_locations_convert_faithfully():
    result, _ = replay()
    assert len(result.locations) == 8
    assert all(loc.id.startswith(PREFIX) for loc in result.locations)
    assert all(in_uk(loc) for loc in result.locations)
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert set(statuses) == {"available", "charging", "inoperative", "out_of_order", "removed"}
    connectors = [c for loc in result.locations for e in loc.evses for c in e.connectors]
    assert {c.power_type for c in connectors} == {"ac_1_phase", "ac_3_phase", "dc"}
    assert {"IEC_62196_T2_COMBO", "CHADEMO"} <= {c.standard for c in connectors}
    assert all(c.max_kw for c in connectors)
    # Live availability is in the locations feed: each EVSE carries its own date.
    parklands = next(loc for loc in result.locations if loc.id == PREFIX + "3199")
    assert [(e.status, e.status_at.isoformat()) for e in parklands.evses] == [
        ("available", "2026-10-17T06:27:13+00:00"),
        ("available", "2026-10-17T06:27:13+00:00"),
    ]


def test_every_connector_is_priced_in_pounds():
    result, _ = replay()
    shown = {t.id.removeprefix(PREFIX): describe_tariff(t) for t in result.tariffs}
    assert len(shown) == 10
    assert all(t.currency == "GBP" for t in result.tariffs)
    assert (shown["465"].state, shown["465"].text) == ("priced", "26p per kWh including VAT")
    assert (shown["3166"].state, shown["3166"].text) == (
        "priced",
        "64p per kWh, plus £0.30 per session including VAT",
    )
    found = {t.id for t in result.tariffs}
    assert all(
        set(c.tariff_ids) <= found
        for loc in result.locations
        for e in loc.evses
        for c in e.connectors
    )


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
        "location '1183' not kept: left off under the decision recorded in the operator file",
        "location '3166' not kept: left off under the decision recorded in the operator file",
    ]

    # Without the decision, every location the feed marks for publishing is kept.
    result, _ = replay(config.model_copy(update={"excluded_locations": None}))
    assert set(TEST_SITES) <= {loc.id.removeprefix(PREFIX) for loc in result.locations}


def test_parkrecharge_records_its_source_terms_and_the_move_to_a_new_host():
    config = load_registry()["parkrecharge"]
    assert config.adapter == "ocpi_221" and config.auth.method == "none"
    assert config.licence.checked.isoformat() == "2026-10-17"
    assert "terms and conditions" in config.licence.basis
    assert {name: e.url for name, e in config.endpoints.items()} == {
        "locations": f"{FEED}locations",
        "tariffs": f"{FEED}tariffs",
    }
    # The old host is gone and the new one's certificate is in date, so the owner's
    # expired-certificate decision of 2026-10-11 (ADR 0021) is no longer needed.
    assert config.expired_certificate is None
    moved = [
        f for f in config.findings if f.kind == "access" and f.date.isoformat() == "2026-10-17"
    ]
    assert len(moved) == 1 and OLD_HOST in moved[0].summary
    assert all(f.status == "resolved" for f in config.findings if f.kind == "access")
    assert config.engagement.log[-1].date.isoformat() == "2026-10-17"
