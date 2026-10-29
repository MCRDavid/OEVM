"""Tests for the feed health page (pipeline/status.py, blueprint task 8). No network."""

import dataclasses
import html
import json
import re
import shutil
from datetime import UTC, datetime, timedelta
from html.parser import HTMLParser
from pathlib import Path

import jsonschema
import pytest

from pipeline import health, publish, run, status
from pipeline.registry import ROOT, load_registry
from pipeline.transparency import short_disclaimer
from schema.operator import neutral_text
from schema.published import Manifest, OperatorStatus, StatusFile
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
    for path in ("disclaimer", "data-licences", "privacy", "security", "report", "transparency"):
        assert f'href="../{path}/"' in page


def test_health_figures_are_counted_from_what_was_received(logs):
    logged = RunLog.model_validate_json((logs / "jolt.json").read_text())
    health = logged.health
    assert (health.locations, health.locations_in_uk) == (4, 4)
    assert (health.evses, health.evses_with_status) == (8, 7)  # one EVSE reports 'preparing'
    assert (health.connectors, health.connectors_with_tariff) == (6, 5)
    assert health.median_last_updated_days is None  # Jolt gives no last_updated
    chargy = RunLog.model_validate_json((logs / "chargy.json").read_text()).health
    # WORKING is not an OCPI 2.2.1 status, but the owner decided how it is shown
    # (nonstandard_statuses in operators/chargy.yaml), so it counts as a status.
    assert chargy.evses_with_status == chargy.evses == 4


def test_connectors_priced_from_a_related_feed_are_counted_on_their_own(logs):
    # PoGo Charge's connectors name tariffs only Evolt Network's feed holds; the owner
    # decided they may be priced from it (tariffs_from, ADR 0020), as the map does.
    def figures(operator_id: str) -> tuple[int, int, int]:
        h = RunLog.model_validate_json((logs / f"{operator_id}.json").read_text()).health
        return h.connectors, h.connectors_with_tariff, h.connectors_with_tariff_from_related

    assert figures("pogo_charge") == (16, 0, 13)
    assert figures("evolt") == (42, 39, 2)
    assert figures("chargeplace_scotland") == (14, 9, 2)
    assert figures("jolt") == (6, 5, 0)


def test_without_the_decision_or_the_related_feed_nothing_more_is_counted():
    operators = load_registry()
    results = {r.operator_id: r for r in run.run_fixtures(operators)}
    pogo = results["pogo_charge"]
    fetched = {i: r.tariffs for i, r in results.items()}
    assert health.health(pogo).connectors_with_tariff_from_related == 0
    undecided = operators["pogo_charge"].model_copy(update={"tariffs_from": None})
    assert publish.related_for(undecided, pogo, fetched) == {}
    # Evolt Network's fetch failed or was not in this run.
    without_evolt = {i: t for i, t in fetched.items() if i != "evolt"}
    related = publish.related_for(operators["pogo_charge"], pogo, without_evolt)
    assert related == {}
    related = publish.related_for(operators["pogo_charge"], pogo, fetched)
    assert health.health(pogo, related).connectors_with_tariff_from_related == 13


def test_a_connector_naming_its_own_tariff_too_is_counted_once():
    # A connector that names a tariff found in its own operator's feed counts in the first
    # figure only, even if it also names one found only in a related feed (ADR 0020).
    operators = load_registry()
    results = {r.operator_id: r for r in run.run_fixtures(operators)}
    fetched = {i: r.tariffs for i, r in results.items()}
    cps = results["chargeplace_scotland"]
    related = publish.related_for(operators["chargeplace_scotland"], cps, fetched)
    own_id = cps.tariffs[0].id
    changed, locations = 0, []
    for location in cps.locations:
        evses = []
        for evse in location.evses:
            connectors = []
            for connector in evse.connectors:
                if not changed and any(i in related for i in connector.tariff_ids):
                    ids = [own_id, *connector.tariff_ids]
                    connector = connector.model_copy(update={"tariff_ids": ids})
                    changed += 1
                connectors.append(connector)
            evses.append(evse.model_copy(update={"connectors": connectors}))
        locations.append(location.model_copy(update={"evses": evses}))
    mixed = dataclasses.replace(cps, locations=locations)
    related = publish.related_for(operators["chargeplace_scotland"], mixed, fetched)
    figures = health.health(mixed, related)
    assert changed == 1
    assert (figures.connectors, figures.connectors_with_tariff) == (14, 10)
    assert figures.connectors_with_tariff_from_related == 1


def test_the_page_shows_connectors_priced_from_a_related_feed(logs, tmp_path):
    page, data = render(logs, tmp_path)
    text, _ = text_of(page)
    assert "0 of 16 (0%) from its own feed 13 more from a related operator\u2019s feed" in text
    assert "39 of 42 (92.9%) from its own feed 2 more from a related operator" in text
    assert "5 of 6 (83.3%)" in text and "5 of 6 (83.3%) from its own feed" not in text
    assert "the map prices those connectors from that exact tariff, never by its name" in text
    assert "a related operator fetched in the same run" in text
    (point,) = data["operators"]["pogo_charge"]["history"]
    assert point["connectors_with_tariff_pct"] == 0
    assert point["connectors_with_tariff_from_related_pct"] == 81.2
    assert "0% from its own feed, 81.2% from a related operator\u2019s feed" in text
    (point,) = data["operators"]["jolt"]["history"]
    assert point["connectors_with_tariff_from_related_pct"] == 0


def test_without_related_prices_the_page_has_no_note_and_old_logs_still_load(logs, tmp_path):
    # Run logs written before this count existed have no such field.
    old = tmp_path / "old"
    old.mkdir()
    for path in logs.glob("*.json"):
        log = json.loads(path.read_text())
        del log["health"]["connectors_with_tariff_from_related"]
        (old / path.name).write_text(json.dumps(log))
    page, data = render(old, tmp_path / "out")
    text, _ = text_of(page)
    assert "from its own feed" not in text and "related operator" not in text
    assert "0 of 16 (0%)" in text
    assert (
        data["operators"]["pogo_charge"]["latest"]["health"]["connectors_with_tariff_from_related"]
        == 0
    )
    jsonschema.validate(data, SCHEMA)


def test_the_note_stays_while_the_history_shows_related_prices(logs, tmp_path):
    # As on a day Evolt Network's fetch fails: no latest run counts any, but earlier days
    # in the 30-day tables still do, so the note explaining them stays.
    render(logs, tmp_path / "a")
    later = tmp_path / "later"
    later.mkdir()
    when = NOW + timedelta(days=1)
    for path in logs.glob("*.json"):
        log = json.loads(path.read_text())
        fetched = datetime.fromisoformat(log["fetched_at"].replace("Z", "+00:00"))
        log["fetched_at"] = (fetched + timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        log["health"]["connectors_with_tariff_from_related"] = 0
        (later / path.name).write_text(json.dumps(log))
    page, data = render(later, tmp_path / "b", tmp_path / "a" / "data" / "status.json", when)
    text, _ = text_of(page)
    shares = [
        p["connectors_with_tariff_from_related_pct"]
        for p in data["operators"]["pogo_charge"]["history"]
    ]
    assert shares == [81.2, 0]
    assert "13 more from a related operator" not in text
    assert "0% from its own feed, 81.2% from a related operator\u2019s feed" in text
    assert "the map prices those connectors from that exact tariff, never by its name" in text


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
    # Fixed times on one day, so the test does not depend on when it runs (an hour after
    # 23:00 UTC is the next day).
    earlier = tmp_path / "earlier"
    shutil.copytree(logs, earlier)
    log = json.loads((earlier / "jolt.json").read_text())
    log["fetched_at"] = (NOW - timedelta(hours=2)).strftime("%Y-%m-%dT%H:%M:%SZ")
    (earlier / "jolt.json").write_text(json.dumps(log))
    _, first = render(earlier, tmp_path / "a")
    later = tmp_path / "later"
    later.mkdir()
    log["fetched_at"] = (NOW - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
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
    # The fixture run is stamped with the real clock, so the failure must come after it.
    when = datetime.now(UTC) + timedelta(days=1)
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
    assert text_of(page)[0].count("Not fetched yet") == len(data["operators"]) == 45


def latest(log: dict) -> OperatorStatus:
    return OperatorStatus(name="Jolt", latest=RunLog.model_validate(log), history=[])


def test_each_switched_on_operator_gets_a_colour_from_its_latest_run(logs):
    good = json.loads((logs / "jolt.json").read_text())
    when = datetime.fromisoformat(good["fetched_at"].replace("Z", "+00:00"))
    assert status.colour(OperatorStatus(name="Jolt", history=[]), when) == status.GREY
    assert status.colour(latest(good), when) == status.GREEN
    # Still green two days on; older than that, a missed daily fetch shows yellow.
    assert status.colour(latest(good), when + timedelta(days=2)) == status.GREEN
    assert status.colour(latest(good), when + timedelta(days=2, hours=1)) == status.YELLOW
    assert status.colour(latest(good | {"complete": False}), when) == status.YELLOW
    nothing = good | {"kept": {"locations": 0, "tariffs": 0}}
    assert status.colour(latest(nothing), when) == status.RED
    failed = run.failure_log("jolt", "live", "HTTP 503", when)
    assert status.colour(latest(failed), when) == status.RED
    yesterday = when - timedelta(days=1)
    kept = run.failure_log("jolt", "live", "HTTP 503", when, kept_copy=(yesterday, 4))
    assert status.colour(latest(kept), when) == status.YELLOW
    empty = run.failure_log("jolt", "live", "HTTP 503", when, kept_copy=(yesterday, 0))
    assert status.colour(latest(empty), when) == status.RED


def test_every_operator_has_a_circle_and_switched_off_ones_are_listed(logs, tmp_path):
    page, data = render(logs, tmp_path)
    registry = load_registry()
    for operator_id, config in registry.items():
        name = html.escape(config.display_name)
        if config.enabled:
            assert operator_id in data["operators"]
            assert re.search(
                rf'<th scope="row"><span class="circle"[^>]*>.</span> {re.escape(name)}</th>', page
            )
        else:
            assert operator_id not in data["operators"]  # status.json is unchanged
            assert f"{status.CIRCLES[status.GREY]}</span> {name}</li>" in page
    text, _ = text_of(page)
    assert f"Of {len(registry)} operators in the registry:" in text
    for shade in status.CIRCLES:
        assert f"<strong>{status.LABELS[shade]}</strong>:" in page  # the key
    # The labels are read out, not just shown as colours.
    assert 'role="img" aria-label="Working"' in page
    assert 'aria-label="Some problems"' in page  # the char.gy fixtures stop after two pages


OVERVIEW_ITEM = re.compile(
    r'<li><span class="circle" role="img" aria-label="([^"]+)"[^>]*>(.)</span> (.*?)</li>'
)


def test_the_overview_lists_every_operator_by_name_with_its_circle(logs, tmp_path):
    page, _ = render(logs, tmp_path)
    overview = re.search(r'<ul class="off overview">(.*?)</ul>', page)
    assert overview and overview.start() < page.index("Latest runs")
    items = OVERVIEW_ITEM.findall(overview.group(1))
    registry = load_registry()
    names = sorted((c.display_name for c in registry.values()), key=str.casefold)
    assert [html.unescape(name) for _, _, name in items] == names
    data = status.build(registry, status.load_runs(logs), None, NOW)
    by_name = {c.display_name: (i, c) for i, c in registry.items()}
    for label, circle, name in items:
        operator_id, config = by_name[html.unescape(name)]
        if config.enabled:
            shown = status.colour(data.operators[operator_id], NOW)
            assert (circle, label) == (status.CIRCLES[shown], status.LABELS[shown])
        else:
            assert (circle, label) == (status.CIRCLES[status.GREY], "Switched off")
    # An operator switched on but not fetched yet is grey, and says so.
    empty = tmp_path / "empty"
    empty.mkdir()
    page, _ = render(empty, tmp_path / "out")
    overview = re.search(r'<ul class="off overview">(.*?)</ul>', page)
    labels = [label for label, _, _ in OVERVIEW_ITEM.findall(overview.group(1))]
    assert labels.count("Not fetched yet") == sum(c.enabled for c in registry.values())


def test_the_detail_sections_stay_closed_until_opened(logs):
    page = status.render_html(
        status.build(load_registry(), status.load_runs(logs), None, NOW),
        [],
        ["Switched Off Example"],
        "The record of runs could not be read from GitHub when this page was built.",
        [],
    )
    headings = re.findall(r'<details class="section"><summary><h2([^>]*)>(.*?)</h2>', page)
    assert headings == [
        ("", "Latest runs"),
        ("", "Switched off"),
        (' id="daily-runs"', "How the daily fetch started"),
        ("", f"The last {status.HISTORY_DAYS} days"),
        (' id="private"', "Hidden on the map unless asked for"),
        (' id="copies"', "Shown from the network&rsquo;s own feed"),
    ]
    # Only the overview is open; every other heading is inside a closed section, and the
    # ids that other pages link to are on headings, which show while closed.
    assert "<details open" not in page
    assert re.findall(r"<h2[^>]*>(.*?)</h2>", page)[0] == "At a glance"
    assert len(re.findall(r"<h2", page)) == len(headings) + 1
    assert '<details class="colours"><summary>What the colours mean</summary>' in page
    assert "<script" not in page


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


# Locations hidden on the map unless asked for (ADR 0023)


@pytest.fixture(scope="module")
def published(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("published")
    assert run.main(["--fixtures", "--publish", str(out)]) == 0
    return out / "data" / "locations.geojson"


def test_the_page_lists_locations_marked_private_with_the_words_found(logs, published, tmp_path):
    out = tmp_path / "out"
    assert (
        status.main(
            [
                "--runs",
                str(logs),
                "--out",
                str(out),
                "--now",
                NOW.isoformat(),
                "--map",
                str(published),
            ]
        )
        == 0
    )
    page = (out / "status" / "index.html").read_text()
    text, _ = text_of(page)
    neutral_text(text)
    assert 'id="private"' in page and 'href="../transparency/#private"' in page
    assert "2 locations hidden unless asked for" in text
    assert (
        "Evolt Network Arthur House - Private Use Only Its name includes “Private Use Only”" in text
    )
    assert "PoGo Charge Swales Central Avenue Every charge point is marked for taxis only" in text


def test_without_the_map_file_the_page_says_so(logs, tmp_path):
    page, _ = render(logs, tmp_path)
    assert "The map files were not available when this page was built." in text_of(page)[0]


def test_a_missing_or_damaged_map_file_is_refused(logs, tmp_path):
    with pytest.raises(status.StatusError, match="does not exist"):
        status.outputs(logs, tmp_path / "out", None, NOW, tmp_path / "missing.geojson")
    broken = tmp_path / "broken.geojson"
    broken.write_text("{}")
    with pytest.raises(status.StatusError, match="not a valid map file"):
        status.outputs(logs, tmp_path / "out", None, NOW, broken)


def test_names_from_the_map_file_are_escaped(logs, published, tmp_path):
    layer = json.loads(published.read_text())
    feature = next(f for f in layer["features"] if f["properties"]["priv"])
    feature["properties"]["name"] = "<b>Private</b>"
    changed = tmp_path / "locations.geojson"
    changed.write_text(json.dumps(layer))
    (tmp_path / "manifest.json").write_bytes((published.parent / "manifest.json").read_bytes())
    page = status.outputs(logs, tmp_path / "out", None, NOW, changed)[
        tmp_path / "out" / "status" / "index.html"
    ]
    assert "<b>" not in page and "&lt;b&gt;Private&lt;/b&gt;" in page


# Locations left off as copies of a network's own feed (ADR 0027)


def test_the_page_says_when_no_copies_were_left_off(logs, published, tmp_path):
    page = status.outputs(logs, tmp_path / "out", None, NOW, published)[
        tmp_path / "out" / "status" / "index.html"
    ]
    text, _ = text_of(page)
    assert 'id="copies"' in page
    assert "No location in the latest map files was left off this way." in text


def test_the_page_lists_copies_left_off_with_their_ids(logs, published, tmp_path):
    (tmp_path / "locations.geojson").write_bytes(published.read_bytes())
    manifest = json.loads((published.parent / "manifest.json").read_text())
    ids = ["monta:GB:UFX:<b>1</b>", "monta:GB:UFX:2"]
    manifest["operators"]["monta"] |= {
        "replaced": 2,
        "replaced_ids": ids,
        "replaced_by": {"urban_fox": 2},
    }
    (tmp_path / "manifest.json").write_text(json.dumps(manifest))
    page = status.outputs(logs, tmp_path / "out", None, NOW, tmp_path / "locations.geojson")[
        tmp_path / "out" / "status" / "index.html"
    ]
    text, _ = text_of(page)
    neutral_text(text)
    assert "Monta Urban Fox 2" in text
    assert "<b>1" not in page and "monta:GB:UFX:&lt;b&gt;1&lt;/b&gt;" in page
    assert status.copy_rows(Manifest.model_validate(manifest), load_registry()) == [
        ("Monta", "Urban Fox", ids)
    ]


def test_a_missing_manifest_beside_the_map_file_is_refused(logs, published, tmp_path):
    (tmp_path / "locations.geojson").write_bytes(published.read_bytes())
    with pytest.raises(status.StatusError, match=r"manifest\.json does not exist"):
        status.outputs(logs, tmp_path / "out", None, NOW, tmp_path / "locations.geojson")
