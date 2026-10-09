"""Tests for charging plan providers (schema/provider.py, pipeline/plans.py) and the
plan list the map loads (data/plans.json)."""

import copy
import datetime as dt
import json
from decimal import Decimal
from pathlib import Path

import pytest
import yaml
from pydantic import ValidationError

from pipeline import publish, run
from pipeline.plans import PROVIDERS_DIR, ProvidersError, load_providers
from pipeline.pricing import plan_fee_text, plan_price_text
from pipeline.registry import load_registry
from schema.provider import ProviderFile
from schema.published import PlansFile

WHEN = dt.datetime(2026, 10, 9, 4, 17, tzinfo=dt.UTC)
TEMPLATE = yaml.safe_load((PROVIDERS_DIR / "_template.yaml").read_text())


def provider(**changes) -> dict:
    data = copy.deepcopy(TEMPLATE)
    plan = changes.pop("plan", {})
    data["plans"][0].update(plan)
    data.update(changes)
    return data


def test_the_template_is_valid():
    ProviderFile.model_validate(TEMPLATE)


def test_plans_are_refused_when_the_terms_forbid_reuse():
    data = provider()
    data["terms"].update(reuse="forbidden", quote="You may not copy any content.")
    with pytest.raises(ValidationError, match="only be listed when the provider's terms"):
        ProviderFile.model_validate(data)
    data["plans"] = []
    ProviderFile.model_validate(data)


@pytest.mark.parametrize("reuse", ["forbidden", "personal_use_only"])
def test_a_restriction_needs_the_providers_own_words(reuse):
    data = provider(plans=[])
    data["terms"].update(reuse=reuse, quote=None)
    with pytest.raises(ValidationError, match="provider's own words"):
        ProviderFile.model_validate(data)


def test_attribution_needs_its_wording():
    data = provider()
    data["terms"].update(reuse="attribution", attribution=None)
    with pytest.raises(ValidationError, match="attribution wording"):
        ProviderFile.model_validate(data)


def test_a_plan_source_must_be_on_the_providers_own_site():
    data = provider(
        plan={"source": {**TEMPLATE["plans"][0]["source"], "url": "https://blog.example.org/x"}}
    )
    with pytest.raises(ValidationError, match="provider's own site"):
        ProviderFile.model_validate(data)
    sub = provider(
        plan={"source": {**TEMPLATE["plans"][0]["source"], "url": "https://help.example.com/x"}}
    )
    ProviderFile.model_validate(sub)


def test_a_plan_is_a_fixed_price_or_a_discount_never_both():
    with pytest.raises(ValidationError, match="not both"):
        ProviderFile.model_validate(provider(plan={"price_per_kwh": 0.39}))
    with pytest.raises(ValidationError, match="needs discount_of"):
        ProviderFile.model_validate(provider(plan={"discount_of": None}))
    fixed = provider(plan={"price_per_kwh": 0.39, "discount_percent": None, "discount_of": None})
    ProviderFile.model_validate(fixed)


def test_operator_ids_must_have_a_registry_file(tmp_path: Path):
    data = provider(plan={"operator_ids": ["nowhere"]})
    (tmp_path / "example.yaml").write_text(yaml.safe_dump(data))
    with pytest.raises(ProvidersError, match="names operator 'nowhere'"):
        load_providers(tmp_path, operator_ids={"jolt"})
    data["plans"][0]["operator_ids"] = ["jolt"]
    (tmp_path / "example.yaml").write_text(yaml.safe_dump(data))
    assert list(load_providers(tmp_path, operator_ids={"jolt"})) == ["example"]


def test_the_file_name_must_match_the_id(tmp_path: Path):
    (tmp_path / "other.yaml").write_text(yaml.safe_dump(provider()))
    with pytest.raises(ProvidersError, match="must match the file name"):
        load_providers(tmp_path, operator_ids=set())


def test_every_committed_provider_file_is_valid():
    providers = load_providers()
    assert providers, "no provider files found"
    for item in providers.values():
        if item.terms.reuse in ("forbidden", "personal_use_only"):
            assert not item.plans


def test_plan_wording_never_turns_a_discount_into_a_price():
    assert plan_fee_text(None) == "Monthly fee not published"
    assert plan_fee_text(Decimal("0")) == "No monthly fee"
    assert plan_fee_text(Decimal("8.99")) == "£8.99 a month"
    assert plan_price_text(Decimal("0.39"), None, None, True) == "39p per kWh including VAT"
    assert plan_price_text(Decimal("0.39"), None, None, False) == "39p per kWh excluding VAT"
    assert plan_price_text(Decimal("0.59"), None, None, None) == "59p per kWh (VAT not stated)"
    assert (
        plan_price_text(None, Decimal("25"), "Electroverse's own price", None)
        == "25% off Electroverse's own price"
    )
    assert plan_price_text(None, None, None, None) == "Price per kWh not published"


def test_the_published_plan_list_matches_the_provider_files(tmp_path: Path):
    operators = load_registry()
    publish.publish(
        run.run_fixtures(operators), operators, tmp_path, mode="fixtures", generated_at=WHEN
    )
    blob = (tmp_path / "data" / "plans.json").read_bytes()
    plans = PlansFile.model_validate_json(blob).plans
    listed = {f"{p.id}.{plan.id}" for p in load_providers().values() for plan in p.plans}
    assert {plan.id for plan in plans} == listed
    for plan in plans:
        assert plan.ppk is None or plan.discount_percent is None
    manifest = json.loads((tmp_path / "data" / "manifest.json").read_text())
    assert "data/plans.json" in {f["path"] for f in manifest["files"]}


def test_a_plan_with_nothing_published_is_not_listed():
    empty = {"monthly_fee": None, "discount_percent": None, "discount_of": None}
    with pytest.raises(ValidationError, match="published fee, price or discount"):
        ProviderFile.model_validate(provider(plan=empty))


def test_plans_are_refused_when_the_terms_could_not_be_read():
    data = provider()
    data["terms"]["reuse"] = "not_read"
    with pytest.raises(ValidationError, match="only be listed when the provider's terms"):
        ProviderFile.model_validate(data)
