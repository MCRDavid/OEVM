"""An operator's own feed shown in place of copies of its locations in another operator's
feed (own_feed_over_copies, ADR 0027). No test touches the network."""

import json
from datetime import UTC, datetime

import pytest
from pydantic import ValidationError

from pipeline import publish, registry, run
from pipeline.registry import load_registry
from schema.operator import OperatorConfig

WHEN = datetime(2026, 10, 23, 12, 0, tzinfo=UTC)
COPY = "monta:GB:UFX:copy-1"
OTHER = "monta:GB:EXN:copy-2"


@pytest.fixture(scope="module")
def results():
    """The fixture run, with two made-up records added to Monta's: one under Urban Fox's
    party GB UFX and one under another party, both copies of a real Monta record."""
    found = run.run_fixtures(load_registry())
    monta = next(r for r in found if r.operator_id == "monta")
    template = monta.locations[0]
    monta.locations += [template.model_copy(update={"id": i}) for i in (COPY, OTHER)]
    return found


def published(results, out, operators=None, **kwargs):
    kwargs.setdefault("mode", "fixtures")
    return publish.publish(results, operators or load_registry(), out, generated_at=WHEN, **kwargs)


def ids_on_map(out) -> set[str]:
    layer = json.loads((out / "data" / "locations.geojson").read_text())
    return {f["properties"]["id"] for f in layer["features"]}


def test_copies_under_the_owners_party_are_left_off_while_its_own_feed_is_on_the_map(
    results, tmp_path
):
    out = published(results, tmp_path)
    on_map = ids_on_map(tmp_path)
    assert COPY not in on_map and OTHER in on_map
    assert any(i.startswith("urban_fox:GB:UFX:") for i in on_map)
    entry = out.manifest.operators["monta"]
    assert entry.replaced == 1 and entry.replaced_ids == [COPY]
    assert entry.replaced_by == {"urban_fox": 1}
    assert entry.mapped == sum(i.startswith("monta:") for i in on_map)
    key = publish.location_key(COPY)
    assert not (tmp_path / "data" / "loc" / key[:2] / f"{key}.json").exists()
    assert any("1 left off as copies of urban_fox's own feed" in line for line in out.report)
    assert out.manifest.operators["urban_fox"].replaced == 0


def test_copies_stay_when_the_owners_own_feed_has_nothing_on_the_map(results, tmp_path):
    without = [r for r in results if r.operator_id != "urban_fox"]
    out = published(without, tmp_path)
    assert COPY in ids_on_map(tmp_path)
    assert out.manifest.operators["monta"].replaced == 0


def test_copies_stay_without_the_owners_decision(results, tmp_path):
    operators = load_registry()
    operators["urban_fox"] = operators["urban_fox"].model_copy(
        update={"own_feed_over_copies": None}
    )
    published(results, tmp_path, operators)
    assert COPY in ids_on_map(tmp_path)


def test_the_owners_last_good_copy_also_replaces_the_copies(results, tmp_path):
    before = tmp_path / "before"
    published(results, before, mode="live")
    urban_fox = next(r for r in results if r.operator_id == "urban_fox")
    config = load_registry()["urban_fox"]
    kept, why = publish.last_good_copy(before, "urban_fox", config, urban_fox.fetched_at)
    assert kept is not None, why
    without = [r for r in results if r.operator_id != "urban_fox"]
    out = published(without, tmp_path / "after", mode="live", kept=[kept])
    assert COPY not in ids_on_map(tmp_path / "after")
    assert out.manifest.operators["monta"].replaced_by == {"urban_fox": 1}


def test_only_urban_fox_records_the_decision_and_it_names_monta():
    operators = load_registry()
    decided = {
        i: c.own_feed_over_copies.operators for i, c in operators.items() if c.own_feed_over_copies
    }
    assert decided == {"urban_fox": ["monta"]}
    assert str(operators["urban_fox"].own_feed_over_copies.decided) == "2026-10-23"


def _decision(**overrides) -> dict:
    data = {
        "decided": "2026-10-23",
        "basis": "The other feed carries this network's sites under its own party.",
        "evidence_url": "https://example.invalid/locations",
        "operators": ["other_operator"],
    }
    data.update(overrides)
    return data


def test_the_decision_needs_a_known_party_and_cannot_name_the_operator_itself():
    config = load_registry()["urban_fox"].model_dump(mode="json")
    OperatorConfig.model_validate(config | {"own_feed_over_copies": _decision()})
    for bad in (
        {"own_feed_over_copies": _decision(operators=["urban_fox"])},
        {"own_feed_over_copies": _decision(), "ocpi_party_id": "unknown"},
        {"own_feed_over_copies": _decision(operators=["monta", "monta"])},
        {"own_feed_over_copies": _decision(operators=["Not An Id"])},
    ):
        with pytest.raises(ValidationError):
            OperatorConfig.model_validate(config | bad)


def test_the_registry_rejects_a_decision_naming_an_unknown_operator():
    operators = load_registry()
    assert registry._copies_problems(operators) == []
    urban_fox = operators["urban_fox"]
    decision = urban_fox.own_feed_over_copies.model_copy(update={"operators": ["no_such_one"]})
    operators["urban_fox"] = urban_fox.model_copy(update={"own_feed_over_copies": decision})
    assert registry._copies_problems(operators) == [
        "urban_fox.yaml: own_feed_over_copies names unknown operator 'no_such_one'"
    ]
