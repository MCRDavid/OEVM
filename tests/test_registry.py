"""Tests for the operator registry: the YAML schema rules, the loader and the seed files."""

import datetime as dt
import re
from pathlib import Path
from typing import get_args

import pytest
import yaml
from pydantic import ValidationError

from pipeline import registry
from schema.operator import ENGAGEMENT_LABELS, EngagementStatus, OperatorConfig
from tests.test_security_files import PUBLISHED_FEED_ADDRESSES

OPERATORS_DIR = Path(__file__).resolve().parent.parent / "operators"
SEED_IDS = {
    "allego",
    "applegreen_electric",
    "arnold_clark_charge",
    "asda_express_electric",
    "be_ev",
    "believ",
    "blink_charging_uk",
    "bp_pulse",
    "charge_my_street",
    "chargeplace_scotland",
    "chargepoint",
    "chargy",
    "clenergy_ev",
    "community_by_shell_recharge",
    "connected_kerb",
    "connekt",
    "electric_blue",
    "elmtronics",
    "esb_energy",
    "ev_smart",
    "evolt",
    "evyve",
    "ez_charge",
    "fastned",
    "for_ev",
    "forward_ev",
    "geniepoint",
    "giga_power",
    "go_zero",
    "gridserve",
    "hubsta",
    "instavolt",
    "ionity",
    "joju",
    "jolt",
    "liberty_charge",
    "lidl",
    "mer_uk",
    "mfg_ev_power",
    "osprey",
    "parkrecharge",
    "plug_n_go",
    "pod",
    "pogo_charge",
    "qwello",
    "raw_charging",
    "roam",
    "scottishpower_recharge",
    "shell_recharge",
    "smart_charge",
    "source_ev",
    "sprint",
    "tesla",
    "totalenergies",
    "trojan_energy",
    "ubitricity",
    "wattif",
    "weev",
    "wenea",
    "zest",
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
        text = path.read_text(encoding="utf-8")
        for address in PUBLISHED_FEED_ADDRESSES:
            text = text.replace(address, "")
        assert not UUID_LIKE.search(text), path.name


def test_cli_validate_succeeds_on_seed_registry(capsys):
    assert registry.main(["--validate"]) == 0
    assert "Operator registry is valid: 60 operators" in capsys.readouterr().out


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
        minimal(
            findings=[{"date": "2026-10-07", "kind": "data_quality", "summary": "It is illegal."}]
        ),
        minimal(notes="The operator is in breach of the rules."),
        minimal(
            findings=[
                {"date": "2026-10-07", "kind": "data_quality", "summary": "x", "status": "resolved"}
            ]
        ),
        minimal(findings=[{"date": "2026-10-07", "kind": "gossip", "summary": "x"}]),
        minimal(findings=[{"date": "unknown", "kind": "access", "summary": "x"}]),
        minimal(
            rate_limit={
                "min_seconds_between_requests": 2,
                "limits": [
                    {
                        "publisher": "Example Operator",
                        "requests": 30,
                        "per_seconds": 3600,
                        "quote": "30 requests per 1 hour",
                        "source_url": "https://example.invalid/terms",
                        "checked": "2026-10-07",
                    }
                ],
            }
        ),
        minimal(rate_limit={"min_seconds_between_requests": 0.5}),
        minimal(
            rate_limit={
                "min_seconds_between_requests": 200,
                "limits": [
                    {
                        "requests": 30,
                        "per_seconds": 3600,
                        "quote": "30 requests per 1 hour",
                        "source_url": "https://example.invalid/terms",
                        "checked": "2026-10-07",
                    }
                ],
            }
        ),
        minimal(
            auth={"method": "header", "name": "x-api-key", "secret_name": EXAMPLE_NAME},
            base_url="http://example.invalid/ocpi",
        ),
        minimal(
            auth={"method": "query_param", "name": "apiKey", "secret_name": EXAMPLE_NAME},
            endpoints={
                "locations": {"url": "http://example.invalid/locations", "status": "documented"}
            },
        ),
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
        "accusatory-finding",
        "accusatory-notes",
        "resolved-without-date",
        "unknown-finding-kind",
        "finding-without-date",
        "gap-breaks-published-limit",
        "gap-below-project-minimum",
        "limit-without-publisher",
        "key-over-plain-http-base-url",
        "key-over-plain-http-endpoint",
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
        minimal(engagement={"status": "key_on_request", "evidence": [evidence]}),
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
        tmp_path, minimal(engagement={"status": "key_on_request", "evidence": [evidence]})
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
        "example_operator: evidence https://example.invalid/help has no date; add the date checked",
        "example_operator: no dated status yet; record a page_checked or feed_searched entry "
        "in engagement.log",
    ]


def test_resolved_finding_with_date_is_valid():
    OperatorConfig.model_validate(
        minimal(
            findings=[
                {
                    "date": "2026-10-01",
                    "kind": "data_quality",
                    "summary": "Prices were missing.",
                    "status": "resolved",
                    "resolved_date": "2026-10-07",
                }
            ]
        )
    )


# The engagement log

REQUEST = {
    "date": "2026-10-01",
    "action": "request_sent",
    "channel": "web_form",
    "summary": "Requested access through the operator's form.",
}
REPLY = {
    "date": "2026-10-05",
    "action": "reply_received",
    "channel": "email",
    "summary": "The operator replied that the request is being reviewed.",
    "evidence_file": "evidence/example_operator/2026-10-05-reply.md",
}
GRANTED = {
    "date": "2026-10-08",
    "action": "key_granted",
    "channel": "email",
    "summary": "A key was issued.",
    "evidence_file": "evidence/example_operator/2026-10-08-key.md",
}


def test_a_complete_log_is_valid():
    OperatorConfig.model_validate(
        minimal(
            engagement={"status": "key_on_request", "log": [REQUEST, REPLY, GRANTED]},
            access_requested="2026-10-01",
            access_granted="2026-10-08",
        )
    )
    OperatorConfig.model_validate(
        minimal(
            engagement={"status": "requested_awaiting_decision", "log": [REQUEST, REPLY]},
            access_requested="2026-10-01",
        )
    )


@pytest.mark.parametrize(
    "data",
    [
        minimal(engagement={"status": "requested_no_reply", "log": [REQUEST]}),
        minimal(
            engagement={"status": "requested_no_reply", "log": [REQUEST, REPLY]},
            access_requested="2026-10-01",
        ),
        minimal(
            engagement={
                "status": "requested_no_reply",
                "log": [
                    REQUEST,
                    REPLY,
                    {**REQUEST, "date": "2026-10-06", "action": "follow_up_sent"},
                ],
            },
            access_requested="2026-10-01",
        ),
        minimal(engagement={"status": "unknown", "log": [REPLY, REQUEST]}),
        minimal(engagement={"status": "unknown", "log": [{**REQUEST, "channel": None}]}),
        minimal(
            engagement={"status": "unknown", "log": [{**REPLY, "evidence_file": None}]},
        ),
        minimal(
            engagement={
                "status": "request_declined",
                "log": [{**REPLY, "action": "request_declined"}],
            }
        ),
        minimal(engagement={"status": "request_declined", "log": [REPLY]}),
        minimal(
            engagement={
                "status": "unknown",
                "log": [{**REQUEST, "summary": "Wrote to opendata@example.invalid for a key."}],
            }
        ),
        minimal(
            engagement={
                "status": "unknown",
                "log": [{**REQUEST, "summary": "The operator is in breach of the rules."}],
            }
        ),
        minimal(engagement={"status": "unknown", "log": [REQUEST]}),
        minimal(access_requested="2026-10-01"),
        minimal(
            engagement={"status": "unknown", "log": [REQUEST, GRANTED]},
            access_requested="2026-10-01",
        ),
        minimal(engagement={"status": "unknown", "log": [{**REQUEST, "date": "unknown"}]}),
        minimal(engagement={"status": "unknown", "log": [{**REQUEST, "action": "chased"}]}),
    ],
    ids=[
        "no-reply-without-access-requested",
        "no-reply-after-a-reply",
        "no-reply-after-a-reply-and-follow-up",
        "log-out-of-order",
        "request-without-channel",
        "reply-without-evidence",
        "decline-without-quote",
        "declined-status-without-decline",
        "email-address-in-summary",
        "accusatory-summary",
        "request-without-access-requested",
        "access-requested-without-request",
        "key-without-access-granted",
        "undated-step",
        "unknown-action",
    ],
)
def test_invalid_engagement_logs_are_rejected(data):
    with pytest.raises(ValidationError):
        OperatorConfig.model_validate(data)


def test_loader_checks_log_evidence_files_exist(tmp_path):
    operators_dir = tmp_path / "operators"
    operators_dir.mkdir()
    write_operator(
        operators_dir,
        minimal(
            engagement={"status": "requested_awaiting_decision", "log": [REQUEST, REPLY]},
            access_requested="2026-10-01",
        ),
    )
    with pytest.raises(registry.RegistryError, match=r"2026-10-05-reply\.md does not exist"):
        registry.load_registry(operators_dir)
    saved = tmp_path / REPLY["evidence_file"]
    saved.parent.mkdir(parents=True)
    saved.write_text("Dated summary of the reply.\n", encoding="utf-8")
    assert "example_operator" in registry.load_registry(operators_dir)


def test_validator_suggests_a_follow_up_after_two_weeks():
    config = OperatorConfig.model_validate(
        minimal(
            engagement={"status": "requested_no_reply", "log": [REQUEST]},
            access_requested="2026-10-01",
        )
    )
    assert registry.warnings_for(config, today=dt.date(2026, 10, 14)) == []
    assert registry.warnings_for(config, today=dt.date(2026, 10, 15)) == [
        "example_operator: no reply recorded 14 days after the 2026-10-01 request sent; "
        "consider a follow-up"
    ]


def test_seed_operators_without_a_dated_status_are_flagged():
    for config in registry.load_registry().values():
        undated = config.engagement.as_of is None
        assert undated == any("no dated status yet" in w for w in registry.warnings_for(config)), (
            config.id
        )


def test_a_repeated_same_day_request_counts_from_its_own_position():
    reply = {**REPLY, "date": "2026-10-01"}
    config = OperatorConfig.model_validate(
        minimal(
            engagement={"status": "requested_awaiting_decision", "log": [REQUEST, reply, REQUEST]},
            access_requested="2026-10-01",
        )
    )
    assert config.engagement.awaiting_reply()


# Tariffs from a related operator's feed (ADR 0020)

RELATED = {
    "decided": "2026-10-10",
    "basis": "Both networks are run by one company and publish from one host.",
    "evidence_url": "https://example.invalid/terms",
}


@pytest.mark.parametrize(
    "operators",
    [[], ["Other"], ["other", "other"], ["example_operator"]],
    ids=["none", "not-an-id", "named-twice", "itself"],
)
def test_a_tariffs_from_decision_needs_other_operator_ids(operators):
    with pytest.raises(ValidationError):
        OperatorConfig.model_validate(
            enabled_open(tariffs_from={**RELATED, "operators": operators})
        )


def test_tariffs_from_may_name_an_operator_on_the_same_host(tmp_path):
    write_operator(tmp_path, enabled_open(tariffs_from={**RELATED, "operators": ["other"]}))
    other = enabled_open(
        id="other",
        base_url="unknown",
        endpoints={
            "tariffs": {"url": "https://example.invalid/other/tariffs", "status": "documented"}
        },
    )
    write_operator(tmp_path, other)
    operators = registry.load_registry(tmp_path)
    assert operators["example_operator"].tariffs_from.operators == ["other"]
    assert "example_operator (from other)" in registry.summary(operators)


def test_tariffs_from_cannot_name_an_unknown_operator(tmp_path):
    write_operator(tmp_path, enabled_open(tariffs_from={**RELATED, "operators": ["other"]}))
    with pytest.raises(registry.RegistryError, match="unknown operator 'other'"):
        registry.load_registry(tmp_path)


def test_tariffs_from_cannot_name_an_operator_on_another_host(tmp_path):
    write_operator(tmp_path, enabled_open(tariffs_from={**RELATED, "operators": ["other"]}))
    write_operator(tmp_path, enabled_open(id="other", base_url="https://other.invalid/ocpi"))
    with pytest.raises(registry.RegistryError, match="not on the same host"):
        registry.load_registry(tmp_path)


def test_only_the_smartcharging_networks_carry_a_tariffs_from_decision():
    operators = registry.load_registry(OPERATORS_DIR)
    decisions = {i: c.tariffs_from.operators for i, c in operators.items() if c.tariffs_from}
    assert decisions == {
        "chargeplace_scotland": ["evolt"],
        "evolt": ["chargeplace_scotland"],
        "pogo_charge": ["evolt"],
    }
