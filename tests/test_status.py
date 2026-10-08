"""Tests for the feed health page (pipeline/status.py, blueprint task 8). No network."""

import json
import re
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

import jsonschema
import pytest

from pipeline import run, status
from pipeline.registry import ROOT, load_registry
from pipeline.transparency import short_disclaimer
from schema.operator import neutral_text
from schema.published import StatusFile
from schema.runlog import RunLog

NOW = datetime(2026, 10, 8, 13, 0, tzinfo=UTC)
SCHEMA = json.loads((ROOT / "schema" / "json" / "status.schema.json").read_text())


@pytest.fixture(scope="module")
def logs(tmp_path_factory) -> Path:
    folder = tmp_path_factory.mktemp("logs")
    assert run.main(["--fixtures", "--log-dir", str(folder)]) == 0
    return folder


def render(logs: Path, out: Path, previous: Path | None = None, now: datetime = NOW):
    files = status.outputs(logs, out, previous, now)
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    return files[out / "status" / "index.html"], json.loads(files[out / "data" / "status.json"])


class Text(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self.text: list[str] = []
        self.tags: list[str] = []

    def handle_starttag(self, tag, attrs):
        self.tags.append(tag)

    def handle_data(self, data):
        self.text.append(data)


def text_of(page: str) -> tuple[str, list[str]]:
    parser = Text()
    parser.feed(page)
    return " ".join(" ".join(parser.text).split()), parser.tags


def test_the_page_renders_from_fixtures_with_neutral_labels(logs, tmp_path):
    page, data = render(logs, tmp_path)
    text, tags = text_of(page)
    neutral_text(text)
    assert chr(0x2014) not in page and '<html lang="en-GB">' in page
    for name in ("char.gy", "GeniePoint", "Jolt"):
        assert name in text
    assert "Fetched, incomplete" in text  # the char.gy fixtures stop after two pages
    assert "4 of 4 (100%)" in text
    assert "they do not say whether anyone has met their legal duties" in text
    assert not {"script", "img", "iframe", "link"} & set(tags)
    jsonschema.validate(data, SCHEMA)


def test_the_page_shows_the_disclaimer_and_required_links(logs, tmp_path):
    page, _ = render(logs, tmp_path)
    assert short_disclaimer().replace('"', "&quot;") in page
    for path in ("DISCLAIMER.md", "DATA_LICENCES.md", "SECURITY.md"):
        assert path in page
    assert 'href="../transparency/"' in page
    assert 'href="../privacy/"' in page


def test_health_figures_are_counted_from_what_was_received(logs):
    logged = RunLog.model_validate_json((logs / "jolt.json").read_text())
    health = logged.health
    assert (health.locations, health.locations_in_uk) == (4, 4)
    assert (health.evses, health.evses_with_status) == (8, 7)  # one EVSE reports 'preparing'
    assert (health.connectors, health.connectors_with_tariff) == (6, 5)
    assert health.median_last_updated_days is None  # Jolt gives no last_updated
    chargy = RunLog.model_validate_json((logs / "chargy.json").read_text()).health
    assert chargy.evses_with_status == 0  # WORKING is not an OCPI 2.2.1 status


def test_history_keeps_one_run_a_day_for_30_days(logs, tmp_path):
    previous = None
    for day in range(35):
        when = NOW + timedelta(days=day)
        folder = tmp_path / f"logs{day}"
        folder.mkdir()
        log = json.loads((logs / "jolt.json").read_text())
        log["fetched_at"] = when.strftime("%Y-%m-%dT%H:%M:%SZ")
        (folder / "jolt.json").write_text(json.dumps(log))
        _, data = render(folder, tmp_path / str(day), previous, when)
        previous = tmp_path / str(day) / "data" / "status.json"
    history = data["operators"]["jolt"]["history"]
    dates = [point["date"] for point in history]
    assert len(history) == 30 and len(set(dates)) == 30
    assert dates[0] == (NOW + timedelta(days=5)).date().isoformat()
    assert dates[-1] == (NOW + timedelta(days=34)).date().isoformat()
    assert data["operators"]["chargy"]["history"] == []  # no run in these logs


def test_a_later_run_on_the_same_day_replaces_the_earlier_one(logs, tmp_path):
    _, first = render(logs, tmp_path / "a")
    log = json.loads((logs / "jolt.json").read_text())
    later = tmp_path / "later"
    later.mkdir()
    fetched = datetime.fromisoformat(log["fetched_at"].replace("Z", "+00:00")) + timedelta(hours=1)
    log |= {"fetched_at": fetched.strftime("%Y-%m-%dT%H:%M:%SZ")}
    log["kept"]["locations"] = 3
    (later / "jolt.json").write_text(json.dumps(log))
    _, second = render(later, tmp_path / "b", tmp_path / "a" / "data" / "status.json")
    history = second["operators"]["jolt"]["history"]
    assert [point["locations"] for point in history] == [3]
    assert second["operators"]["chargy"]["latest"] == first["operators"]["chargy"]["latest"]


def test_a_failed_run_is_shown_and_keeps_the_last_success(logs, tmp_path):
    render(logs, tmp_path / "a")
    failed = tmp_path / "failed"
    failed.mkdir()
    when = NOW + timedelta(days=1)
    log = run.failure_log("jolt", "live", "gave up on https://example.invalid: HTTP 503", when)
    (failed / "jolt.json").write_text(json.dumps(log))
    page, data = render(failed, tmp_path / "b", tmp_path / "a" / "data" / "status.json", when)
    jolt = data["operators"]["jolt"]
    assert jolt["last_attempt"] > jolt["last_success"]
    text, _ = text_of(page)
    assert "Fetch failed" in text and "HTTP 503" in text


def test_operators_with_no_run_are_not_fetched_yet(tmp_path):
    empty = tmp_path / "empty"
    empty.mkdir()
    page, data = render(empty, tmp_path / "out")
    assert text_of(page)[0].count("Not fetched yet") == len(data["operators"]) == 3


def test_the_committed_site_folder_is_never_written(logs):
    with pytest.raises(status.StatusError, match="not the committed site/ folder"):
        status.outputs(logs, ROOT / "site", None, NOW)


def test_text_from_run_logs_is_escaped(logs, tmp_path):
    log = json.loads((logs / "jolt.json").read_text())
    log["issues"] = ["<script>alert(1)</script>"]
    folder = tmp_path / "logs"
    folder.mkdir()
    (folder / "jolt.json").write_text(json.dumps(log))
    page, _ = render(folder, tmp_path / "out")
    assert "<script>" not in page and "&lt;script&gt;" in page


# Run log checks (moved from the transparency page)


def chargy_log(logs: Path) -> dict:
    return json.loads((logs / "chargy.json").read_text())


@pytest.mark.parametrize(
    ("change", "message"),
    [
        (lambda log: {"operator": "chargy", "mode": "live"}, "is not a valid run log"),
        (lambda log: log | {"raw_url": "https://example.invalid/?apiKey=x"}, "raw_url"),
    ],
    ids=["missing-fields", "extra-field"],
)
def test_malformed_run_logs_are_refused(logs, tmp_path, capsys, change, message):
    folder = tmp_path / "logs"
    folder.mkdir()
    (folder / "chargy.json").write_text(json.dumps(change(chargy_log(logs))))
    assert (
        status.main(
            ["--runs", str(folder), "--out", str(tmp_path / "out"), "--now", NOW.isoformat()]
        )
        == 1
    )
    error = capsys.readouterr().err
    assert message in error and "apiKey=x" not in error
    assert not (tmp_path / "out").exists()


def test_a_run_log_must_be_named_after_its_operator(logs, tmp_path):
    (tmp_path / "jolt.json").write_text(json.dumps(chargy_log(logs)))
    with pytest.raises(status.StatusError, match=r"name it chargy\.json"):
        status.load_runs(tmp_path)


def test_a_run_log_for_an_operator_not_switched_on_is_refused(logs, tmp_path):
    (tmp_path / "gridserve.json").write_text(
        json.dumps(chargy_log(logs) | {"operator": "gridserve"})
    )
    with pytest.raises(status.StatusError, match="not switched on: gridserve"):
        status.build(load_registry(), status.load_runs(tmp_path), None, NOW)


def test_long_issues_are_shortened_in_run_logs():
    log = run.failure_log("chargy", "live", "x" * 2000, NOW)
    assert len(log["error"]) == len(log["issues"][0]) == run.MAX_ISSUE_LENGTH
    assert log["issues"][0].endswith("...")


def test_the_command_line_writes_both_files(logs, tmp_path, capsys):
    out = tmp_path / "out"
    assert status.main(["--runs", str(logs), "--out", str(out), "--now", NOW.isoformat()]) == 0
    assert (out / "status" / "index.html").exists()
    StatusFile.model_validate_json((out / "data" / "status.json").read_text())
    assert re.search(r"Wrote .*status\.json", capsys.readouterr().out)
