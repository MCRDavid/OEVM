"""Keeping every host's gap between one run and the next (pipeline/refresh_runs.py).

No test calls GitHub: the API is a dictionary of answers. No test sleeps.
"""

import re
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta

import pytest
import yaml

from adapters.http import required_gap
from pipeline import daily_runs, refresh, refresh_runs
from pipeline.registry import ROOT, load_registry

REPO = "MCRDavid/OEVM"
NOW = datetime(2026, 11, 12, 5, 30, 20, tzinfo=UTC)
CURRENT = 900
FETCH, REFRESH = "fetch-daily.yml", "refresh-statuses.yml"
WORKFLOWS = ROOT / ".github" / "workflows"


def make_run(run_id, updated, state="completed"):
    return {
        "id": run_id,
        "run_number": run_id,
        "status": state,
        "conclusion": "success" if state == "completed" else None,
        "created_at": updated,
        "updated_at": updated,
    }


def feed_job(workflow, ended, conclusion="success"):
    return [
        {"name": "Some other job", "conclusion": "success", "completed_at": "2030-01-01T00:00:00Z"},
        {"name": refresh_runs.FEED_JOBS[workflow], "conclusion": conclusion, "completed_at": ended},
    ]


class FakeGitHub:
    """Answers the two API paths the module asks for, and keeps the questions."""

    def __init__(self, fetches=(), refreshes=(), jobs=None, fail=False):
        self.runs = {FETCH: list(fetches), REFRESH: list(refreshes)}
        self.jobs, self.fail, self.asked = jobs or {}, fail, []

    def __call__(self, path):
        self.asked.append(path)
        if self.fail:
            raise daily_runs.DailyRunsError("GitHub did not answer")
        listing = re.fullmatch(rf"repos/{REPO}/actions/workflows/([\w.-]+)/runs\?(.*)", path)
        if listing:
            assert "branch=main" in listing.group(2)
            return {"workflow_runs": self.runs[listing.group(1)]}
        found = re.fullmatch(rf"repos/{REPO}/actions/runs/(\d+)/jobs\?per_page=100", path)
        assert found, path
        return {"jobs": self.jobs.get(int(found.group(1)), [])}

    @property
    def jobs_asked(self):
        return [int(m.group(1)) for p in self.asked if (m := re.search(r"/runs/(\d+)/jobs", p))]


def run_main(command, github, **kwargs):
    args = [command, "--repo", REPO, "--run-id", str(CURRENT), "--now", NOW.isoformat()]
    return refresh_runs.main(args, get=github, **kwargs)


# The check: a refresh never waits behind another run


def test_a_refresh_goes_ahead_when_every_other_run_has_finished():
    github = FakeGitHub(
        fetches=[make_run(1, "2026-11-12T04:36:00Z")],
        refreshes=[make_run(CURRENT, "2026-11-12T05:30:05Z", state="in_progress")],
    )
    refresh_now, why = refresh_runs.should_refresh(github, REPO, CURRENT)
    assert refresh_now and "refreshes" in why
    # Two questions, and no run's jobs: the check is quick.
    assert len(github.asked) == 2


@pytest.mark.parametrize("state", ["queued", "in_progress", "pending", "waiting", "requested"])
@pytest.mark.parametrize("workflow", [FETCH, REFRESH])
def test_a_refresh_stops_while_a_fetch_or_another_refresh_has_not_finished(workflow, state):
    other = [make_run(7, "2026-11-12T05:29:00Z", state=state)]
    github = FakeGitHub(**{"fetches" if workflow == FETCH else "refreshes": other})
    refresh_now, why = refresh_runs.should_refresh(github, REPO, CURRENT)
    assert not refresh_now
    assert f"{refresh_runs.WORKFLOW_NAMES[workflow]} run 7 has not finished" in why
    assert "without asking any feed" in why


def test_a_refresh_stops_when_github_cannot_be_asked():
    # Unlike the daily fetch's check, which fetches anyway: a missed refresh costs an
    # hour of statuses, and asking a host too soon is never worth that.
    refresh_now, why = refresh_runs.should_refresh(FakeGitHub(fail=True), REPO, CURRENT)
    assert not refresh_now and "asks no feed" in why


def test_the_check_writes_its_answer_for_the_next_job(tmp_path, monkeypatch, capsys):
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert run_main("check", FakeGitHub()) == 0
    busy = FakeGitHub(fetches=[make_run(7, "2026-11-12T05:29:00Z", state="in_progress")])
    assert run_main("check", busy) == 0
    assert output.read_text() == "refresh=true\nrefresh=false\n"
    assert "Fetch daily run 7 has not finished" in capsys.readouterr().out


# When the last run stopped asking feeds


def test_the_last_end_is_the_latest_feed_job_of_either_workflow():
    github = FakeGitHub(
        fetches=[make_run(1, "2026-11-12T04:38:00Z")],
        refreshes=[make_run(2, "2026-11-12T03:46:00Z")],
        jobs={
            1: feed_job(FETCH, "2026-11-12T04:36:30Z"),
            2: feed_job(REFRESH, "2026-11-12T03:44:00Z"),
        },
    )
    # The feed job's own end, not the run's, which a deploy makes later.
    assert refresh_runs.last_ended(github, REPO, CURRENT) == datetime(
        2026, 11, 12, 4, 36, 30, tzinfo=UTC
    )
    # The older run ended before that job did, so its jobs are not asked for.
    assert github.jobs_asked == [1]


def test_a_run_that_skipped_its_feed_job_asked_nothing():
    github = FakeGitHub(
        fetches=[
            make_run(3, "2026-11-12T06:18:00Z"),  # the timer's second try: already fetched
            make_run(1, "2026-11-12T04:38:00Z"),
        ],
        refreshes=[make_run(2, "2026-11-12T05:45:00Z")],
        jobs={
            3: feed_job(FETCH, "2026-11-12T06:17:40Z", conclusion="skipped"),
            2: feed_job(REFRESH, "2026-11-12T05:43:10Z"),
            1: feed_job(FETCH, "2026-11-12T04:36:30Z"),
        },
    )
    assert refresh_runs.last_ended(github, REPO, CURRENT) == datetime(
        2026, 11, 12, 5, 43, 10, tzinfo=UTC
    )
    assert github.jobs_asked == [3, 2]


@pytest.mark.parametrize("conclusion", ["failure", "cancelled", "timed_out"])
def test_a_feed_job_that_failed_or_was_stopped_still_counts(conclusion):
    # It may have asked feeds before it stopped.
    github = FakeGitHub(
        refreshes=[make_run(2, "2026-11-12T05:45:00Z")],
        jobs={2: feed_job(REFRESH, "2026-11-12T05:44:00Z", conclusion=conclusion)},
    )
    assert refresh_runs.last_ended(github, REPO, CURRENT) == datetime(
        2026, 11, 12, 5, 44, tzinfo=UTC
    )


def test_a_run_still_going_counts_once_its_feed_job_has_ended():
    # A refresh whose deploy is still running, and a fetch that is still fetching.
    github = FakeGitHub(
        fetches=[make_run(4, "2026-11-12T05:00:00Z", state="in_progress")],
        refreshes=[
            make_run(3, "2026-11-12T04:50:00Z", state="in_progress"),
            make_run(2, "2026-11-12T03:46:00Z"),
        ],
        jobs={
            4: [{"name": refresh_runs.FEED_JOBS[FETCH], "conclusion": None, "completed_at": None}],
            3: feed_job(REFRESH, "2026-11-12T04:49:00Z"),
            2: feed_job(REFRESH, "2026-11-12T03:44:00Z"),
        },
    )
    assert refresh_runs.last_ended(github, REPO, CURRENT) == datetime(
        2026, 11, 12, 4, 49, tzinfo=UTC
    )
    assert github.jobs_asked == [4, 3]


def test_this_run_is_never_counted_and_no_run_means_no_time():
    github = FakeGitHub(
        refreshes=[make_run(CURRENT, "2026-11-12T05:30:10Z")],
        jobs={CURRENT: feed_job(REFRESH, "2026-11-12T05:30:09Z")},
    )
    assert refresh_runs.last_ended(github, REPO, CURRENT) is None
    assert github.jobs_asked == []


def test_last_ended_writes_the_time_for_the_refresh(tmp_path, monkeypatch, capsys):
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    github = FakeGitHub(
        fetches=[make_run(1, "2026-11-12T04:38:00Z")],
        jobs={1: feed_job(FETCH, "2026-11-12T04:36:30Z")},
    )
    assert run_main("last-ended", github) == 0
    assert run_main("last-ended", FakeGitHub()) == 0
    assert output.read_text() == "ended=2026-11-12T04:36:30Z\nended=\n"
    # The refresh reads the time as written, and an empty one is left out by the workflow.
    assert refresh._when("2026-11-12T04:36:30Z") == datetime(2026, 11, 12, 4, 36, 30, tzinfo=UTC)
    assert "No run that asked feeds" in capsys.readouterr().out


def test_last_ended_fails_when_github_cannot_be_asked(tmp_path, monkeypatch, capsys):
    # The refresh job stops there, before it asks any feed.
    output = tmp_path / "output"
    monkeypatch.setenv("GITHUB_OUTPUT", str(output))
    assert run_main("last-ended", FakeGitHub(fail=True)) == 1
    assert not output.exists()
    assert "Could not read when the last run ended" in capsys.readouterr().err


# The daily fetch's wait


@pytest.mark.parametrize(
    ("ended", "expected"),
    [
        (None, 0),
        (NOW - timedelta(hours=1), 0),
        (NOW - timedelta(seconds=721), 0),
        (NOW - timedelta(seconds=700), 21),
        (NOW, 721),
        (NOW + timedelta(minutes=5), 721),  # a clock that disagrees never adds to the gap
    ],
)
def test_the_wait_is_what_is_left_of_the_gap(ended, expected):
    assert refresh_runs.seconds_to_wait(ended, 721, NOW) == expected


def test_the_gap_is_the_longest_any_fetched_operator_keeps():
    operators = load_registry()
    fetched = [c for c in operators.values() if refresh.refreshable(c)]
    assert refresh_runs.longest_gap() == max(required_gap(c) for c in fetched)
    # Never shorter than any host's cool-down in a refresh, which uses the same gaps.
    assert all(refresh_runs.longest_gap() >= refresh.cool_down([c]) for c in fetched)
    # Roam's feed allows 5 requests an hour: with the margin, 721 seconds.
    assert refresh_runs.longest_gap() >= required_gap(operators["roam"]) >= 721


def test_the_daily_fetch_waits_out_the_gap_after_a_refresh(capsys):
    slept = []
    github = FakeGitHub(
        refreshes=[make_run(2, "2026-11-12T05:27:00Z")],
        jobs={2: feed_job(REFRESH, "2026-11-12T05:25:20Z")},
    )
    assert run_main("wait", github, sleep=slept.append, gap=lambda: 721.0) == 0
    assert slept == [421.0]  # 721 seconds after 05:25:20 is 300 seconds before NOW
    assert "Waiting 421 seconds" in capsys.readouterr().out


def test_the_daily_fetch_does_not_wait_when_the_gap_has_passed(capsys):
    slept = []
    github = FakeGitHub(
        refreshes=[make_run(2, "2026-11-12T03:46:00Z")],
        jobs={2: feed_job(REFRESH, "2026-11-12T03:44:00Z")},
    )
    assert run_main("wait", github, sleep=slept.append, gap=lambda: 721.0) == 0
    assert run_main("wait", FakeGitHub(), sleep=slept.append, gap=lambda: 721.0) == 0
    assert slept == []
    assert capsys.readouterr().out.count("No wait is needed.") == 2


def test_the_daily_fetch_waits_the_whole_gap_when_github_cannot_be_asked(capsys):
    slept = []
    code = run_main("wait", FakeGitHub(fail=True), sleep=slept.append, gap=lambda: 721.0)
    assert code == 0
    assert slept == [721.0]
    assert "::warning::" in capsys.readouterr().out


def test_an_answer_that_cannot_be_read_also_waits_the_whole_gap():
    slept = []
    github = FakeGitHub(refreshes=[{"id": 2, "status": "completed"}])  # no updated_at
    assert run_main("wait", github, sleep=slept.append, gap=lambda: 721.0) == 0
    assert slept == [721.0]


# The workflows


def _workflow(name):
    return yaml.safe_load((WORKFLOWS / name).read_text(encoding="utf-8"))


def test_the_feed_jobs_are_named_as_in_the_workflows():
    assert _workflow(FETCH)["jobs"]["fetch"]["name"] == refresh_runs.FEED_JOBS[FETCH]
    assert _workflow(REFRESH)["jobs"]["refresh"]["name"] == refresh_runs.FEED_JOBS[REFRESH]
    for name, title in refresh_runs.WORKFLOW_NAMES.items():
        assert _workflow(name)["name"] == title
    assert refresh_runs.FEED_JOBS[FETCH] == daily_runs.FETCH_JOB


def test_the_refresh_and_the_daily_fetch_never_ask_feeds_at_the_same_time():
    daily = _workflow(FETCH)["concurrency"]
    job = _workflow(REFRESH)["jobs"]["refresh"]
    assert job["concurrency"] == {"group": daily["group"], "cancel-in-progress": False}
    assert daily["cancel-in-progress"] is False
    # The whole of Refresh statuses is not in the group: its check must run first.
    assert "concurrency" not in _workflow(REFRESH)


def test_a_refresh_checks_first_and_asks_for_the_last_end_once_it_holds_the_group():
    jobs = _workflow(REFRESH)["jobs"]
    check = next(s for s in jobs["check"]["steps"] if s.get("id") == "check")
    # Standard library only: the check runs before anything is installed.
    assert check["run"] == "python3 -m pipeline.refresh_runs check"
    assert "concurrency" not in jobs["check"]
    assert jobs["check"]["permissions"] == {"contents": "read", "actions": "read"}
    assert jobs["refresh"]["needs"] == "check"
    assert "needs.check.outputs.refresh == 'true'" in jobs["refresh"]["if"]
    steps = jobs["refresh"]["steps"]
    ids = [s.get("id") for s in steps]
    assert ids.index("last") < ids.index("refresh")
    assert steps[ids.index("last")]["run"].endswith("pipeline.refresh_runs last-ended")
    step = steps[ids.index("refresh")]
    assert step["env"]["LAST_RUN_ENDED"] == "${{ steps.last.outputs.ended }}"
    assert '--last-run-ended "$LAST_RUN_ENDED"' in step["run"]


def test_only_main_refreshes_and_only_when_started_by_hand_or_the_timer():
    workflow = _workflow(REFRESH)
    # No GitHub schedule: it starts runs hours late (ADR 0024).
    assert set(workflow[True]) == {"workflow_dispatch"}
    started_by = workflow[True]["workflow_dispatch"]["inputs"]["started_by"]
    assert started_by["options"] == ["hand", "timer"] and started_by["default"] == "hand"
    for job in ("check", "refresh"):
        assert "github.ref == 'refs/heads/main'" in workflow["jobs"][job]["if"]


def test_the_daily_fetch_waits_before_it_fetches():
    steps = _workflow(FETCH)["jobs"]["fetch"]["steps"]
    runs = [s.get("run", "") for s in steps]
    wait = next(i for i, run in enumerate(runs) if "pipeline.refresh_runs wait" in run)
    fetch = next(i for i, s in enumerate(steps) if s.get("id") == "fetch")
    assert wait == fetch - 1
    assert set(steps[wait]["env"]) == {"GH_TOKEN"}
    # If the wait fails, the fetch is not stopped: it waits longer than any gap instead.
    assert runs[wait].startswith("if ! uv run python -m pipeline.refresh_runs wait; then")
    fallback = int(re.search(r"^\s+sleep (\d+)$", runs[wait], flags=re.MULTILINE).group(1))
    assert fallback > refresh_runs.longest_gap()
    assert "exit" not in runs[wait]


def test_the_wait_with_the_real_registry_and_no_answer_from_github(monkeypatch, capsys):
    # The command as the workflow runs it, apart from the sleep, with GitHub out of reach.
    def unreachable(request, timeout):
        assert request.full_url.startswith("https://api.github.com/repos/")
        raise urllib.error.URLError("no route")

    monkeypatch.setattr(urllib.request, "urlopen", unreachable)
    monkeypatch.setenv("GH_TOKEN", "not-a-token")
    monkeypatch.setenv("GITHUB_REPOSITORY", REPO)
    monkeypatch.setenv("GITHUB_RUN_ID", str(CURRENT))
    slept = []
    assert refresh_runs.main(["wait"], sleep=slept.append) == 0
    assert slept == [refresh_runs.longest_gap()]
    out = capsys.readouterr().out
    assert "::warning::" in out and "not-a-token" not in out


def test_the_check_and_the_last_end_need_nothing_outside_the_standard_library():
    source = (ROOT / "pipeline" / "refresh_runs.py").read_text(encoding="utf-8")
    imported = set(re.findall(r"^(?:from|import) ([\w.]+)", source, flags=re.MULTILINE))
    assert imported <= {
        "argparse",
        "os",
        "sys",
        "time",
        "collections.abc",
        "datetime",
        "pipeline.daily_runs",
    }
