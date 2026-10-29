"""Tests for pipeline/publish.py (blueprint task 7). No test touches the network."""

import json
from datetime import UTC, datetime
from decimal import Decimal
from pathlib import Path

import jsonschema
import pytest

from pipeline import publish, run
from pipeline.registry import ROOT, load_registry
from pipeline.tariffs import ConnectorPrice
from schema.models import Coordinates

SCHEMAS = ROOT / "schema" / "json"
WHEN = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)


@pytest.fixture(scope="module")
def results():
    return run.run_fixtures(load_registry())


def published(results, out: Path, operators=None):
    return publish.publish(
        results, operators or load_registry(), out, mode="fixtures", generated_at=WHEN
    )


def schema(name: str) -> dict:
    return json.loads((SCHEMAS / f"{name}.schema.json").read_text(encoding="utf-8"))


def test_every_output_validates_against_its_exported_schema(results, tmp_path):
    published(results, tmp_path)
    data = tmp_path / "data"
    layer = json.loads((data / "locations.geojson").read_text())
    jsonschema.validate(layer, schema("map-layer"))
    jsonschema.validate(json.loads((data / "manifest.json").read_text()), schema("manifest"))
    details = sorted((data / "loc").glob("*/*.json"))
    assert len(details) == len(layer["features"]) == 183
    for path in details:
        jsonschema.validate(json.loads(path.read_text()), schema("location-detail"))


def test_each_point_links_to_its_detail_file(results, tmp_path):
    published(results, tmp_path)
    data = tmp_path / "data"
    for feature in json.loads((data / "locations.geojson").read_text())["features"]:
        key = feature["properties"]["key"]
        detail = json.loads((data / "loc" / key[:2] / f"{key}.json").read_text())
        assert detail["location"]["id"] == feature["properties"]["id"]
        lon, lat = feature["geometry"]["coordinates"]
        assert (lat, lon) == (
            round(detail["location"]["coordinates"]["latitude"], 6),
            round(detail["location"]["coordinates"]["longitude"], 6),
        )


def test_the_manifest_records_operators_attribution_and_sizes(results, tmp_path):
    out = published(results, tmp_path)
    manifest = out.manifest
    assert set(manifest.operators) == {
        "allego",
        "arnold_clark_charge",
        "blink_charging_uk",
        "bright_green",
        "chargeplace_scotland",
        "chargepoint",
        "chargy",
        "clenergy_ev",
        "connekt",
        "enfield_council",
        "esb_ecars",
        "esb_energy",
        "ev_point",
        "evolt",
        "evyve",
        "fastned",
        "geniepoint",
        "globe_ev",
        "ionity",
        "jolt",
        "lidl",
        "mer_uk",
        "mfg_ev_power",
        "monta",
        "parkrecharge",
        "plug_charging",
        "pod",
        "pogo_charge",
        "raw_charging",
        "roam",
        "scottishpower_recharge",
        "source_ev",
        "three_ti",
        "ubitricity",
        "urban_fox",
        "zest",
    }
    for operator_id, entry in manifest.operators.items():
        config = load_registry()[operator_id]
        assert entry.attribution == " ".join(config.attribution.split())
        assert entry.licence == ("CC-BY-4.0" if operator_id == "zest" else "OGL-3.0")
        assert entry.licence == config.licence.name
    sizes = {f.path: f for f in manifest.files}
    assert sizes["data/locations.geojson"].bytes > sizes["data/locations.geojson"].gzip_bytes > 0
    assert sizes["data/loc/"].files == 183
    assert any("gzipped" in line for line in out.report)


def test_publishing_is_repeatable(results, tmp_path):
    published(results, tmp_path / "a")
    published(results, tmp_path / "b")
    for name in ("locations.geojson", "manifest.json"):
        assert (tmp_path / "a" / "data" / name).read_bytes() == (
            tmp_path / "b" / "data" / name
        ).read_bytes()


def test_a_detail_file_never_outlives_its_location(results, tmp_path):
    published(results, tmp_path)
    stale = tmp_path / "data" / "loc" / "zz" / "zzzzzzzzzzzzzzzz.json"
    stale.parent.mkdir(parents=True)
    stale.write_text("{}")
    published(results, tmp_path)
    assert not stale.exists()


def test_coordinates_outside_the_uk_are_left_off_not_moved(results, tmp_path):
    jolt = next(r for r in results if r.operator_id == "jolt")
    moved = jolt.locations[0].model_copy(
        update={"coordinates": Coordinates(latitude=53.097591, longitude=2.444352)}
    )
    altered = [*(r for r in results if r.operator_id != "jolt")]
    altered.append(type(jolt)(**{**jolt.__dict__, "locations": [moved, *jolt.locations[1:]]}))
    out = published(altered, tmp_path)
    entry = out.manifest.operators["jolt"]
    assert (entry.mapped, entry.not_mapped, entry.not_mapped_ids) == (3, 1, [moved.id])
    ids = [
        f["properties"]["id"]
        for f in json.loads((tmp_path / "data" / "locations.geojson").read_text())["features"]
    ]
    assert moved.id not in ids


def _detail(out_dir: Path, location_id: str) -> dict:
    key = publish.location_key(location_id)
    return json.loads((out_dir / "data" / "loc" / key[:2] / f"{key}.json").read_text())


SMARTCHARGING = {"pogo_charge", "evolt", "chargeplace_scotland"}


def test_related_networks_are_priced_from_each_others_tariffs_by_exact_id(results, tmp_path):
    # PoGo Charge's connectors name tariffs only Evolt Network's feed holds, as do those at
    # ChargePlace Scotland's Dunipace site; Evolt Network's Granton site names one only
    # ChargePlace Scotland's holds. The owner decided each may be used (ADR 0020).
    out = published(results, tmp_path)
    related = {i: e.priced_from_related for i, e in out.manifest.operators.items()}
    assert related == {i: 0 for i in related} | {
        "pogo_charge": 13,
        "evolt": 2,
        "chargeplace_scotland": 2,
    }
    assert any("13 connectors priced from a related operator's tariffs" in x for x in out.report)
    cases = {
        "pogo_charge:GB:POG:156948": ("evolt", "Evolt Network", 2),
        "chargeplace_scotland:GB:CPS:450779": ("evolt", "Evolt Network", 1),
        "evolt:GB:SSM:11848487": ("chargeplace_scotland", "ChargePlace Scotland", 1),
    }
    for location_id, (source, name, count) in cases.items():
        detail = _detail(tmp_path, location_id)
        config = load_registry()[source]
        assert {p["state"] for p in detail["prices"]} == {"priced"}
        assert all(p["unresolved_ids"] == [] for p in detail["prices"])
        assert all(i.startswith(f"{source}:") for p in detail["prices"] for i in p["tariff_ids"])
        assert [o["published_by"] for o in detail["tariff_options"]] == [name] * count
        assert [t["provenance"]["source_id"] for t in detail["tariffs"]] == [source] * count
        (where,) = detail["tariff_sources"]
        assert where["name"] == name and where["licence"] == "OGL-3.0"
        assert where["attribution"] == " ".join(config.attribution.split())
        assert where["source_url"] == config.endpoints["tariffs"].url
        assert "never by name" in where["note"]
        # The location keeps its own operator's attribution.
        assert detail["attribution"] != where["attribution"]


def test_other_locations_keep_their_own_operators_tariffs(results, tmp_path):
    published(results, tmp_path)
    for path in (tmp_path / "data" / "loc").glob("*/*.json"):
        detail = json.loads(path.read_text())
        own = detail["location"]["provenance"]["source_id"]
        if detail["tariff_sources"]:
            assert own in SMARTCHARGING
            continue
        assert all(o["published_by"] is None for o in detail["tariff_options"])
        assert {t["provenance"]["source_id"] for t in detail["tariffs"]} <= {own}


def test_without_the_owners_decision_the_related_tariffs_are_not_used(results, tmp_path):
    operators = {
        i: c.model_copy(update={"tariffs_from": None}) if i in SMARTCHARGING else c
        for i, c in load_registry().items()
    }
    out = published(results, tmp_path, operators)
    assert all(e.priced_from_related == 0 for e in out.manifest.operators.values())
    detail = _detail(tmp_path, "pogo_charge:GB:POG:156948")
    assert {p["text"] for p in detail["prices"]} == {"Price unknown"}
    assert detail["tariff_sources"] == [] and detail["tariffs"] == []


def test_only_the_operators_named_in_the_decision_are_searched(results, tmp_path):
    # PoGo Charge's tariffs are all in Evolt Network's feed, which this decision does not
    # name, so nothing is matched even though Evolt Network is in the same run.
    operators = load_registry()
    decision = operators["pogo_charge"].tariffs_from
    named_other = decision.model_copy(update={"operators": ["chargeplace_scotland"]})
    operators["pogo_charge"] = operators["pogo_charge"].model_copy(
        update={"tariffs_from": named_other}
    )
    out = published(results, tmp_path, operators)
    assert out.manifest.operators["pogo_charge"].priced_from_related == 0
    detail = _detail(tmp_path, "pogo_charge:GB:POG:156948")
    assert {p["text"] for p in detail["prices"]} == {"Price unknown"}
    assert detail["tariff_sources"] == []


def test_a_related_operator_missing_from_the_run_leaves_the_price_unknown(results, tmp_path):
    # As when Evolt Network's fetch fails, or only PoGo Charge is fetched: a kept copy of
    # Evolt Network's map files holds no tariffs, so nothing is matched.
    out = published([r for r in results if r.operator_id != "evolt"], tmp_path)
    assert out.manifest.operators["pogo_charge"].priced_from_related == 0
    assert out.manifest.operators["chargeplace_scotland"].priced_from_related == 0
    detail = _detail(tmp_path, "chargeplace_scotland:GB:CPS:450779")
    assert {p["text"] for p in detail["prices"]} == {"Price unknown"}
    assert detail["tariff_sources"] == []


def test_a_missing_minus_sign_is_restored_by_the_owners_decision_for_evolt(results, tmp_path):
    # Evolt Network's Glasgow location has longitude 4.26275; the Isle of Man and Australia
    # ones stay off the map.
    out = published(results, tmp_path)
    entry = out.manifest.operators["evolt"]
    assert (entry.mapped, entry.not_mapped, entry.corrected) == (7, 2, 1)
    assert entry.corrected_ids == ["evolt:GB:SSM:1261778"]
    assert "evolt:GB:SSM:1261778" not in entry.not_mapped_ids
    key = publish.location_key("evolt:GB:SSM:1261778")
    detail = json.loads((tmp_path / "data" / "loc" / key[:2] / f"{key}.json").read_text())
    assert detail["location"]["coordinates"] == {"latitude": 55.86005, "longitude": -4.26275}
    assert detail["coordinates_corrected"]["published"] == {
        "latitude": 55.86005,
        "longitude": 4.26275,
    }


def test_obviously_swapped_coordinates_are_swapped_back_and_marked(results, tmp_path):
    out = published(results, tmp_path)
    entry = out.manifest.operators["clenergy_ev"]
    swapped_id = "clenergy_ev:GB:CEV:67dd63746bcfca846582fe3e"  # UBI 98 Southwell Road, SE5
    assert entry.corrected_ids == [swapped_id] and entry.corrected == 1
    assert swapped_id not in entry.not_mapped_ids
    assert entry.not_mapped == 2  # the St Lucia and Dublin locations stay off the map
    key = publish.location_key(swapped_id)
    detail = json.loads((tmp_path / "data" / "loc" / key[:2] / f"{key}.json").read_text())
    assert detail["location"]["coordinates"] == {"latitude": 51.467819, "longitude": -0.09703}
    assert detail["coordinates_corrected"]["published"] == {
        "latitude": -0.09703,
        "longitude": 51.467819,
    }
    assert "wrong way round" in detail["coordinates_corrected"]["note"]
    # Evolt Network's Glasgow location and BrightGreen's Kiln Farm Station, named by the owner,
    # are the only others corrected (a minus sign each).
    glasgow = publish.location_key("evolt:GB:SSM:1261778")
    kiln = publish.location_key(KILN_FARM)
    others = [
        p
        for p in (tmp_path / "data" / "loc").glob("*/*.json")
        if p.stem not in (key, glasgow, kiln)
    ]
    assert all(json.loads(p.read_text())["coordinates_corrected"] is None for p in others)
    assert any("1 with coordinates corrected" in line for line in out.report)


KILN_FARM = "bright_green:GB:unknown:4cbfa56a-07da-4cf1-90be-8277667b4158"


def test_a_minus_sign_is_added_only_to_a_location_the_owner_named(results, tmp_path):
    # Kiln Farm Station (MK11 3LW) is published at longitude .82, in Suffolk: inside the UK, so
    # only the owner's naming it in swapped_coordinates.sign_missing moves it (ADR 0013).
    out = published(results, tmp_path)
    entry = out.manifest.operators["bright_green"]
    assert entry.corrected_ids == [KILN_FARM]
    key = publish.location_key(KILN_FARM)
    detail = json.loads((tmp_path / "data" / "loc" / key[:2] / f"{key}.json").read_text())
    assert detail["location"]["coordinates"] == {"latitude": 52.04, "longitude": -0.82}
    assert detail["coordinates_corrected"]["published"] == {"latitude": 52.04, "longitude": 0.82}
    assert "away from the place its postcode names" in detail["coordinates_corrected"]["note"]
    bright_green = load_registry()["bright_green"]
    unnamed = bright_green.swapped_coordinates.model_copy(update={"sign_missing": []})
    operators = load_registry() | {
        "bright_green": bright_green.model_copy(update={"swapped_coordinates": unnamed})
    }
    again = published(results, tmp_path / "unnamed", operators)
    assert again.manifest.operators["bright_green"].corrected == 0
    assert again.manifest.operators["bright_green"].mapped == entry.mapped


def test_a_named_location_keeps_its_place_once_the_feed_sends_a_new_postcode(results):
    bright_green = next(r for r in results if r.operator_id == "bright_green")
    kiln = next(loc for loc in bright_green.locations if loc.id == KILN_FARM)
    config = load_registry()["bright_green"]
    assert publish.corrected_coordinates(kiln, config) is not None
    moved = kiln.model_copy(
        update={"address": kiln.address.model_copy(update={"postal_code": "IP14 1AA"})}
    )
    assert publish.corrected_coordinates(moved, config) is None


def _swapped_location(results, **address):
    clenergy = next(r for r in results if r.operator_id == "clenergy_ev")
    location = next(loc for loc in clenergy.locations if loc.name.startswith("UBI 98"))
    return location.model_copy(update={"address": location.address.model_copy(update=address)})


def test_swaps_need_the_owners_decision_a_uk_postcode_and_gbr(results):
    config = load_registry()["clenergy_ev"]
    assert publish.swapped_back(_swapped_location(results), config) is not None
    undecided = config.model_copy(update={"swapped_coordinates": None})
    assert publish.swapped_back(_swapped_location(results), undecided) is None
    irish = _swapped_location(results, postal_code="F91 TCN3")
    assert publish.swapped_back(irish, config) is None
    abroad = _swapped_location(results, country="IRL")
    assert publish.swapped_back(abroad, config) is None


def test_a_point_that_is_not_in_the_uk_either_way_is_not_moved(results):
    config = load_registry()["clenergy_ev"]
    location = _swapped_location(results)
    elsewhere = location.model_copy(
        update={"coordinates": Coordinates(latitude=14.0144, longitude=-61.0045)}
    )
    assert publish.swapped_back(elsewhere, config) is None


def _unsigned(results, latitude, longitude, **address):
    location = _swapped_location(results, **address)
    return location.model_copy(
        update={"coordinates": Coordinates(latitude=latitude, longitude=longitude)}
    )


def test_an_obviously_missing_minus_sign_is_restored_and_marked(results):
    config = load_registry()["clenergy_ev"]
    # GeniePoint's Crewe Civic and Clenergy EV's UoL MSCP 1 as published on 9 Oct 2026.
    for latitude, longitude, postcode in (
        (53.097591, 2.444352, "CW1 2JZ"),
        (53.804825, 1.551283, "N/A"),
    ):
        location = _unsigned(results, latitude, longitude, postal_code=postcode)
        assert publish.swapped_back(location, config) is None
        moved, correction = publish.corrected_coordinates(location, config)
        assert moved.coordinates.longitude == -longitude
        assert moved.coordinates.latitude == latitude
        assert correction.published == location.coordinates
        assert "without its minus sign" in correction.note
        assert str(longitude) in correction.note


def test_minus_signs_need_the_owners_decision_gbr_and_no_foreign_postcode(results):
    config = load_registry()["clenergy_ev"]
    crewe = (53.097591, 2.444352)
    undecided = config.model_copy(update={"swapped_coordinates": None})
    assert (
        publish.sign_restored(_unsigned(results, *crewe, postal_code="CW1 2JZ"), undecided) is None
    )
    assert publish.sign_restored(_unsigned(results, *crewe, country="IRL"), config) is None
    assert publish.sign_restored(_unsigned(results, *crewe, postal_code="F91 TCN3"), config) is None
    # Far out at sea either way, and a point already west of the meridian, stay as they are.
    assert publish.sign_restored(_unsigned(results, 54.5, 4.0), config) is None
    assert publish.sign_restored(_unsigned(results, 14.0144, -61.0045), config) is None


def test_operators_that_are_switched_off_are_never_published(results, tmp_path):
    operators = load_registry()
    operators["jolt"] = operators["jolt"].model_copy(update={"enabled": False})
    with pytest.raises(publish.PublishError, match="jolt is not switched on"):
        published(results, tmp_path, operators)
    assert not (tmp_path / "data").exists()


def test_the_committed_site_folder_is_never_written(results):
    with pytest.raises(publish.PublishError, match="not the committed site/ folder"):
        published(results, ROOT / "site")


def _layer_and_details(results, tmp_path, operators=None):
    published(results, tmp_path, operators)
    layer = json.loads((tmp_path / "data" / "locations.geojson").read_text())
    for feature in layer["features"]:
        key = feature["properties"]["key"]
        detail = json.loads((tmp_path / "data" / "loc" / key[:2] / f"{key}.json").read_text())
        yield feature["properties"], detail


def test_free_is_only_shown_when_every_connector_is_confirmed_free(results, tmp_path):
    for properties, detail in _layer_and_details(results, tmp_path):
        states = {p["state"] for p in detail["prices"]}
        assert (properties["price"] == "free") == (states == {"free_confirmed"})
        assert ("Free (confirmed)" in properties["pt"]) == (states == {"free_confirmed"})


def test_a_location_with_one_free_connector_is_not_called_free(results):
    location = next(
        loc
        for result in results
        for loc in result.locations
        if sum(len(e.connectors) for e in loc.evses) >= 2
    )
    connectors = [(e, c) for e in location.evses for c in e.connectors]
    prices = [
        ConnectorPrice(
            location_id=location.id,
            evse_uid=evse.uid,
            connector_id=c.id,
            state="free_confirmed" if i == 0 else "priced",
            text="",
            energy_low=None if i == 0 else Decimal("0.79"),
            energy_high=None if i == 0 else Decimal("0.79"),
            includes_vat=None if i == 0 else True,
        )
        for i, (evse, c) in enumerate(connectors)
    ]
    properties = publish.map_properties(location, prices, "0" * 16)
    assert properties.price == "priced"
    assert properties.pt == "Energy 79p per kWh including VAT; some connectors free (confirmed)"
    assert {c.price for c in properties.cons} == {"free", "priced"}
    assert all((c.price == "free") == (c.ppk is None) for c in properties.cons)


def test_each_kind_of_connector_is_listed_once_with_its_power_and_price(results, tmp_path):
    for properties, detail in _layer_and_details(results, tmp_path):
        connectors = [c for e in detail["location"]["evses"] for c in e["connectors"]]
        kinds = {(c["std"], c["kw"], c["price"], c["ppk"], c["out"]) for c in properties["cons"]}
        assert len(kinds) == len(properties["cons"]), "no repeats"
        assert {c["standard"] for c in connectors} == {c["std"] for c in properties["cons"]}
        assert {c["max_kw"] for c in connectors} == {c["kw"] for c in properties["cons"]}


def test_connectors_alike_but_for_their_lowest_price_are_both_listed(results):
    location = next(
        loc
        for result in results
        for loc in result.locations
        if sum(len(e.connectors) for e in loc.evses) >= 2
    ).model_copy(deep=True)
    connectors = [(e, c) for e in location.evses for c in e.connectors]
    for _, c in connectors:  # the same kind of connector everywhere
        c.standard, c.max_kw = "IEC_62196_T2_COMBO", 50.0
    prices = [
        ConnectorPrice(
            location_id=location.id,
            evse_uid=evse.uid,
            connector_id=c.id,
            state="priced",
            text="",
            energy_low=Decimal("0.924"),
            energy_high=Decimal("0.924"),
            includes_vat=True,
            # Only the first also lists the operator's cheaper app tariff.
            lowest=Decimal("0.828") if i == 0 else Decimal("0.924"),
            lowest_vat=True,
        )
        for i, (evse, c) in enumerate(connectors)
    ]
    properties = publish.map_properties(location, prices, "0" * 16)
    assert sorted(c.lt for c in properties.cons) == ["82.8p", "92.4p"]


def test_connectors_reported_out_of_service_are_marked(results, tmp_path):
    seen = set()
    for properties, detail in _layer_and_details(results, tmp_path):
        for evse in detail["location"]["evses"]:
            for c in evse["connectors"]:
                out = evse["status"] in publish.OUT_OF_SERVICE
                assert any(
                    s["std"] == c["standard"] and s["kw"] == c["max_kw"] and s["out"] == out
                    for s in properties["cons"]
                )
                seen.add(out)
    assert seen == {True, False}  # the fixtures hold both
    assert "blocked" not in publish.OUT_OF_SERVICE and "unknown" not in publish.OUT_OF_SERVICE


def _ppk_by_operator(results, tmp_path, operators=None):
    by_operator = {}
    for properties, _ in _layer_and_details(results, tmp_path, operators):
        by_operator.setdefault(properties["op"], set()).update(c["ppk"] for c in properties["cons"])
    return by_operator


def test_price_per_kwh_is_only_given_with_vat(results, tmp_path):
    by_operator = _ppk_by_operator(results, tmp_path)
    # char.gy's feed states no VAT; the owner decided to add 20% (vat_not_stated).
    assert by_operator["chargy"] == {59.0}
    assert 49.2 in by_operator["jolt"]
    # BrightGreen states VAT at 20%, read as already in its prices by the owner's decision.
    assert 59.0 in by_operator["bright_green"] and 70.8 not in by_operator["bright_green"]


def test_without_the_in_price_decision_stated_vat_is_added(results, tmp_path):
    operators = load_registry()
    operators["bright_green"] = operators["bright_green"].model_copy(update={"vat_in_price": None})
    by_operator = _ppk_by_operator(results, tmp_path, operators)
    assert 70.8 in by_operator["bright_green"] and 59.0 not in by_operator["bright_green"]


def test_without_the_vat_decision_a_price_with_no_vat_has_no_price_per_kwh(results, tmp_path):
    operators = load_registry()
    operators["chargy"] = operators["chargy"].model_copy(update={"vat_not_stated": None})
    assert _ppk_by_operator(results, tmp_path, operators)["chargy"] == {None}


def test_vat_is_added_only_where_the_owner_decided_and_the_tariffs_stay_as_published(
    results, tmp_path
):
    decided = {i for i, c in load_registry().items() if c.vat_not_stated}
    assert decided == {
        "allego",
        "blink_charging_uk",
        "chargy",
        "clenergy_ev",
        "ev_point",
        "globe_ev",
        "lidl",
        "raw_charging",
        "roam",
    }
    for properties, detail in _layer_and_details(results, tmp_path):
        texts = [o["text"] for o in detail["tariff_options"] if o["state"] == "priced"]
        added = [t for t in texts if "added by this project" in t]
        assert bool(added) == (properties["op"] in decided and bool(texts))
        if properties["op"] in decided:
            assert "VAT not stated" not in properties["pt"]
            for tariff in detail["tariffs"]:
                assert all(
                    c["vat"] is None for e in tariff["elements"] for c in e["price_components"]
                )


def test_a_location_needs_a_price_for_each_connector(results):
    location = next(loc for result in results for loc in result.locations if loc.evses)
    with pytest.raises(publish.PublishError, match="a price for each connector"):
        publish.map_properties(location, [], "0" * 16)


def test_the_command_line_publishes_and_reports_sizes(tmp_path, capsys):
    assert run.main(["--fixtures", "--publish", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "data/locations.geojson: 1 file(s)" in out and "gzipped" in out
    assert run.FIXTURE_KEY not in (tmp_path / "data" / "locations.geojson").read_text()


def _named_as(tariff_id: str, named: list[str]) -> str:
    """The id a connector names for a tariff found in a related operator's feed: the one
    with the same OCPI id (after "<operator>:<country>:<party>:")."""
    (match,) = [i for i in named if i.split(":", 3)[3] == tariff_id.split(":", 3)[3]]
    return match


def test_details_list_every_tariff_the_connectors_refer_to(results, tmp_path):
    for _, detail in _layer_and_details(results, tmp_path):
        connectors = [c for e in detail["location"]["evses"] for c in e["connectors"]]
        listed = list(dict.fromkeys(i for c in connectors for i in c["tariff_ids"]))
        shown = [
            o["tariff_id"] if o["published_by"] is None else _named_as(o["tariff_id"], listed)
            for o in detail["tariff_options"]
        ]
        assert sorted(shown) == sorted(listed)
        found = {t["id"] for t in detail["tariffs"]}
        for option in detail["tariff_options"]:
            reason = option["reason"] or ""
            missing = "could not be read from the operator's tariff data" in reason
            assert (option["tariff_id"] in found) != missing


def test_a_location_named_private_is_marked_with_its_words_and_counted(results, tmp_path):
    # Evolt Network's "Arthur House - Private Use Only" (ADR 0023). The map hides it unless
    # the visitor asks; its detail file is published unchanged.
    out = published(results, tmp_path)
    layer = json.loads((tmp_path / "data" / "locations.geojson").read_text())
    marked = {f["properties"]["name"]: f["properties"]["priv"] for f in layer["features"]}
    assert {name: words for name, words in marked.items() if words} == {
        "Arthur House - Private Use Only": "Private Use Only"
    }
    hidden = {op: e.private for op, e in out.manifest.operators.items() if e.private}
    assert hidden == {"evolt": 1, "pogo_charge": 1}
    assert any(
        "evolt: 7 locations mapped" in line and "1 private or taxis only" in line
        for line in out.report
    )
    detail = _detail(tmp_path, "evolt:GB:SSM:12343565")
    assert [e["physical_reference"] for e in detail["location"]["evses"]] == [
        "SEC31617",
        "SEC31615",
        "SEC31616",
        "SEC31618",
        "SEC31620",
        "SEC31619",
    ]


def test_taxi_only_locations_are_flagged_by_the_owners_decision(results, tmp_path):
    # PoGo Charge's "Swales Central Avenue": every EVSE is TAXI_ONLY, read as taxis only by
    # the decision in operators/pogo_charge.yaml (ADR 0023).
    published(results, tmp_path)
    layer = json.loads((tmp_path / "data" / "locations.geojson").read_text())
    taxis = [f["properties"]["name"] for f in layer["features"] if f["properties"]["taxi"]]
    assert taxis == ["Swales Central Avenue"]
    detail = _detail(tmp_path, "pogo_charge:GB:POG:957309")
    assert {tuple(e["parking_restrictions"]) for e in detail["location"]["evses"]} == {
        ("taxis_only",)
    }


def test_each_kind_of_connector_carries_its_map_label(results, tmp_path):
    labels = {}
    for properties, detail in _layer_and_details(results, tmp_path):
        for summary in properties["cons"]:
            labels[(properties["name"], summary["kw"])] = summary["lt"]
            # Free only from the price state; a lowest price always says its VAT basis.
            assert (summary["lt"] == "Free") == (summary["price"] == "free")
            assert (summary["lvat"] is None) == (summary["low"] is None)
            assert (summary["lvar"] is None) == (summary["low"] is None)
            if summary["low"] is not None and summary["lt"] != "Free":
                assert summary["lt"].endswith("excl. VAT") != summary["lvat"]
                assert summary["lt"].startswith("from ") == summary["lvar"]
        lows = [s["low"] for s in properties["cons"] if s["low"] is not None]
        listed = [
            o["ppk_low"]
            for o in detail["tariff_options"]
            if o["state"] == "priced" and o["ppk_low"]
        ]
        if lows:
            assert min(lows) >= min(listed), "the label never undercuts the listed tariffs"
    # GeniePoint's app price, not only its contactless price (pay at the charger: 92.4p).
    assert labels[("Premier Inn Dumbarton/ Loch Lomond", 60.0)] == "82.8p"
    assert labels[("Premier Inn Alnwick", 7.0)] == "57.6p"
    # char.gy's weekday night price, with VAT at 20% added (vat_not_stated): 32.5p in the feed.
    assert labels[("141 - 143 Seaford Road", 5.06)] == "from 39p"
    assert labels[("Atlantic Quay", 22.0)] == "Free"
    # ScottishPower's all-zero test tariff is withheld (ADR 0022), so it gives no label.
    assert labels[("Glengarry", 30.0)] is None
