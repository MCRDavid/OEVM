"""Tests for the normalised data models (schema/models.py) and the exported JSON Schema."""

import json
from pathlib import Path

import pytest
from jsonschema import Draft202012Validator
from pydantic import ValidationError

from schema.export import ROOT, build_schemas, render
from schema.models import Location, Tariff

FIXTURES = Path(__file__).parent / "fixtures" / "normalised"
MODEL_FIXTURES = [(Location, "location.json"), (Tariff, "tariff.json")]
SCHEMA_FILES = {
    Location: ROOT / "schema" / "json" / "location.schema.json",
    Tariff: ROOT / "schema" / "json" / "tariff.schema.json",
}


def load(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


@pytest.fixture
def location_data() -> dict:
    return load("location.json")


@pytest.fixture
def tariff_data() -> dict:
    return load("tariff.json")


def set_all_prices(tariff: dict, price: float) -> dict:
    for element in tariff["elements"]:
        for component in element["price_components"]:
            component["price"] = price
    return tariff


# Round trips and the exported schema


@pytest.mark.parametrize(("model", "fixture"), MODEL_FIXTURES)
def test_fixture_round_trips_unchanged(model, fixture):
    data = load(fixture)
    parsed = model.model_validate(data)
    assert parsed.model_dump(mode="json") == data
    assert model.model_validate_json(parsed.model_dump_json()) == parsed


@pytest.mark.parametrize(("model", "fixture"), MODEL_FIXTURES)
def test_output_validates_against_committed_json_schema(model, fixture):
    schema = json.loads(SCHEMA_FILES[model].read_text(encoding="utf-8"))
    Draft202012Validator.check_schema(schema)
    output = model.model_validate(load(fixture)).model_dump(mode="json")
    Draft202012Validator(schema).validate(output)


def test_committed_json_schema_files_are_up_to_date():
    for path, schema in build_schemas().items():
        assert path.read_text(encoding="utf-8") == render(schema), (
            f"{path.relative_to(ROOT)} is out of date: run 'uv run python -m schema.export'"
        )


# Tariff price_state


def test_all_zero_components_are_free_confirmed(tariff_data):
    del tariff_data["price_state"]
    tariff = Tariff.model_validate(set_all_prices(tariff_data, 0))
    assert tariff.price_state == "free_confirmed"


def test_any_non_zero_component_is_priced(tariff_data):
    del tariff_data["price_state"]
    set_all_prices(tariff_data, 0)
    tariff_data["elements"][1]["price_components"][0]["price"] = 0.01
    assert Tariff.model_validate(tariff_data).price_state == "priced"


def test_tariff_without_components_is_unknown(tariff_data):
    del tariff_data["price_state"]
    tariff_data["elements"] = []
    assert Tariff.model_validate(tariff_data).price_state == "unknown"


def test_price_state_is_derived_when_omitted(tariff_data):
    del tariff_data["price_state"]
    assert Tariff.model_validate(tariff_data).price_state == "priced"


def test_claiming_free_for_a_priced_tariff_is_rejected(tariff_data):
    tariff_data["price_state"] = "free_confirmed"
    with pytest.raises(ValidationError, match="does not match the price components"):
        Tariff.model_validate(tariff_data)


def test_missing_vat_stays_missing_not_zero(tariff_data):
    tariff_data["elements"][1]["price_components"][0]["vat"] = None
    output = Tariff.model_validate(tariff_data).model_dump(mode="json")
    assert output["elements"][1]["price_components"][0]["vat"] is None


@pytest.mark.parametrize(
    "change",
    [
        lambda t: t["elements"][0].update(price_components=[]),
        lambda t: t["elements"][0]["price_components"][0].update(price=-0.1),
        lambda t: t["elements"][0]["price_components"][0].update(vat=120),
        lambda t: t["elements"][0]["price_components"][0].update(type="kwh"),
        lambda t: t["elements"][0]["restrictions"].update(start_time="7am"),
        lambda t: t.update(currency="gbp"),
        lambda t: t.update(id="other:GB:EXA:TARIFF-DC"),
        lambda t: t.update(unexpected_field=1),
    ],
    ids=[
        "empty-components",
        "negative-price",
        "vat-over-100",
        "unknown-component-type",
        "bad-time",
        "lower-case-currency",
        "id-not-matching-source",
        "unknown-field",
    ],
)
def test_invalid_tariffs_are_rejected(tariff_data, change):
    change(tariff_data)
    with pytest.raises(ValidationError):
        Tariff.model_validate(tariff_data)


# Location


def test_minimal_location_gets_unknown_defaults(location_data):
    minimal = {k: location_data[k] for k in ("id", "coordinates", "provenance")}
    location = Location.model_validate(minimal)
    assert location.access == "unknown"
    assert location.opening_hours is None
    assert location.evses == []
    assert location.address.street is None


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d["provenance"].update(fetched_at="2026-10-06T09:05:00"),
        lambda d: d["evses"][0].update(status_at="2026-10-06T09:00:00"),
        lambda d: d["coordinates"].update(latitude=91),
        lambda d: d["coordinates"].update(longitude=-181),
        lambda d: d.update(id="other:GB:EXA:LOC-001"),
        lambda d: d.update(id="example-LOC-001"),
        lambda d: d["evses"][1].update(uid="EVSE-1"),
        lambda d: d["evses"][0]["connectors"].append(dict(d["evses"][0]["connectors"][0])),
        lambda d: d["evses"][0].update(status_at=None),
        lambda d: d["opening_hours"].update(twenty_four_seven=True),
        lambda d: d["opening_hours"]["regular_hours"][0].update(weekday=8),
        lambda d: d.update(access="private"),
        lambda d: d["provenance"].update(confidence="certain"),
        lambda d: d["provenance"].update(source_url="example.invalid/ocpi"),
        lambda d: d["address"].update(country="GB"),
        lambda d: d.update(unexpected_field=1),
    ],
    ids=[
        "naive-fetched-at",
        "naive-status-at",
        "latitude-out-of-range",
        "longitude-out-of-range",
        "id-not-matching-source",
        "id-wrong-shape",
        "duplicate-evse-uid",
        "duplicate-connector-id",
        "status-without-time",
        "always-open-with-hours",
        "weekday-out-of-range",
        "unknown-access-value",
        "unknown-confidence",
        "url-without-scheme",
        "two-letter-country",
        "unknown-field",
    ],
)
def test_invalid_locations_are_rejected(location_data, change):
    change(location_data)
    with pytest.raises(ValidationError):
        Location.model_validate(location_data)


def test_timestamps_keep_their_offset(location_data):
    location_data["provenance"]["fetched_at"] = "2026-10-06T10:05:00+01:00"
    output = Location.model_validate(location_data).model_dump(mode="json")
    assert output["provenance"]["fetched_at"] == "2026-10-06T10:05:00+01:00"
