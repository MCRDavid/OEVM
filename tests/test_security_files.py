"""Checks for the security policy, security.txt and issue forms.

The security.txt check depends on today's date on purpose: it fails when fewer than 30
days remain before Expires, as a reminder to renew the file.
"""

import re
import subprocess
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest
import yaml

from pipeline.project import REPOSITORY_URL

ROOT = Path(__file__).resolve().parent.parent
SECURITY_TXT = ROOT / "site" / ".well-known" / "security.txt"
REPORT_URL = f"{REPOSITORY_URL}/security/advisories/new"
POLICY_URL = f"{REPOSITORY_URL}/blob/main/SECURITY.md"
# Keys such as Jolt's shared apiKey look like this. None may be committed.
KEY_LIKE = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", re.I)
# Recorded feed data holds operators' own record ids, and the lock file holds hashes.
KEY_SCAN_SKIPPED = ("tests/fixtures/", "uv.lock")
# Public notice ids on the government's Contracts Finder site, cited in the blueprint, and
# feed addresses an operator links on its own public page with no key: the id in them names
# the operator's account on its data host (operators/arnold_clark_charge.yaml).
PUBLISHED_FEED_ADDRESSES = {
    "https://api.fuuse.io/opendata/e6397b95-1624-49cd-824d-ab2f9dfe7294/",
}
KEY_LIKE_ALLOWED = {
    "https://www.contractsfinder.service.gov.uk/Notice/9b22d88e-38ba-4055-8e0e-84c58a196aa0",
    "https://www.contractsfinder.service.gov.uk/Notice/Attachment/3f6da4fd-2533-4289-a49e-ebad9a25c086",
    *PUBLISHED_FEED_ADDRESSES,
}
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
    assert config["blank_issues_enabled"] is False, "every issue should start from a form"


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


def tracked_files() -> list[str]:
    try:
        listing = subprocess.run(
            ["git", "ls-files", "-z"], cwd=ROOT, capture_output=True, check=True
        ).stdout
    except (OSError, subprocess.CalledProcessError):
        pytest.skip("not a git checkout")
    return [name for name in listing.decode("utf-8").split("\0") if name]


def test_no_tracked_file_contains_a_key_like_value():
    found = []
    for name in tracked_files():
        if name.startswith(KEY_SCAN_SKIPPED):
            continue
        try:
            text = (ROOT / name).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError):
            continue
        for allowed in KEY_LIKE_ALLOWED:
            text = text.replace(allowed, "")
        found += [f"{name}: {match.group(0)[:8]}..." for match in KEY_LIKE.finditer(text)]
    assert not found, "key-like values found; keep keys in GitHub Actions secrets"
