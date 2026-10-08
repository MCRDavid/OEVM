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
    assert len(details) == len(layer["features"]) == 13
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
    assert set(manifest.operators) == {"chargy", "geniepoint", "jolt"}
    for operator_id, entry in manifest.operators.items():
        config = load_registry()[operator_id]
        assert entry.attribution == " ".join(config.attribution.split())
        assert entry.licence == "OGL-3.0"
    sizes = {f.path: f for f in manifest.files}
    assert sizes["data/locations.geojson"].bytes > sizes["data/locations.geojson"].gzip_bytes > 0
    assert sizes["data/loc/"].files == 13
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


def test_operators_that_are_switched_off_are_never_published(results, tmp_path):
    operators = load_registry()
    operators["jolt"] = operators["jolt"].model_copy(update={"enabled": False})
    with pytest.raises(publish.PublishError, match="jolt is not switched on"):
        published(results, tmp_path, operators)
    assert not (tmp_path / "data").exists()


def test_the_committed_site_folder_is_never_written(results):
    with pytest.raises(publish.PublishError, match="not the committed site/ folder"):
        published(results, ROOT / "site")


def _layer_and_details(results, tmp_path):
    published(results, tmp_path)
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
        kinds = {(c["std"], c["kw"], c["price"], c["ppk"]) for c in properties["cons"]}
        assert len(kinds) == len(properties["cons"]), "no repeats"
        assert {c["standard"] for c in connectors} == {c["std"] for c in properties["cons"]}
        assert {c["max_kw"] for c in connectors} == {c["kw"] for c in properties["cons"]}


def test_price_per_kwh_is_only_given_with_vat(results, tmp_path):
    by_operator = {}
    for properties, _ in _layer_and_details(results, tmp_path):
        by_operator.setdefault(properties["op"], set()).update(c["ppk"] for c in properties["cons"])
    assert by_operator["chargy"] == {None}  # char.gy states no VAT
    assert 49.2 in by_operator["jolt"]


def test_a_location_needs_a_price_for_each_connector(results):
    location = next(loc for result in results for loc in result.locations if loc.evses)
    with pytest.raises(publish.PublishError, match="a price for each connector"):
        publish.map_properties(location, [], "0" * 16)


def test_the_command_line_publishes_and_reports_sizes(tmp_path, capsys):
    assert run.main(["--fixtures", "--publish", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "data/locations.geojson: 1 file(s)" in out and "gzipped" in out
    assert run.FIXTURE_KEY not in (tmp_path / "data" / "locations.geojson").read_text()
