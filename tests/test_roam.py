"""Roam's open data feed, OCPI 2.1.1 records read by adapters/roam.py (no network)."""

import json
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import pytest

from adapters import roam
from adapters.http import FeedError, PoliteClient
from adapters.ocpi_221.normalise import IssueLog
from adapters.replay import ReplayTransport
from pipeline import publish, run
from pipeline.geography import place_in_uk
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry
from schema.operator import OperatorConfig

FIXTURES = Path(__file__).parent / "fixtures" / "roam"
WHEN = datetime(2026, 10, 26, 19, 0, tzinfo=UTC)
PREFIX = "roam:GB:EVC:"
TYTHERINGTON = PREFIX + "0G2WrxDlQlXuRWbDBaRa"
NORWOOD_HALL = PREFIX + "2fDHay9pjCSytGLYz37F"
BOLEY_PARK = PREFIX + "bWbUNpOKSQHU9mUnCF23"
MARLIE = "DYmze49fRHgjNu18NOUV"


def config(**update) -> OperatorConfig:
    return load_registry()["roam"].model_copy(update=update)


def replay(cfg: OperatorConfig | None = None):
    sleeps: list[float] = []
    transport = ReplayTransport(FIXTURES)
    result = run.run_operator(cfg or config(), transport=transport, sleep=sleeps.append)
    return result, transport, sleeps


def connectors(result):
    return [c for loc in result.locations for e in loc.evses for c in e.connectors]


def recorded_locations() -> list[dict]:
    path = FIXTURES / "locations.json"
    return json.loads(path.read_text(encoding="utf-8"))["response"]["body"]["data"]


def test_each_module_is_read_in_one_request_twelve_minutes_apart():
    result, transport, sleeps = replay()
    assert transport.requested == [
        "https://data.evc.ninja/public/v1/data",
        "https://data.evc.ninja/public/v1/tariffs",
    ]
    assert result.complete and result.requests == 2
    assert result.modules["locations"].total_reported == 7
    assert result.modules["tariffs"].total_reported == 8
    # 5 requests an hour on the locations address: 720 s each, plus the 1 s margin.
    assert len(sleeps) == 1 and 720 < sleeps[0] <= 721


def test_recorded_locations_convert_with_roams_party_and_ocpi_221_names():
    result, _, _ = replay()
    assert len(result.locations) == 6
    assert all(location.id.startswith(PREFIX) for location in result.locations)
    assert {t.id for t in result.tariffs} == {
        PREFIX + i for i in [*(c["tariff_id"] for c in _raw_connectors()), "free_tariff"]
    }
    power = Counter((c.power_type, c.max_kw) for c in connectors(result))
    assert set(power) == {("ac_3_phase", 22.08), ("dc", 100.0), ("dc", 300.0)}
    # Each connector's one tariff_id becomes its tariff_ids, and every one is in the feed.
    tariffs = {t.id for t in result.tariffs}
    assert all(len(c.tariff_ids) == 1 and c.tariff_ids[0] in tariffs for c in connectors(result))
    statuses = Counter(e.status for loc in result.locations for e in loc.evses)
    assert set(statuses) == {"available", "charging", "out_of_order", "unknown"}
    (site,) = [loc for loc in result.locations if loc.id == TYTHERINGTON]
    assert site.operator.name == "Roam Charging" and site.address.country == "GBR"


def _raw_connectors() -> list[dict]:
    return [c for loc in recorded_locations() for e in loc["evses"] for c in e["connectors"]]


def test_locations_with_no_publish_flag_are_kept_only_under_the_owners_decision():
    """Finding of 2026-10-26: no location has a publish flag."""
    assert all("publish" not in loc for loc in recorded_locations())
    result, _, _ = replay()
    assert "kept under the decision recorded in the operator file (7 times)" in "\n".join(
        result.issues
    )
    result, _, _ = replay(config(missing_publish_flag=None))
    assert result.locations == []
    assert "location not kept: publish flag missing (7 times)" in result.issues


def test_an_evse_status_is_shown_as_sent_whatever_its_second_connector_says():
    """Finding of 2026-10-26: connectors carry statuses of their own, which are not used."""
    raw = {
        e["uid"]: e
        for loc in recorded_locations()
        if loc["id"] != MARLIE
        for e in loc["evses"]
        if len({c["status"] for c in e["connectors"]}) > 1
    }
    assert raw, "the fixture should hold an EVSE whose connectors differ"
    result, _, _ = replay()
    evses = {e.uid: e for loc in result.locations for e in loc.evses}
    for uid, evse in raw.items():
        assert evse["status"] == evse["connectors"][0]["status"]
        assert evses[uid].status == evse["status"].lower().replace("outoforder", "out_of_order")


def test_duplicate_connector_ids_leave_that_location_off():
    """Finding of 2026-10-26: some EVSEs give both connectors the id 1."""
    result, _, _ = replay()
    assert not any(loc.id.endswith(MARLIE) for loc in result.locations)
    assert PREFIX + MARLIE in result.dropped_location_ids
    assert any(
        line.startswith(f"location {MARLIE!r} skipped") and "duplicate connector ids" in line
        for line in result.issues
    )


def test_a_location_with_no_evses_is_shown_as_published():
    result, _, _ = replay()
    (site,) = [loc for loc in result.locations if loc.id == BOLEY_PARK]
    assert site.evses == []


def test_every_location_is_genuinely_in_the_uk():
    result, _, _ = replay()
    for location in result.locations:
        point = location.coordinates
        assert place_in_uk(point.latitude, point.longitude, location.address.postal_code)


def test_prices_show_with_vat_added_only_under_the_owners_decision():
    result, _, _ = replay()
    (tariff,) = [t for t in result.tariffs if t.id == PREFIX + "Rt3tiIkSSppod6Q1Exmw"]
    assert tariff.currency == "GBP"
    assert all(c.vat is None for e in tariff.elements for c in e.price_components)
    assert describe_tariff(tariff).text == "45p per kWh (excluding VAT, VAT not stated)"
    shown = describe_tariff(tariff, added_vat=config().vat_not_stated.add_percent)
    assert shown.state == "priced"
    assert shown.text.startswith("54p per kWh including VAT, with VAT at 20% added by this")


def test_the_free_tariff_is_free_only_because_every_price_is_zero():
    """Finding of 2026-10-26: a test charger names free_tariff, a flat fee of 0."""
    result, _, _ = replay()
    (free,) = [t for t in result.tariffs if t.price_state == "free_confirmed"]
    assert free.id == PREFIX + "free_tariff"
    assert describe_tariff(free).text == "Free"
    (site,) = [loc for loc in result.locations if loc.id == NORWOOD_HALL]
    on_free = [e for e in site.evses if any(free.id in c.tariff_ids for c in e.connectors)]
    assert [e.status for e in on_free] == ["unknown"]


def test_published_files_carry_the_attribution_and_prices_with_vat(tmp_path):
    operators = load_registry()
    result, _, _ = replay()
    publish.publish([result], operators, tmp_path, mode="fixtures", generated_at=WHEN)
    data = tmp_path / "data"
    statement = " ".join(operators["roam"].attribution.split())
    layer = json.loads((data / "locations.geojson").read_text(encoding="utf-8"))
    assert statement in layer["attribution"]
    assert len(layer["features"]) == 6
    (site,) = [f["properties"] for f in layer["features"] if f["properties"]["id"] == TYTHERINGTON]
    assert "VAT not stated" not in site["pt"]
    details = [json.loads(p.read_text(encoding="utf-8")) for p in (data / "loc").rglob("*.json")]
    texts = [o["text"] for d in details for o in d["tariff_options"] if o["state"] == "priced"]
    assert texts and all("added by this project" in text for text in texts)


def test_the_adapter_renames_only_what_is_missing():
    issues = IssueLog()
    sent = {"id": "1", "voltage": 230, "amperage": 32, "tariff_id": "abc"}
    assert roam._connector(sent, issues) == {
        **sent,
        "max_voltage": 230,
        "max_amperage": 32,
        "tariff_ids": ["abc"],
    }
    own = {"id": "1", "max_voltage": 400, "voltage": 230, "tariff_ids": ["x"], "tariff_id": "y"}
    assert roam._connector(own, issues) == own
    assert roam._connector({"id": "1", "tariff_id": 7}, issues)["tariff_ids"] == []
    assert roam._connector({"id": "1"}, issues)["tariff_ids"] == []
    assert issues.lines() == ["connector tariff_id 7 is not an id; not used"]
    assert roam._connector("not a connector", issues) == "not a connector"
    assert roam.ocpi_location({"id": "a", "evses": None}, issues) == {"id": "a", "evses": None}
    assert roam.ocpi_location(["a"], issues) == ["a"]


@pytest.mark.parametrize("option", ["date_from", "page_size"])
def test_the_feed_has_no_date_from_or_page_size(option):
    value = WHEN if option == "date_from" else 10
    cfg = config()
    client = PoliteClient(cfg, transport=ReplayTransport(FIXTURES), sleep=lambda _s: None)
    with client, pytest.raises(FeedError, match="no date_from or page size"):
        roam.fetch(cfg, client, **{option: value})


def test_roam_records_its_terms_decisions_and_rate_limit():
    cfg = config()
    assert cfg.adapter == "custom" and cfg.enabled
    assert run.CUSTOM_ADAPTERS["roam"] is roam.fetch
    assert (cfg.ocpi_country_code, cfg.ocpi_party_id) == ("GB", "EVC")
    assert cfg.auth.method == "none" and cfg.auth.secret_name is None
    assert cfg.licence.name == "OGL-3.0" and str(cfg.licence.checked) == "2026-10-26"
    (limit,) = cfg.rate_limit.limits
    assert (limit.requests, limit.per_seconds, limit.endpoint) == (5, 3600, "locations")
    assert limit.quote == "ratelimit-policy: 5;w=3600"
    assert cfg.rate_limit.min_seconds_between_requests == 721
    assert str(cfg.missing_publish_flag.decided) == "2026-10-26"
    assert str(cfg.vat_not_stated.decided) == "2026-10-26"
    assert cfg.vat_not_stated.add_percent == 20
    assert str(cfg.access_requested) == "2026-10-24"
    assert cfg.engagement.log[-2].action == "reply_received"
    assert cfg.engagement.log[-2].evidence_file == "evidence/roam/2026-10-26-reply-email.md"
