"""Tests for the operator registry: the YAML schema rules, the loader and the seed files."""

import re
from pathlib import Path
from typing import get_args

import pytest
import yaml
from pydantic import ValidationError

from pipeline import registry
from schema.operator import ENGAGEMENT_LABELS, EngagementStatus, OperatorConfig

OPERATORS_DIR = Path(__file__).resolve().parent.parent / "operators"
SEED_IDS = {
    "bp_pulse",
    "chargy",
    "community_by_shell_recharge",
    "geniepoint",
    "go_zero",
    "gridserve",
    "instavolt",
    "jolt",
    "pod",
    "shell_recharge",
    "ubitricity",
}
UUID_LIKE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
# Fake values for tests that check credentials are rejected. None of them is a real secret.
FAKE_URL_WITH_PASSWORD = "https://user:pass@example.invalid/ocpi"  # pragma: allowlist secret
EXAMPLE_NAME = "EXAMPLE_TOKEN"
RESERVED_NAME = "GITHUB_TOKEN"


CHECKED_LICENCE = {"name": "OGL-3.0", "basis": "Checked for this test.", "checked": "2026-10-07"}


def minimal(**overrides) -> dict:
    """The smallest valid operator: nothing known, not enabled."""
    data = {
        "id": "example_operator",
        "display_name": "Example Operator",
        "ocpi_country_code": "unknown",
        "ocpi_party_id": "unknown",
        "adapter": "unknown",
        "base_url": "unknown",
        "auth": {"method": "unknown"},
        "supports_single_location": "unknown",
        "cors": "unknown",
        "engagement": {"status": "unknown"},
        "enabled": False,
    }
    data.update(overrides)
    return data


def enabled_open(**overrides) -> dict:
    """A valid enabled operator with an anonymous feed."""
    data = minimal(
        adapter="ocpi_221",
        base_url="https://example.invalid/ocpi",
        auth={"method": "none"},
        attribution="Contains data from Example Operator.",
        licence=CHECKED_LICENCE,
        enabled=True,
    )
    data.update(overrides)
    return data


def write_operator(directory: Path, data: dict, name: str | None = None) -> Path:
    path = directory / (name or f"{data['id']}.yaml")
    path.write_text(yaml.safe_dump(data, sort_keys=False), encoding="utf-8")
    return path


# The seed files


def test_seed_registry_is_valid_and_complete():
    operators = registry.load_registry(OPERATORS_DIR)
    assert set(operators) == SEED_IDS


def test_template_is_valid_and_disabled():
    data = yaml.safe_load((OPERATORS_DIR / "_template.yaml").read_text(encoding="utf-8"))
    config = OperatorConfig.model_validate(data)
    assert config.enabled is False


def test_operator_files_contain_no_key_like_values():
    for path in sorted(OPERATORS_DIR.glob("*.yaml")):
        assert not UUID_LIKE.search(path.read_text(encoding="utf-8")), path.name


def test_cli_validate_succeeds_on_seed_registry(capsys):
    assert registry.main(["--validate"]) == 0
    assert "Operator registry is valid: 11 operators" in capsys.readouterr().out


def test_cli_without_validate_prints_help(capsys):
    assert registry.main([]) == 2
    assert "--validate" in capsys.readouterr().out


def test_every_engagement_status_has_a_neutral_label():
    assert set(ENGAGEMENT_LABELS) == set(get_args(EngagementStatus))


# Schema rules


def test_minimal_and_enabled_examples_are_valid():
    OperatorConfig.model_validate(minimal())
    OperatorConfig.model_validate(enabled_open())


@pytest.mark.parametrize(
    "data",
    [
        minimal(base_url="https://example.invalid/ocpi?apiKey=abc"),
        minimal(
            endpoints={
                "locations": {
                    "url": "https://example.invalid/locations?token=abc",
                    "status": "documented",
                }
            }
        ),
        minimal(base_url=FAKE_URL_WITH_PASSWORD),
        minimal(sources=[{"url": "https://example.invalid/?access_token=abc"}]),
        minimal(auth={"method": "none", "secret_name": EXAMPLE_NAME}),
        minimal(auth={"method": "header", "name": "x-key"}),
        minimal(auth={"method": "query_param", "secret_name": EXAMPLE_NAME}),
        minimal(auth={"method": "header", "name": "x-key", "secret_name": EXAMPLE_NAME.lower()}),
        minimal(auth={"method": "header", "name": "x-key", "secret_name": RESERVED_NAME}),
        enabled_open(adapter="unknown"),
        enabled_open(base_url="unknown"),
        enabled_open(auth={"method": "unknown"}),
        enabled_open(auth={"method": "header", "name": "unknown", "secret_name": EXAMPLE_NAME}),
        enabled_open(attribution=None),
        enabled_open(licence=None),
        enabled_open(licence={**CHECKED_LICENCE, "checked": "unknown"}),
        enabled_open(licence={**CHECKED_LICENCE, "name": "unknown"}),
        minimal(licence={"name": "OGL-3.0", "checked": "2026-10-07"}),
        minimal(engagement={"status": "open_anonymous"}),
        minimal(
            engagement={
                "status": "requested_no_reply",
                "evidence": [{"date": "2026-10-01", "file": "evidence/example_operator/a.md"}],
            }
        ),
        minimal(access_requested="2026-10-02", access_granted="2026-10-01"),
        minimal(engagement={"status": "open_anonymous", "evidence": [{"date": "unknown"}]}),
        minimal(
            engagement={
                "status": "unknown",
                "evidence": [{"date": "6 October", "url": "https://example.invalid"}],
            }
        ),
        minimal(id="osm"),
        minimal(id="Example-Operator"),
        minimal(ocpi_party_id="cg"),
        minimal(ocpi_country_code="GBR"),
        minimal(adapter="ocpi"),
        minimal(cors=True),
        minimal(typo_field=1),
    ],
    ids=[
        "key-in-base-url",
        "token-in-endpoint",
        "password-in-url",
        "token-in-source-url",
        "secret-with-no-auth",
        "header-without-secret",
        "query-param-without-name",
        "lower-case-secret-name",
        "reserved-secret-prefix",
        "enabled-without-adapter",
        "enabled-without-url",
        "enabled-with-unknown-auth",
        "enabled-with-unknown-header-name",
        "enabled-without-attribution",
        "enabled-without-licence",
        "enabled-with-unchecked-licence",
        "enabled-with-unknown-licence",
        "licence-without-basis",
        "status-without-evidence",
        "no-reply-without-request-date",
        "granted-before-requested",
        "evidence-without-url-or-file",
        "evidence-with-bad-date",
        "reserved-id",
        "bad-id",
        "bad-party-id",
        "bad-country-code",
        "unknown-adapter",
        "yaml-yes-instead-of-value",
        "unknown-field",
    ],
)
def test_invalid_operator_configs_are_rejected(data):
    with pytest.raises(ValidationError):
        OperatorConfig.model_validate(data)


# Loader


def test_loader_reports_id_not_matching_file_name(tmp_path):
    write_operator(tmp_path, minimal(), name="something_else.yaml")
    with pytest.raises(registry.RegistryError, match="must match the file name"):
        registry.load_registry(tmp_path)


def test_loader_rejects_yml_extension(tmp_path):
    write_operator(tmp_path, minimal())
    write_operator(tmp_path, minimal(id="other"), name="other.yml")
    with pytest.raises(registry.RegistryError, match=r"rename to \.yaml"):
        registry.load_registry(tmp_path)


def test_loader_reports_broken_yaml(tmp_path):
    (tmp_path / "broken.yaml").write_text("id: [unclosed\n", encoding="utf-8")
    with pytest.raises(registry.RegistryError, match=r"broken\.yaml"):
        registry.load_registry(tmp_path)


def test_loader_reports_empty_directory(tmp_path):
    with pytest.raises(registry.RegistryError, match="no operator files"):
        registry.load_registry(tmp_path)


def test_loader_ignores_underscore_files(tmp_path):
    write_operator(tmp_path, minimal())
    (tmp_path / "_notes.yaml").write_text("not: an operator\n", encoding="utf-8")
    assert set(registry.load_registry(tmp_path)) == {"example_operator"}


def test_loader_checks_evidence_files_exist(tmp_path):
    operators_dir = tmp_path / "operators"
    operators_dir.mkdir()
    evidence = {"date": "2026-10-06", "file": "evidence/example_operator/reply.md"}
    write_operator(
        operators_dir,
        minimal(engagement={"status": "request_declined", "evidence": [evidence]}),
    )
    with pytest.raises(registry.RegistryError, match="does not exist"):
        registry.load_registry(operators_dir)

    saved = tmp_path / "evidence" / "example_operator" / "reply.md"
    saved.parent.mkdir(parents=True)
    saved.write_text("Dated summary of the reply.\n", encoding="utf-8")
    assert "example_operator" in registry.load_registry(operators_dir)


def test_loader_rejects_evidence_in_another_operators_folder(tmp_path):
    evidence = {"date": "2026-10-06", "file": "evidence/someone_else/reply.md"}
    write_operator(
        tmp_path, minimal(engagement={"status": "request_declined", "evidence": [evidence]})
    )
    with pytest.raises(registry.RegistryError, match="must be under evidence/example_operator/"):
        registry.load_registry(tmp_path)


def test_cli_validate_fails_on_invalid_registry(tmp_path, capsys):
    write_operator(tmp_path, minimal(enabled=True))
    assert registry.main(["--validate", "--dir", str(tmp_path)]) == 1
    assert "NOT valid" in capsys.readouterr().err


def test_undated_evidence_produces_a_warning():
    config = OperatorConfig.model_validate(
        minimal(
            engagement={
                "status": "open_shared_key",
                "evidence": [{"date": "unknown", "url": "https://example.invalid/help"}],
            }
        )
    )
    assert registry.warnings_for(config) == [
        "example_operator: evidence https://example.invalid/help has no date; add the date checked"
    ]
