"""How the daily fetch starts, once a day, and the record of its runs (ADR 0024).

No test calls GitHub: the API is a dictionary of answers.
"""

import json
import re
import tomllib
from datetime import UTC, date, datetime, timedelta

import pytest
import yaml

from pipeline import daily_runs, status
from pipeline.daily_runs import (
    CANCELLED,
    DEPLOY_FAILED,
    FAILED,
    HAND,
    OPERATOR_MISSING,
    PUBLISHED,
    RUNNING,
    SCHEDULE,
    SKIPPED,
    THIS_RUN,
    TIMER,
)
from pipeline.project import REPOSITORY_URL
from pipeline.registry import ROOT

REPO = "MCRDavid/OEVM"
NOW = datetime(2026, 10, 12, 4, 30, tzinfo=UTC)
CURRENT = 900
WORKFLOW = ROOT / ".github" / "workflows" / "fetch-daily.yml"


def make_run(run_id, created, event="schedule", title=None, state="completed", end="success"):
    if title is None:
        title = {
            "schedule": "Fetch daily (GitHub schedule 47 4 * * *)",
            "timer": "Fetch daily (Cloudflare timer)",
        }.get(event, "Fetch daily (by hand)")
    return {
        "id": run_id,
        "run_number": run_id,
        "event": "workflow_dispatch" if event in ("timer", "hand") else event,
        "display_title": title,
        "status": state,
        "conclusion": end if state == "completed" else None,
        "created_at": created,
        "html_url": f"https://github.com/{REPO}/actions/runs/{run_id}",
    }


def make_jobs(fetch="success", deploy="success", report="skipped"):
    jobs = [{"name": daily_runs.CHECK_JOB, "conclusion": "success"}]
    if fetch is not None:
        jobs.append({"name": daily_runs.FETCH_JOB, "conclusion": fetch})
    if deploy is not None:
        jobs.append({"name": "Deploy / Build and deploy to GitHub Pages", "conclusion": deploy})
    jobs.append({"name": daily_runs.REPORT_JOB, "conclusion": report})
    return jobs


class FakeGitHub:
    """Answers the two API paths the module asks for, and counts the questions."""

    def __init__(self, runs, jobs=None, fail=False):
        self.runs, self.jobs, self.fail, self.asked = runs, jobs or {}, fail, []

    def __call__(self, path):
        self.asked.append(path)
        if self.fail:
            raise daily_runs.DailyRunsError("GitHub did not answer")
        listing = re.fullmatch(rf"repos/{REPO}/actions/workflows/fetch-daily\.yml/runs\?(.*)", path)
        if listing:
            page = int(re.search(r"(?:^|&)page=(\d+)", listing.group(1)).group(1))
            assert "branch=main" in listing.group(1)
            return {"workflow_runs": self.runs[(page - 1) * 100 : page * 100]}
        found = re.fullmatch(rf"repos/{REPO}/actions/runs/(\d+)/jobs\?per_page=100", path)
        assert found, path
        return {"jobs": self.jobs.get(int(found.group(1)), [])}


# How a run started and what it did


@pytest.mark.parametrize(
    ("run", "expected"),
    [
        (make_run(1, "2026-10-12T10:40:00Z"), (SCHEDULE, "47 4 * * *")),
        # Before 12 October 2026 the title did not name the schedule; there was only one.
        (make_run(1, "2026-10-11T10:48:25Z", title="Fetch daily"), (SCHEDULE, "17 4 * * *")),
        (make_run(1, "2026-10-12T04:17:05Z", event="timer"), (TIMER, None)),
        (make_run(1, "2026-10-12T09:00:00Z", event="hand"), (HAND, None)),
        (make_run(1, "2026-10-10T02:05:37Z", event="hand", title="Fetch daily"), (HAND, None)),
    ],
)
def test_how_a_run_started_comes_from_its_event_and_title(run, expected):
    assert daily_runs.started_by(run) == expected


@pytest.mark.parametrize(
    ("end", "jobs", "expected"),
    [
        ("success", make_jobs(), PUBLISHED),
        ("failure", make_jobs(report="failure"), OPERATOR_MISSING),
        ("failure", make_jobs(deploy="failure"), DEPLOY_FAILED),
        ("success", make_jobs(fetch="skipped", deploy="skipped"), SKIPPED),
        ("failure", make_jobs(fetch="failure", deploy="skipped"), FAILED),
        ("failure", make_jobs(fetch="timed_out", deploy="skipped"), FAILED),
        ("cancelled", make_jobs(fetch="cancelled", deploy="skipped"), CANCELLED),
        # Cancelled while waiting behind another run, before any job started.
        ("cancelled", [], CANCELLED),
        # The check itself failed, so the fetch was skipped: not "already ran".
        ("failure", make_jobs(fetch="skipped", deploy="skipped"), FAILED),
    ],
)
def test_what_a_run_did_comes_from_its_jobs(end, jobs, expected):
    run = make_run(5, "2026-10-12T04:17:00Z", end=end)
    assert daily_runs.outcome(run, jobs, CURRENT) == expected


def test_a_run_still_going_and_the_current_run_are_named_as_such():
    going = make_run(5, "2026-10-12T04:17:00Z", state="in_progress")
    assert daily_runs.outcome(going, [], CURRENT) == RUNNING
    assert daily_runs.outcome(make_run(CURRENT, "2026-10-12T04:17:00Z"), [], CURRENT) == THIS_RUN


@pytest.mark.parametrize(
    ("cron", "started", "late"),
    [
        ("17 4 * * *", "2026-10-11T10:48:25Z", timedelta(hours=6, minutes=31, seconds=25)),
        ("47 4 * * *", "2026-10-12T04:50:00Z", timedelta(minutes=3)),
        # A late-evening schedule that started after midnight belongs to the day before.
        ("47 22 * * *", "2026-10-12T01:47:00Z", timedelta(hours=3)),
    ],
)
def test_the_delay_is_measured_from_the_time_set(cron, started, late):
    run = daily_runs.DailyRun(1, 1, daily_runs._time(started), SCHEDULE, cron, PUBLISHED, "")
    assert run.delay == late


def test_only_daily_schedules_are_measured():
    assert daily_runs.scheduled_time("*/5 * * * *", NOW) is None
    assert daily_runs.scheduled_time("61 4 * * *", NOW) is None
    timer = daily_runs.DailyRun(1, 1, NOW, TIMER, None, PUBLISHED, "")
    assert timer.delay is None


@pytest.mark.parametrize(
    ("value", "words"),
    [
        (timedelta(minutes=4), "4 min"),
        (timedelta(hours=1), "1 h"),
        (timedelta(hours=6, minutes=18, seconds=40), "6 h 19 min"),
    ],
)
def test_delays_read_as_hours_and_minutes(value, words):
    assert daily_runs.duration(value) == words


# The check: one fetch a day


def check(github, event="schedule", how=""):
    return daily_runs.should_fetch(github, REPO, event, how, NOW.date(), CURRENT)


def test_a_run_started_by_hand_always_fetches_without_asking():
    github = FakeGitHub([make_run(1, "2026-10-12T04:17:00Z")], {1: make_jobs()})
    fetch, why = check(github, event="workflow_dispatch", how="hand")
    assert fetch and "by hand" in why
    assert github.asked == []


@pytest.mark.parametrize(("event", "how"), [("schedule", ""), ("workflow_dispatch", "timer")])
def test_a_timer_or_schedule_run_stops_when_today_has_been_published(event, how):
    runs = [
        make_run(CURRENT, "2026-10-12T04:47:00Z", state="in_progress"),
        make_run(7, "2026-10-12T04:17:03Z", event="timer"),
    ]
    fetch, why = check(FakeGitHub(runs, {7: make_jobs()}), event, how)
    assert not fetch
    assert "Run 7 (Cloudflare timer) already fetched and published today (2026-10-12)" in why


def test_an_operator_left_off_the_map_still_counts_as_published():
    runs = [make_run(7, "2026-10-12T04:17:03Z", event="timer", end="failure")]
    fetch, _ = check(FakeGitHub(runs, {7: make_jobs(report="failure")}))
    assert not fetch


@pytest.mark.parametrize(
    "jobs",
    [
        make_jobs(fetch="skipped", deploy="skipped"),
        make_jobs(fetch="failure", deploy="skipped"),
        # Fetched, but the site was not updated: the next try fetches and deploys again.
        make_jobs(deploy="failure"),
    ],
)
def test_a_run_that_did_not_publish_today_does_not_stop_the_next(jobs):
    runs = [make_run(7, "2026-10-12T04:17:03Z", event="timer", end="failure")]
    fetch, _ = check(FakeGitHub(runs, {7: jobs}))
    assert fetch


def test_yesterdays_run_does_not_count_and_older_pages_are_not_read():
    runs = [make_run(6, "2026-10-11T23:59:59Z", event="hand")]
    github = FakeGitHub(runs, {6: make_jobs()})
    fetch, why = check(github)
    assert fetch and "No run has fetched and published today" in why
    assert len(github.asked) == 1  # the list only; no jobs for yesterday's run


def test_if_github_cannot_be_asked_the_run_fetches_anyway():
    fetch, why = check(FakeGitHub([], fail=True))
    assert fetch and "Could not check" in why


def test_the_check_writes_its_answer_for_the_next_job(tmp_path, monkeypatch, capsys):
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    runs = [make_run(7, "2026-10-12T04:17:03Z", event="timer")]
    args = ["check", "--event", "schedule", "--repo", REPO, "--run-id", str(CURRENT)]
    code = daily_runs.main(
        [*args, "--now", NOW.isoformat()], get=FakeGitHub(runs, {7: make_jobs()})
    )
    assert code == 0
    assert output.read_text() == "fetch=false\n"
    assert "stops without fetching" in capsys.readouterr().out


# The record for the feed health page


def history():
    """Runs from 8 to 12 October 2026, newest first, as GitHub lists them."""
    runs = [
        make_run(CURRENT, "2026-10-12T04:17:02Z", event="timer", state="in_progress"),
        make_run(8, "2026-10-11T10:48:25Z", title="Fetch daily"),
        make_run(7, "2026-10-10T10:35:41Z", title="Fetch daily"),
        make_run(6, "2026-10-10T02:05:37Z", event="hand", title="Fetch daily"),
        make_run(4, "2026-10-09T11:18:39Z", title="Fetch daily"),
        make_run(3, "2026-10-08T23:41:31Z", event="hand", title="Fetch daily"),
    ]
    jobs = {
        8: make_jobs(),
        7: make_jobs(),
        6: make_jobs(),
        4: make_jobs(),
        3: make_jobs(report="failure"),
    }
    runs[-1]["conclusion"] = "failure"
    return runs, jobs


def test_the_record_lists_each_run_with_how_it_started_and_what_it_did():
    runs, jobs = history()
    record = daily_runs.collect(FakeGitHub(runs, jobs), REPO, NOW, CURRENT)
    assert record.since == date(2026, 10, 8)  # the first run; nothing earlier exists
    got = [(r.number, r.started_by, r.outcome) for r in record.runs]
    assert got == [
        (3, HAND, OPERATOR_MISSING),
        (4, SCHEDULE, PUBLISHED),
        (6, HAND, PUBLISHED),
        (7, SCHEDULE, PUBLISHED),
        (8, SCHEDULE, PUBLISHED),
        (CURRENT, TIMER, THIS_RUN),
    ]


def test_the_record_covers_30_days_when_runs_go_back_further():
    runs = [make_run(2, "2026-10-01T04:17:00Z"), make_run(1, "2026-09-01T04:17:00Z")]
    record = daily_runs.collect(FakeGitHub(runs, {2: make_jobs()}), REPO, NOW, CURRENT)
    assert record.since == date(2026, 9, 13)
    assert [r.number for r in record.runs] == [2]


def test_the_summary_counts_days_and_github_schedule_delays():
    runs, jobs = history()
    summary = daily_runs.summarise(daily_runs.collect(FakeGitHub(runs, jobs), REPO, NOW, CURRENT))
    assert (summary.days, summary.days_updated) == (5, 5)
    assert (summary.schedule_days, summary.schedule_runs, summary.schedule_on_time) == (3, 3, 0)
    # 7 h 01 min, 6 h 18 min and 6 h 31 min late on 9, 10 and 11 October 2026.
    assert daily_runs.duration(summary.schedule_median_delay) == "6 h 31 min"
    assert (summary.timer_since, summary.timer_span, summary.timer_days) == (NOW.date(), 1, 1)


def test_the_record_round_trips_through_its_file(tmp_path):
    runs, jobs = history()
    out = tmp_path / "record" / "daily-runs.json"
    args = ["record", "--out", str(out), "--repo", REPO, "--run-id", str(CURRENT)]
    assert daily_runs.main([*args, "--now", NOW.isoformat()], get=FakeGitHub(runs, jobs)) == 0
    loaded = daily_runs.load_record(out)
    assert loaded == daily_runs.collect(FakeGitHub(runs, jobs), REPO, NOW, CURRENT)
    assert json.loads(out.read_text())["since"] == "2026-10-08"


def test_when_github_cannot_be_asked_the_record_is_left_out_and_the_run_goes_on(tmp_path, capsys):
    out = tmp_path / "daily-runs.json"
    args = ["record", "--out", str(out), "--repo", REPO, "--run-id", "1"]
    assert daily_runs.main(args, get=FakeGitHub([], fail=True)) == 0
    assert not out.exists()
    assert "::warning::" in capsys.readouterr().out


@pytest.mark.parametrize(
    "change",
    [
        lambda d: d.pop("since"),
        lambda d: d["runs"][0].update(outcome="great"),
        lambda d: d["runs"][0].update(started_by="someone"),
        lambda d: d["runs"][0].update(url="https://example.org/run"),
    ],
)
def test_a_damaged_record_is_refused(tmp_path, change):
    runs, jobs = history()
    data = json.loads(daily_runs.to_json(daily_runs.collect(FakeGitHub(runs, jobs), REPO, NOW, 1)))
    change(data)
    path = tmp_path / "daily-runs.json"
    path.write_text(json.dumps(data))
    with pytest.raises(daily_runs.DailyRunsError):
        daily_runs.load_record(path)


# On the feed health page


@pytest.fixture
def logs(tmp_path_factory):
    from pipeline import run

    folder = tmp_path_factory.mktemp("logs")
    assert run.main(["--fixtures", "--log-dir", str(folder)]) == 0
    return folder


def page_with(logs, tmp_path, record_file):
    files = status.outputs(logs, tmp_path / "build", None, NOW, None, record_file)
    return files[tmp_path / "build" / "status" / "index.html"]


def test_the_feed_health_page_shows_how_the_daily_fetch_started(logs, tmp_path):
    runs, jobs = history()
    path = tmp_path / "daily-runs.json"
    path.write_text(
        daily_runs.to_json(daily_runs.collect(FakeGitHub(runs, jobs), REPO, NOW, CURRENT))
    )
    page = page_with(logs, tmp_path, path)
    assert '<h2 id="daily-runs">How the daily fetch started</h2>' in page
    assert "Days the map was updated: 5 of 5, since 8 October 2026." in page
    assert (
        "started a run on 3 of 5 days. 0 of its 3 runs started within 1 h of the time set" in page
    )
    assert "the median delay was 6 h 31 min." in page
    assert (
        "The Cloudflare timer started a run on 1 of 1 days since its first run on 12 October"
        in page
    )
    assert f'<a href="https://github.com/{REPO}/actions/runs/8">run 8</a>' in page
    assert "Fetched; this run built this page" in page


def test_the_page_says_when_the_record_could_not_be_read(logs, tmp_path):
    page = page_with(logs, tmp_path, tmp_path / "missing.json")
    assert "could not be read from GitHub" in page


def test_without_a_record_the_section_is_left_out(logs, tmp_path):
    assert 'id="daily-runs"' not in page_with(logs, tmp_path, None)


def test_days_with_no_run_are_listed(logs, tmp_path):
    runs = [make_run(4, "2026-10-09T11:18:39Z", title="Fetch daily")]
    path = tmp_path / "daily-runs.json"
    path.write_text(
        daily_runs.to_json(
            daily_runs.collect(FakeGitHub(runs, {4: make_jobs()}), REPO, NOW, CURRENT)
        )
    )
    page = page_with(logs, tmp_path, path)
    assert page.count("No run</td>") == 3  # 10, 11 and 12 October
    assert "Days the map was updated: 1 of 4" in page


# The workflow and the timer agree


def _workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def _crons() -> list[str]:
    on = _workflow()[True]  # YAML reads the key "on" as True
    return [entry["cron"] for entry in on["schedule"]]


def _timer_crons() -> list[str]:
    return tomllib.loads((ROOT / "relay" / "wrangler.toml").read_text())["triggers"]["crons"]


def test_every_start_time_is_daily_and_away_from_the_top_of_the_hour():
    for cron in [*_crons(), *_timer_crons()]:
        assert daily_runs.scheduled_time(cron, NOW) is not None, cron
        assert not cron.startswith(("0 ", "00 ")), cron
    # GitHub's schedule is the backup, so it comes after the timer's first try each day.
    first = min(daily_runs.scheduled_time(c, NOW.replace(hour=23)) for c in _timer_crons())
    assert all(daily_runs.scheduled_time(c, NOW.replace(hour=23)) > first for c in _crons())
    assert len(_timer_crons()) <= 5  # Cloudflare's free plan, per account


def test_the_timer_starts_this_workflow_on_main_as_the_timer():
    worker = (ROOT / "relay" / "worker.js").read_text(encoding="utf-8")
    owner_repo = REPOSITORY_URL.removeprefix("https://github.com/")
    assert (
        f"api.github.com/repos/{owner_repo}/actions/workflows/{WORKFLOW.name}/dispatches" in worker
    )
    assert 'started_by: "timer"' in worker
    started_by = _workflow()[True]["workflow_dispatch"]["inputs"]["started_by"]
    assert started_by["options"] == [HAND, TIMER] and started_by["default"] == HAND


def test_the_run_title_says_how_each_run_started():
    title = _workflow()["run-name"]
    assert "format('Fetch daily (GitHub schedule {0})', github.event.schedule)" in title
    assert "'Fetch daily (Cloudflare timer)'" in title
    run = make_run(1, "2026-10-12T10:00:00Z", title="Fetch daily (GitHub schedule 47 10 * * *)")
    assert daily_runs.started_by(run) == (SCHEDULE, "47 10 * * *")


def test_only_the_first_timer_or_schedule_run_each_day_fetches():
    jobs = _workflow()["jobs"]
    check_job = jobs["check"]
    assert check_job["name"] == daily_runs.CHECK_JOB
    assert check_job["permissions"] == {"contents": "read", "actions": "read"}
    step = next(s for s in check_job["steps"] if s.get("id") == "check")
    # Standard library only: the check runs before anything is installed.
    assert step["run"].startswith("python3 -m pipeline.daily_runs check")
    assert jobs["fetch"]["name"] == daily_runs.FETCH_JOB
    assert jobs["fetch"]["needs"] == "check"
    assert "needs.check.outputs.fetch == 'true'" in jobs["fetch"]["if"]
    assert jobs["report"]["name"] == daily_runs.REPORT_JOB
    assert jobs["deploy"]["name"] + " / " == daily_runs.DEPLOY_JOB_PREFIX


def test_the_daily_fetch_records_its_runs_on_the_feed_health_page():
    steps = _workflow()["jobs"]["fetch"]["steps"]
    names = [s.get("name", "") for s in steps]
    record = names.index("Read how the daily fetch started over the last 30 days")
    page = names.index("Build the feed health page")
    assert record < page
    assert "--out record/daily-runs.json" in steps[record]["run"]
    assert "--daily-runs record/daily-runs.json" in steps[page]["run"]


def test_the_check_needs_nothing_outside_the_standard_library():
    source = (ROOT / "pipeline" / "daily_runs.py").read_text(encoding="utf-8")
    imported = set(re.findall(r"^(?:from|import) (\w+)", source, flags=re.MULTILINE))
    assert imported <= {
        "argparse",
        "json",
        "os",
        "re",
        "statistics",
        "sys",
        "urllib",
        "collections",
        "dataclasses",
        "datetime",
        "pathlib",
    }
