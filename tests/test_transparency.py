"""Tests for the transparency page (pipeline/transparency.py)."""

import html
import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from pipeline import transparency
from pipeline.project import REPOSITORY_URL
from pipeline.registry import load_registry
from schema.operator import OperatorConfig, neutral_text

FIXTURES = Path(__file__).parent / "fixtures"


class TextAndTags(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.tags: list[tuple[str, dict]] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append((tag, dict(attrs)))

    def handle_data(self, data):
        self.text.append(data)


def parse(page: str) -> TextAndTags:
    parser = TextAndTags()
    parser.feed(page)
    return parser


@pytest.fixture(scope="module")
def page() -> str:
    return transparency.outputs()[transparency.PAGE_PATH]


def test_committed_page_and_json_are_up_to_date():
    for path, text in transparency.outputs().items():
        assert path.read_text(encoding="utf-8") == text, (
            f"{path.name} is out of date: run 'uv run python -m pipeline.transparency'"
        )
    assert transparency.main(["--check"]) == 0


def test_page_lists_every_operator_and_finding(page):
    text = " ".join(parse(page).text)
    for config in load_registry().values():
        assert config.display_name in text
        for finding in config.findings:
            assert " ".join(finding.summary.split()) in " ".join(text.split())


def test_page_shows_the_short_disclaimer_and_required_links(page):
    assert transparency.short_disclaimer() in " ".join(parse(page).text)
    footer = page[page.index("<footer>") :]
    # DISCLAIMER.md asks for the short version in the footer of every page.
    assert html.escape(transparency.short_disclaimer(), quote=True) in footer
    hrefs = {attrs.get("href") for tag, attrs in parse(page).tags if tag == "a"}
    for path in ("DISCLAIMER.md", "DATA_LICENCES.md", "SECURITY.md"):
        assert f"{REPOSITORY_URL}/blob/main/{path}" in hrefs
    assert "../privacy/" in hrefs  # the privacy notice, published on the site


def test_page_loads_nothing_from_anywhere_else(page):
    tags = parse(page).tags
    assert not [t for t, _ in tags if t in ("script", "link", "img", "iframe")]
    assert not [a for _, a in tags if "src" in a]
    assert "@import" not in page and "url(" not in page


def test_page_is_british_english_and_neutral(page):
    assert '<html lang="en-GB">' in page
    assert chr(0x2014) not in page  # no em dashes
    neutral_text(" ".join(parse(page).text))


def test_rate_limits_show_our_setting_and_the_regulation(page):
    data = json.loads(transparency.outputs()[transparency.JSON_PATH])
    assert "set no limit" in data["regulation"]["summary"]
    for op in data["operators"]:
        rate = op["rate_limit"]
        gap, per_hour = rate["our_gap_seconds"], rate["our_max_per_hour"]
        assert gap >= 1
        # per_hour requests a gap apart fit in an hour; one more would not.
        assert (per_hour - 1) * gap < 3600 <= per_hour * gap


def test_a_decision_on_missing_publish_flags_is_shown(page):
    data = json.loads(transparency.outputs()[transparency.JSON_PATH])
    decisions = {op["id"]: op["missing_publish_flag"] for op in data["operators"]}
    assert decisions["jolt"]["decided"] == "2026-10-08"
    assert decisions["chargy"] is None
    assert "Locations with no publish flag" in page
    assert "Shown: Jolt publishes this feed itself" in " ".join(page.split())


def test_each_published_limit_names_its_publisher(page):
    data = json.loads(transparency.outputs()[transparency.JSON_PATH])
    published = [p for op in data["operators"] for p in op["rate_limit"]["published"]]
    assert published and all(p["publisher"] for p in published)
    assert "Published limit (operator or its data host)" in page
    assert "published by Eco-Movement" in page and "published by Gridserve" in page


@pytest.mark.parametrize(("gap", "expected"), [(2, 1800), (7, 515), (30, 120), (125, 29)])
def test_hourly_maximum(gap, expected):
    assert transparency.max_per_hour(gap) == expected


def test_text_from_the_registry_is_escaped():
    config = OperatorConfig.model_validate(
        {
            "id": "example_operator",
            "display_name": "Example <b>Operator</b>",
            "ocpi_country_code": "unknown",
            "ocpi_party_id": "unknown",
            "adapter": "unknown",
            "base_url": "unknown",
            "auth": {"method": "unknown"},
            "supports_single_location": "unknown",
            "cors": "unknown",
            "engagement": {"status": "unknown"},
            "findings": [
                {"date": "2026-10-07", "kind": "data_quality", "summary": "<script>x</script>"}
            ],
            "enabled": False,
        }
    )
    page = transparency.render_html(transparency.build({config.id: config}))
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "<b>Operator</b>" not in page


def test_runs_are_on_the_feed_health_page_not_here(page):
    assert 'href="../status/"' in page
    assert "latest_run" not in transparency.outputs()[transparency.JSON_PATH]


def test_url_templates_are_not_links(page):
    hrefs = [attrs.get("href", "") for tag, attrs in parse(page).tags if tag == "a"]
    assert not [href for href in hrefs if "{" in href]
    assert "<code>https://api.joltcharge.com/v1/uk/public/tariffs/{tariffId}</code>" in page


def test_last_reviewed_counts_resolved_dates():
    config = OperatorConfig.model_validate(
        {
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
            "findings": [
                {
                    "date": "2026-10-07",
                    "kind": "data_quality",
                    "summary": "Prices were missing.",
                    "status": "resolved",
                    "resolved_date": "2026-11-20",
                }
            ],
            "enabled": False,
        }
    )
    assert transparency.last_reviewed({config.id: config}) == "2026-11-20"


# The engagement log

REQUEST = {
    "date": "2026-10-01",
    "action": "request_sent",
    "channel": "web_form",
    "summary": "Requested access through the operator's form.",
}


def operator_with(engagement: dict, **overrides) -> OperatorConfig:
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
        "engagement": engagement,
        "enabled": False,
    }
    data.update(overrides)
    return OperatorConfig.model_validate(data)


def test_every_operator_appears_in_the_engagement_table(page):
    table = page[page.index("Access status for every known operator") :]
    table = table[: table.index("</table>")]
    for config in load_registry().values():
        assert html.escape(config.display_name) in table


def test_status_is_dated_by_the_latest_log_entry():
    check = {
        "date": "2026-10-09",
        "action": "page_checked",
        "summary": "Read the page.",
        "evidence_url": "https://example.invalid/open-data",
    }
    config = operator_with(
        {
            "status": "key_on_request",
            "evidence": [{"date": "2026-10-02", "url": "https://example.invalid/open-data"}],
            "log": [check],
        }
    )
    assert transparency.engagement_headline(config.engagement) == (
        "Key issued on request (as of 2026-10-09)"
    )
    assert transparency.last_reviewed({config.id: config}) == "2026-10-09"


def test_requests_and_responses_are_shown_as_dates_not_day_counts():
    chase = {**REQUEST, "date": "2026-10-15", "action": "follow_up_sent"}
    check = {"date": "2026-10-29", "action": "page_checked", "summary": "Checked for a reply."}
    config = operator_with(
        {"status": "requested_no_reply", "log": [REQUEST, chase, check]},
        access_requested="2026-10-01",
    )
    assert transparency.engagement_headline(config.engagement) == (
        "Requested, no reply (as of 2026-10-29)"
    )
    view = transparency.operator_view(config)
    assert view["access_requested"] == "2026-10-01"
    assert view["engagement"]["last_request"] == "2026-10-15"
    assert view["engagement"]["last_response"] is None
    assert view["engagement"]["last_response_text"] == "None recorded"
    page = transparency.render_html(transparency.build({config.id: config}))
    section = page[
        page.index("<h2>Access and engagement</h2>") : page.index("<h2>Rate limits</h2>")
    ]
    assert not re.search(r"\bdays?\b", " ".join(parse(section).text))


def test_the_last_response_is_shown_with_its_date():
    reply = {
        "date": "2026-10-05",
        "action": "reply_received",
        "channel": "email",
        "summary": "The operator replied that the request is being reviewed.",
        "evidence_url": "https://example.invalid/reply",
    }
    config = operator_with(
        {"status": "requested_awaiting_decision", "log": [REQUEST, reply]},
        access_requested="2026-10-01",
    )
    view = transparency.operator_view(config)
    assert view["engagement"]["last_response"] == {
        "date": "2026-10-05",
        "action": "reply_received",
    }
    assert view["engagement"]["last_response_text"] == "2026-10-05 (Reply received)"


def test_an_operator_never_asked_shows_no_request_sent():
    config = operator_with({"status": "unknown"})
    assert transparency.last_response_text(config.engagement) == "No request sent"


def test_an_undated_status_says_so():
    config = operator_with({"status": "unknown"})
    assert transparency.engagement_headline(config.engagement) == (
        "Not yet established (no dated check yet)"
    )


def test_a_declined_request_shows_the_operators_words_and_saved_copy():
    decline = {
        "date": "2026-10-20",
        "action": "request_declined",
        "channel": "email",
        "summary": "The operator replied that it does not offer a feed to individuals.",
        "quote": "We are <not> able to offer access.",
        "evidence_file": "evidence/example_operator/2026-10-20-reply.md",
    }
    config = operator_with(
        {"status": "request_declined", "log": [REQUEST, decline]},
        access_requested="2026-10-01",
    )
    page = transparency.render_html(transparency.build({config.id: config}))
    assert "&ldquo;We are &lt;not&gt; able to offer access.&rdquo;" in page
    assert f"{REPOSITORY_URL}/blob/main/evidence/example_operator/2026-10-20-reply.md" in page
    neutral_text(" ".join(parse(page).text))


def test_a_decision_to_swap_back_coordinates_is_shown(page):
    data = json.loads(transparency.outputs()[transparency.JSON_PATH])
    decisions = {op["id"]: op["swapped_coordinates"] for op in data["operators"]}
    decided = {"clenergy_ev", "geniepoint"}
    assert all(decisions[k]["decided"] == "2026-10-09" for k in decided)
    assert all(v is None for k, v in decisions.items() if k not in decided)
    assert "obviously missing a minus sign, are corrected and marked" in " ".join(page.split())
