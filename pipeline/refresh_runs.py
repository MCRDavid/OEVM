"""Keeping every host's gap between one run and the next (ADR 0032).

Two workflows ask operators' feeds: Fetch daily (.github/workflows/fetch-daily.yml) and
Refresh statuses (.github/workflows/refresh-statuses.yml). Their feed jobs share one
concurrency group, so GitHub never runs the two together. The polite client's timers last
one run, though, so a run must also know when the last one stopped asking. The workflows'
run history says when, and this reads it three ways:

    python3 -m pipeline.refresh_runs check

is the first job of Refresh statuses. It writes refresh=false to $GITHUB_OUTPUT when
another run of either workflow on main is waiting or running, and refresh=true otherwise,
so a refresh never waits in the concurrency group, where it would take the place of a
daily fetch that is waiting there. It also says false when GitHub cannot be asked: a
missed refresh costs an hour of statuses, and asking a host too soon is never worth that.

    python3 -m pipeline.refresh_runs last-ended

writes ended=<time> to $GITHUB_OUTPUT: when the feed job of either workflow last ended,
whatever its result, or nothing if none is found in the newest 30 runs of each. The
refresh passes it on (pipeline.refresh --last-run-ended). It fails when GitHub cannot be
asked, and the refresh then stops before asking any feed.

    uv run python -m pipeline.refresh_runs wait

is run by Fetch daily before it fetches. It sleeps until the longest gap any switched-on
operator keeps has passed since that time. That is seldom any wait at all, because the
refresh before the daily fetch has usually ended long before. If GitHub cannot be asked
it waits the whole gap, which is always enough, because no other feed job runs while this
one holds the concurrency group.

All three read the GitHub API with GH_TOKEN, which needs "actions: read". The first two
use only the standard library. Tests never call the API.
"""

import argparse
import os
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime

from pipeline.daily_runs import DailyRunsError, Getter, github_getter, jobs_of

# The job that asks feeds in each workflow, by the name GitHub reports (tests keep these
# in step with the workflow files).
FEED_JOBS = {
    "fetch-daily.yml": "Fetch operator feeds",
    "refresh-statuses.yml": "Read charge point statuses",
}
WORKFLOW_NAMES = {"fetch-daily.yml": "Fetch daily", "refresh-statuses.yml": "Refresh statuses"}
# How many of each workflow's newest runs are read: over a day of hourly refreshes.
NEWEST = 30


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def newest_runs(get: Getter, repo: str, current_run_id: int | None) -> list[tuple[str, dict]]:
    """The newest runs of both workflows on main, apart from this run, each with its
    workflow file."""
    found = []
    for workflow in FEED_JOBS:
        listing = get(
            f"repos/{repo}/actions/workflows/{workflow}/runs"
            f"?branch=main&exclude_pull_requests=true&per_page={NEWEST}"
        )
        found += [
            (workflow, run)
            for run in listing.get("workflow_runs", [])
            if run["id"] != current_run_id
        ]
    return found


def active(get: Getter, repo: str, current_run_id: int | None) -> list[tuple[str, dict]]:
    """Other runs of either workflow that have not finished: waiting, queued or running."""
    return [
        (workflow, run)
        for workflow, run in newest_runs(get, repo, current_run_id)
        if run.get("status") != "completed"
    ]


def should_refresh(get: Getter, repo: str, current_run_id: int | None) -> tuple[bool, str]:
    """Whether this run refreshes, and why, in words for the run's log."""
    try:
        busy = active(get, repo, current_run_id)
    except (DailyRunsError, KeyError, TypeError) as exc:
        return False, f"Could not check for other runs, so this run asks no feed: {exc}"
    if busy:
        workflow, run = busy[0]
        return False, (
            f"{WORKFLOW_NAMES[workflow]} run {run.get('run_number', run['id'])} has not "
            "finished, so this run stops without asking any feed."
        )
    return True, "No other fetch or refresh is waiting or running, so this run refreshes."


def last_ended(get: Getter, repo: str, current_run_id: int | None) -> datetime | None:
    """When a feed job of either workflow last ended, whatever its result: it may have
    asked feeds before it failed or was stopped. A job that was skipped asked nothing."""
    runs = sorted(
        newest_runs(get, repo, current_run_id),
        key=lambda found: _time(found[1]["updated_at"]),
        reverse=True,
    )
    latest: datetime | None = None
    for workflow, run in runs:
        # A finished run changed last when it ended, so none of its jobs ended later.
        finished = run.get("status") == "completed"
        if latest is not None and finished and _time(run["updated_at"]) <= latest:
            break
        for job in jobs_of(get, repo, run["id"]):
            if job.get("name") != FEED_JOBS[workflow] or not job.get("completed_at"):
                continue
            if job.get("conclusion") in (None, "skipped"):
                continue
            ended = _time(job["completed_at"])
            latest = ended if latest is None else max(latest, ended)
    return latest


def seconds_to_wait(ended: datetime | None, gap: float, now: datetime) -> float:
    """How long to wait so that gap seconds have passed since the last feed job ended;
    never longer than the gap itself."""
    if ended is None:
        return 0.0
    return min(gap, max(0.0, gap - (now - ended).total_seconds()))


def longest_gap() -> float:
    """The longest gap any operator that is fetched keeps on its host, in seconds."""
    # Imported here so that check and last-ended need nothing installed.
    from adapters.http import required_gap
    from pipeline.refresh import refreshable
    from pipeline.registry import load_registry

    return max(
        (required_gap(config) for config in load_registry().values() if refreshable(config)),
        default=0.0,
    )


def _write_output(name: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")
    else:
        print(f"{name}={value}")


def _stamp(when: datetime) -> str:
    return when.astimezone(UTC).isoformat().replace("+00:00", "Z")


def main(
    argv: list[str] | None = None,
    get: Getter | None = None,
    *,
    sleep: Callable[[float], None] = time.sleep,
    gap: Callable[[], float] = longest_gap,
) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m pipeline.refresh_runs", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in [
        ("check", "say whether this run refreshes"),
        ("last-ended", "say when a run last stopped asking feeds"),
        ("wait", "wait until every host's gap has passed since then"),
    ]:
        command = commands.add_parser(name, help=help_text)
        command.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
        command.add_argument("--run-id", type=int, default=os.environ.get("GITHUB_RUN_ID"))
        command.add_argument("--now", type=datetime.fromisoformat, help="default: now")
    args = parser.parse_args(argv)
    if not args.repo or args.run_id is None:
        parser.error("needs --repo and --run-id, or GITHUB_REPOSITORY and GITHUB_RUN_ID")
    if get is None:
        token = os.environ.get("GH_TOKEN", "")
        if not token:
            parser.error("needs GH_TOKEN with actions: read")
        get = github_getter(token)

    if args.command == "check":
        refresh, why = should_refresh(get, args.repo, args.run_id)
        print(why)
        _write_output("refresh", "true" if refresh else "false")
        return 0

    try:
        ended = last_ended(get, args.repo, args.run_id)
        problem = None
    except (DailyRunsError, KeyError, TypeError, ValueError) as exc:
        ended, problem = None, exc

    if args.command == "last-ended":
        if problem is not None:
            print(f"::error::Could not read when the last run ended: {problem}", file=sys.stderr)
            return 1
        print(
            f"The last run stopped asking feeds at {_stamp(ended)}."
            if ended
            else f"No run that asked feeds is among the newest {NEWEST} of each workflow."
        )
        _write_output("ended", _stamp(ended) if ended else "")
        return 0

    longest = gap()
    if problem is not None:
        seconds = longest
        print(
            "::warning::Could not read when the last run ended, so this run waits the "
            f"whole gap of {longest:.0f} seconds before it fetches: {problem}"
        )
    else:
        now = (args.now or datetime.now(UTC)).astimezone(UTC)
        seconds = seconds_to_wait(ended, longest, now)
        print(
            (f"The last run stopped asking feeds at {_stamp(ended)}. " if ended else "")
            + (
                f"Waiting {seconds:.0f} seconds, so that {longest:.0f} seconds have passed."
                if seconds
                else "No wait is needed."
            )
        )
    if seconds:
        sleep(seconds)
    return 0


if __name__ == "__main__":
    sys.exit(main())
