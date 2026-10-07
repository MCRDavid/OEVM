"""Tests for the transparency page (pipeline/transparency.py)."""

import json
import re
from html.parser import HTMLParser
from pathlib import Path

import pytest

from adapters.http import PoliteClient
from adapters.ocpi_221 import fetch
from adapters.replay import ReplayTransport
from pipeline import run, transparency
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
    hrefs = {attrs.get("href") for tag, attrs in parse(page).tags if tag == "a"}
    for path in ("DISCLAIMER.md", "DATA_LICENCES.md", "docs/PRIVACY_AND_COOKIES.md"):
        assert f"{REPOSITORY_URL}/blob/main/{path}" in hrefs
    assert f"{REPOSITORY_URL}/blob/main/SECURITY.md" in hrefs


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
        assert rate["our_gap_seconds"] >= 1
        assert rate["our_max_per_hour"] == int(3600 // rate["our_gap_seconds"])


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
    page = transparency.render_html(transparency.build({config.id: config}, {}))
    assert "<script>" not in page and "&lt;script&gt;" in page
    assert "<b>Operator</b>" not in page


def test_run_logs_appear_on_the_page(tmp_path):
    config = load_registry()["chargy"]
    transport = ReplayTransport(FIXTURES / "chargy")
    with PoliteClient(config, transport=transport, sleep=lambda _s: None) as client:
        result = fetch(config, client, page_size=2, max_pages=2)
    (tmp_path / "chargy.json").write_text(json.dumps(run.run_log(result, "fixtures")))

    data = transparency.build(load_registry(), transparency.load_runs(tmp_path))
    page = transparency.render_html(data)
    assert "Latest run for each operator" in page
    assert "WORKING" in page
    assert re.search(r"4 records of 5946 reported, stopped early", page)


def test_check_mode_refuses_run_logs(tmp_path):
    with pytest.raises(SystemExit):
        transparency.main(["--check", "--runs", str(tmp_path)])
