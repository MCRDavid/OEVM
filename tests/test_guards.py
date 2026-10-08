"""Guards that keep project rules from depending on careful review alone.

Each test turns a rule from CLAUDE.md into a check that runs on every change.
"""

import json
import re
import socket
import subprocess
from pathlib import Path

import httpx
import pytest

from pipeline import run
from pipeline.registry import load_registry

ROOT = Path(__file__).resolve().parent.parent
FIXTURES = ROOT / "tests" / "fixtures"
DATA_LICENCES = (ROOT / "DATA_LICENCES.md").read_text(encoding="utf-8")
OPERATORS = load_registry()


def test_tests_cannot_reach_the_network():
    with pytest.raises(RuntimeError, match="must never use the network"):
        httpx.get("https://example.com/", timeout=5)
    with pytest.raises(RuntimeError, match="must never use the network"):
        socket.create_connection(("example.com", 443), timeout=5)


def fixture_sets() -> dict[str, dict]:
    sets = {}
    for manifest in sorted(FIXTURES.glob("*/manifest.json")):
        sets[manifest.parent.name] = json.loads(manifest.read_text(encoding="utf-8"))
    return sets


@pytest.mark.parametrize("operator_id", sorted(i for i, c in OPERATORS.items() if c.enabled))
def test_every_enabled_operator_is_complete(operator_id):
    """An operator is switched on only with an adapter, fixtures, licence and attribution."""
    config = OPERATORS[operator_id]
    if config.adapter == "custom":
        assert operator_id in run.CUSTOM_ADAPTERS, "no custom adapter is registered"
    else:
        assert config.adapter in run.ADAPTERS, f"the {config.adapter} adapter is not built"
    assert operator_id in fixture_sets(), f"no tests/fixtures/{operator_id}/manifest.json"
    assert config.licence and config.licence.checked != "unknown"
    assert f"| {config.display_name} |" in DATA_LICENCES, "no row in DATA_LICENCES.md"


@pytest.mark.parametrize("folder", sorted(fixture_sets()))
def test_every_fixture_set_has_a_source_and_licence(folder):
    """Recorded operator data is only kept with attribution and a licence row."""
    manifest = fixture_sets()[folder]
    assert manifest["operator"] == folder
    config = OPERATORS[folder]
    assert config.licence is not None, "fixtures need the operator's licence section filled in"
    assert f"| {config.display_name} |" in DATA_LICENCES
    readme = (FIXTURES / folder / "README.md").read_text(encoding="utf-8")
    assert "## Source and licence" in readme
    assert config.attribution, "the operator file needs an attribution statement"
    assert f"Contains data from {config.display_name}" in readme
    assert "not covered by this project's Apache-2.0 code licence" in " ".join(readme.split())


def test_every_custom_adapter_belongs_to_a_custom_operator():
    for operator_id in run.CUSTOM_ADAPTERS:
        assert OPERATORS[operator_id].adapter == "custom", operator_id


def test_fixture_replays_never_need_a_real_key(monkeypatch):
    for config in OPERATORS.values():
        if config.auth.secret_name:
            monkeypatch.delenv(config.auth.secret_name, raising=False)
    assert run.main(["--fixtures"]) == 0


def test_no_em_dashes_in_tracked_text():
    try:
        names = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
        ).stdout.decode()
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    found = []
    for name in filter(None, names.split("\0")):
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        if name.startswith("tests/fixtures/"):
            continue
        if chr(0x2014) in text:
            found.append(name)
    assert not found, f"em dashes found in {found}"


def test_operator_files_record_dated_evidence_for_findings():
    for config in OPERATORS.values():
        for finding in config.findings:
            assert finding.evidence_url, f"{config.id}: finding on {finding.date} has no evidence"
            assert re.search(r"[a-z]", finding.summary), config.id
