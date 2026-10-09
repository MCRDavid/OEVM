"""The /add-operator skill stays in step with the registry, the adapters and the commands."""

import importlib.util
import re
import typing

from pipeline import run
from pipeline.registry import ROOT
from schema.operator import AdapterName, EngagementStatus

SKILL = (ROOT / ".claude" / "skills" / "add-operator" / "SKILL.md").read_text(encoding="utf-8")


def test_skill_has_a_name_and_description():
    front = SKILL.split("---")[1]
    assert re.search(r"^name: add-operator$", front, re.MULTILINE)
    assert re.search(r"^description: \S", front, re.MULTILINE)


def test_adapter_table_matches_what_is_built():
    states = dict(re.findall(r"^\| `(\w+)` \| ([a-z ]*?) *\|", SKILL, re.MULTILINE))
    assert set(states) == set(typing.get_args(AdapterName))
    for name, state in states.items():
        if name == "unknown":
            continue
        built = name in run.ADAPTERS or (name == "custom" and bool(run.CUSTOM_ADAPTERS))
        assert state == ("built" if built else "not built yet"), name


def test_every_engagement_status_that_needs_a_key_is_named():
    for status in ("key_on_request", "requested_no_reply", "signed_agreement_required"):
        assert status in typing.get_args(EngagementStatus)
        assert f"`{status}`" in SKILL


def test_every_command_runs_a_module_that_exists():
    modules = set(re.findall(r"uv run python -m ([\w.]+)", SKILL))
    assert modules
    for module in modules:
        assert importlib.util.find_spec(module), module


def test_every_repository_path_it_names_exists():
    paths = set(re.findall(r"`((?:operators|tests|pipeline|\.github|schema)/[^`<\s]+)`", SKILL))
    paths.add("DATA_LICENCES.md")
    assert paths
    for path in paths:
        assert (ROOT / path).exists(), path
