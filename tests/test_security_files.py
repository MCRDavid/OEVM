"""Checks for the security policy, security.txt and issue forms.

The security.txt check depends on today's date on purpose: it fails when fewer than 30
days remain before Expires, as a reminder to renew the file.
"""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import yaml

from pipeline.project import REPOSITORY_URL

ROOT = Path(__file__).resolve().parent.parent
SECURITY_TXT = ROOT / "site" / ".well-known" / "security.txt"
REPORT_URL = f"{REPOSITORY_URL}/security/advisories/new"
POLICY_URL = f"{REPOSITORY_URL}/blob/main/SECURITY.md"
# RFC 9116 fields, plus CSAF and Bug-Bounty, which IANA's registry added later.
RFC_9116_FIELDS = {
    "Acknowledgments",
    "Bug-Bounty",
    "Canonical",
    "Contact",
    "CSAF",
    "Encryption",
    "Expires",
    "Hiring",
    "Policy",
    "Preferred-Languages",
}


def security_txt_fields() -> list[tuple[str, str]]:
    fields = []
    for line in SECURITY_TXT.read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#"):
            continue
        name, separator, value = line.partition(": ")
        assert separator, f"not a field line: {line!r}"
        fields.append((name, value.strip()))
    return fields


def test_security_txt_has_only_rfc_9116_fields():
    names = [name for name, _ in security_txt_fields()]
    assert set(names) <= RFC_9116_FIELDS
    assert names.count("Expires") == 1
    assert names.count("Contact") >= 1


def test_security_txt_is_small_plain_utf8_with_https_links():
    raw = SECURITY_TXT.read_bytes()
    raw.decode("utf-8")
    assert len(raw) < 32 * 1024 and len(raw.splitlines()) < 1000  # RFC 9116 section 5.4
    for name, value in security_txt_fields():
        assert len(value) < 2048
        if name in {"Contact", "Policy", "Canonical", "Acknowledgments", "Hiring"}:
            assert value.startswith(("https://", "mailto:", "tel:")), name


def test_security_txt_points_at_this_repository():
    fields = security_txt_fields()
    assert [value for name, value in fields if name == "Contact"] == [REPORT_URL, POLICY_URL]
    assert dict(fields)["Policy"] == POLICY_URL


def test_security_txt_has_not_expired_and_is_less_than_a_year_ahead():
    expires = datetime.fromisoformat(dict(security_txt_fields())["Expires"])
    now = datetime.now(UTC)
    assert expires - now > timedelta(days=30), (
        "site/.well-known/security.txt expires soon: set Expires to a date under a year ahead"
    )
    assert expires - now < timedelta(days=366), "RFC 9116 recommends Expires under a year ahead"


def test_security_policy_explains_private_reporting():
    policy = (ROOT / "SECURITY.md").read_text(encoding="utf-8")
    assert "Report a vulnerability" in policy
    assert "privately" in policy


def test_issue_forms_point_security_reports_to_the_private_route():
    config = yaml.safe_load((ROOT / ".github" / "ISSUE_TEMPLATE" / "config.yml").read_text())
    assert [link["url"] for link in config["contact_links"]] == [REPORT_URL]


def test_issue_forms_warn_that_issues_are_public():
    for path in (ROOT / ".github" / "ISSUE_TEMPLATE").glob("*.yml"):
        if path.name == "config.yml":
            continue
        form = yaml.safe_load(path.read_text(encoding="utf-8"))
        assert {"name", "description", "body"} <= set(form), path.name
        text = path.read_text(encoding="utf-8")
        assert "Issues are public" in text, path.name
        checkboxes = [item for item in form["body"] if item["type"] == "checkboxes"]
        assert checkboxes and all(
            option.get("required") for box in checkboxes for option in box["attributes"]["options"]
        ), path.name
