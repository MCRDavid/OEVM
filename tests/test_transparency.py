"""Tests for the transparency page (pipeline/transparency.py)."""

import html
import json
import re
from datetime import UTC, datetime
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
NOW_UTC = datetime(2026, 10, 8, 3, 0, tzinfo=UTC)


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
        gap, per_hour = rate["our_gap_seconds"], rate["our_max_per_hour"]
        assert gap >= 1
        # per_hour requests a gap apart fit in an hour; one more would not.
        assert (per_hour - 1) * gap < 3600 <= per_hour * gap


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


def chargy_run_log() -> dict:
    config = load_registry()["chargy"]
    transport = ReplayTransport(FIXTURES / "chargy")
    with PoliteClient(config, transport=transport, sleep=lambda _s: None) as client:
        result = fetch(config, client, page_size=2, max_pages=2)
    return run.run_log(result, "fixtures")


def test_a_reported_total_of_zero_is_shown_as_zero(tmp_path):
    log = chargy_run_log()
    log["modules"]["tariffs"].update(records=0, reported=0)
    (tmp_path / "chargy.json").write_text(json.dumps(log))
    page = transparency.render_html(
        transparency.build(load_registry(), transparency.load_runs(tmp_path))
    )
    assert "tariffs: 0 records of 0 reported" in page


def test_a_failed_run_is_shown_as_failed(tmp_path):
    log = run.failure_log("chargy", "live", "gave up on https://char.gy/x: HTTP 503", NOW_UTC)
    (tmp_path / "chargy.json").write_text(json.dumps(log))
    page = transparency.render_html(
        transparency.build(load_registry(), transparency.load_runs(tmp_path))
    )
    assert "Run failed" in page and "HTTP 503" in page


def test_a_malformed_run_log_is_refused(tmp_path, capsys):
    (tmp_path / "chargy.json").write_text(json.dumps({"operator": "chargy", "mode": "live"}))
    out = tmp_path / "build"
    assert transparency.main(["--runs", str(tmp_path), "--out", str(out)]) == 1
    assert "chargy.json is not a valid run log" in capsys.readouterr().err


def test_a_run_log_with_extra_fields_is_refused(tmp_path, capsys):
    log = chargy_run_log()
    log["raw_url"] = "https://example.invalid/locations?apiKey=never-published"
    (tmp_path / "chargy.json").write_text(json.dumps(log))
    assert transparency.main(["--runs", str(tmp_path), "--out", str(tmp_path / "out")]) == 1
    error = capsys.readouterr().err
    assert "raw_url" in error and "never-published" not in error
    assert not (tmp_path / "out").exists()


def test_a_run_log_must_be_named_after_its_operator(tmp_path):
    (tmp_path / "jolt.json").write_text(json.dumps(chargy_run_log()))
    with pytest.raises(ValueError, match=r"name it chargy\.json"):
        transparency.load_runs(tmp_path)


def test_a_run_log_for_an_unknown_operator_is_refused(tmp_path):
    log = chargy_run_log() | {"operator": "nobody"}
    (tmp_path / "nobody.json").write_text(json.dumps(log))
    with pytest.raises(ValueError, match="not in the registry: nobody"):
        transparency.build(load_registry(), transparency.load_runs(tmp_path))


def test_only_known_run_log_fields_are_published(tmp_path):
    (tmp_path / "chargy.json").write_text(json.dumps(chargy_run_log()))
    data = transparency.build(load_registry(), transparency.load_runs(tmp_path))
    chargy = next(op for op in data["operators"] if op["id"] == "chargy")
    assert set(chargy["latest_run"]) == set(run.RunLog.model_fields)


def test_long_issues_are_shortened_in_run_logs():
    log = run.failure_log("chargy", "live", "x" * 2000, NOW_UTC)
    assert len(log["error"]) == len(log["issues"][0]) == run.MAX_ISSUE_LENGTH
    assert log["issues"][0].endswith("...")


def test_runs_need_an_out_folder_so_the_committed_page_is_kept(tmp_path):
    with pytest.raises(SystemExit):
        transparency.main(["--runs", str(tmp_path)])
    (tmp_path / "logs").mkdir()
    (tmp_path / "logs" / "chargy.json").write_text(json.dumps(chargy_run_log()))
    before = transparency.PAGE_PATH.read_text(encoding="utf-8")
    out = tmp_path / "build"
    assert transparency.main(["--runs", str(tmp_path / "logs"), "--out", str(out)]) == 0
    assert "Latest run for each operator" in (out / "transparency" / "index.html").read_text()
    assert (out / "data" / "transparency.json").exists()
    assert transparency.PAGE_PATH.read_text(encoding="utf-8") == before


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
