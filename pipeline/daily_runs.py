"""How each day's fetch started, and whether today's has already run (ADR 0024).

Fetch daily (.github/workflows/fetch-daily.yml) can be started three ways:

- by the relay Worker's timer, a Cloudflare Cron Trigger (relay/wrangler.toml), which asks
  GitHub to start the workflow (relay/worker.js); this is the main way;
- by GitHub's own schedule, kept as a backup. GitHub says scheduled runs "can be delayed
  during periods of high loads" and that "some queued jobs may be dropped"; from 9 to 12
  October 2026 they started six to seven hours late, or not at all;
- by hand, from the Actions tab.

So that this still means one fetch a day, a run started by the timer or the schedule
first asks:

    python3 -m pipeline.daily_runs check --event schedule --started-by ""

which writes fetch=false to $GITHUB_OUTPUT when another run of Fetch daily on main has
already fetched and published today (UTC), and fetch=true otherwise. It also says true
when GitHub cannot be asked: a second fetch in a day is better than none, and every fetch
keeps every operator's rate limit. A run started by hand always fetches.

    python3 -m pipeline.daily_runs record --out daily-runs.json

saves the last 30 days of runs, how each started and what it did, for the feed health
page (pipeline.status --daily-runs). Both read the GitHub API with GH_TOKEN, which needs
"actions: read". They use only the standard library, so the check needs no install.
Tests never call the API.
"""

import argparse
import json
import os
import re
import statistics
import sys
import urllib.error
import urllib.request
from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

API = "https://api.github.com"
WORKFLOW = "fetch-daily.yml"
# Job names as GitHub reports them; the deploy job comes from the reusable deploy.yml.
CHECK_JOB = "Check whether today's fetch has run"
FETCH_JOB = "Fetch operator feeds"
DEPLOY_JOB_PREFIX = "Deploy / "
REPORT_JOB = "Report failed operators"

RECORD_DAYS = 30
MAX_PAGES = 10
# A scheduled start this close to the time set counts as on time.
ON_TIME = timedelta(hours=1)
# The only schedule before 12 October 2026, when run titles began to name theirs.
FIRST_CRON = "17 4 * * *"

# How a run started (the workflow's run-name says which).
SCHEDULE, TIMER, HAND = "schedule", "timer", "hand"
STARTED_BY_LABELS = {SCHEDULE: "GitHub schedule", TIMER: "Cloudflare timer", HAND: "By hand"}
TIMER_TITLE = "(Cloudflare timer)"
SCHEDULE_TITLE = re.compile(r"\(GitHub schedule ([^)]+)\)")

# What a run did.
PUBLISHED = "published"
OPERATOR_MISSING = "operator_missing"
DEPLOY_FAILED = "deploy_failed"
SKIPPED = "skipped"
FAILED = "failed"
CANCELLED = "cancelled"
RUNNING = "running"
THIS_RUN = "this_run"
OUTCOME_LABELS = {
    PUBLISHED: "Fetched and published",
    OPERATOR_MISSING: "Fetched and published; at least one operator was left off the map",
    DEPLOY_FAILED: "Fetched, but the site was not updated",
    SKIPPED: "Stopped: that day's fetch had already run",
    FAILED: "Failed before publishing",
    CANCELLED: "Cancelled",
    RUNNING: "Still running when this page was built",
    THIS_RUN: "Fetched; this run built this page",
}
# Runs that updated the map. A deploy that failed did not, so the next timer or schedule
# run that day tries again.
UPDATED = frozenset({PUBLISHED, OPERATOR_MISSING, THIS_RUN})

Getter = Callable[[str], dict]


class DailyRunsError(Exception):
    """GitHub could not be asked, or a record file cannot be read."""


def github_getter(token: str) -> Getter:
    """GET a GitHub API path with the workflow's token, as parsed JSON."""

    def get(path: str) -> dict:
        request = urllib.request.Request(
            f"{API}/{path}",
            headers={
                "Accept": "application/vnd.github+json",
                "Authorization": f"Bearer {token}",
                "X-GitHub-Api-Version": "2022-11-28",
                "User-Agent": "OEVM daily run record",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=30) as response:
                return json.load(response)
        except (urllib.error.URLError, TimeoutError, ValueError) as exc:
            # The message names the path only, never the token.
            raise DailyRunsError(f"GitHub did not answer {path}: {exc}") from None

    return get


def _time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(UTC)


def started_by(run: dict) -> tuple[str, str | None]:
    """How a run started, and for a scheduled run the schedule it came from."""
    title = run.get("display_title") or ""
    if run.get("event") == "schedule":
        found = SCHEDULE_TITLE.search(title)
        return SCHEDULE, found.group(1).strip() if found else FIRST_CRON
    if run.get("event") == "workflow_dispatch" and TIMER_TITLE in title:
        return TIMER, None
    return HAND, None


def outcome(run: dict, jobs: Iterable[dict], current_run_id: int | None) -> str:
    """What a run did, from its jobs' conclusions."""
    if run["id"] == current_run_id:
        return THIS_RUN
    if run.get("status") != "completed":
        return RUNNING
    conclusions = {job["name"]: job.get("conclusion") for job in jobs}
    fetch = conclusions.get(FETCH_JOB)
    if fetch == "success":
        deploy = [c for name, c in conclusions.items() if name.startswith(DEPLOY_JOB_PREFIX)]
        if deploy != ["success"]:
            return DEPLOY_FAILED
        return OPERATOR_MISSING if conclusions.get(REPORT_JOB) == "failure" else PUBLISHED
    if run.get("conclusion") == "cancelled" or fetch == "cancelled":
        return CANCELLED
    if fetch == "skipped" and run.get("conclusion") == "success":
        return SKIPPED
    return FAILED


def scheduled_time(cron: str, started: datetime) -> datetime | None:
    """The last time a daily "M H * * *" schedule was due at or before a run started."""
    found = re.fullmatch(r"(\d{1,2}) (\d{1,2}) \* \* \*", cron.strip())
    if not found:
        return None
    minute, hour = int(found.group(1)), int(found.group(2))
    if minute > 59 or hour > 23:
        return None
    due = started.replace(hour=hour, minute=minute, second=0, microsecond=0)
    return due - timedelta(days=1) if due > started else due


@dataclass(frozen=True)
class DailyRun:
    """One run of Fetch daily, as the feed health page shows it."""

    id: int
    number: int
    created_at: datetime
    started_by: str
    cron: str | None
    outcome: str
    url: str

    @property
    def delay(self) -> timedelta | None:
        """How long after the time set a scheduled run started."""
        if self.started_by != SCHEDULE or not self.cron:
            return None
        due = scheduled_time(self.cron, self.created_at)
        return None if due is None else self.created_at - due


@dataclass(frozen=True)
class Record:
    generated_at: datetime
    since: date
    runs: list[DailyRun]


def list_runs(get: Getter, repo: str, since: date) -> tuple[list[dict], bool]:
    """Runs of Fetch daily on main started on or after since, newest first, and whether
    any earlier run exists."""
    runs = []
    for page in range(1, MAX_PAGES + 1):
        batch = get(
            f"repos/{repo}/actions/workflows/{WORKFLOW}/runs"
            f"?branch=main&exclude_pull_requests=true&per_page=100&page={page}"
        ).get("workflow_runs", [])
        for run in batch:
            if _time(run["created_at"]).date() < since:
                return runs, True
            runs.append(run)
        if len(batch) < 100:
            break
    return runs, False


def jobs_of(get: Getter, repo: str, run_id: int) -> list[dict]:
    return get(f"repos/{repo}/actions/runs/{run_id}/jobs?per_page=100").get("jobs", [])


def daily_run(get: Getter, repo: str, run: dict, current_run_id: int | None) -> DailyRun:
    how, cron = started_by(run)
    final = run["id"] != current_run_id and run.get("status") == "completed"
    jobs = jobs_of(get, repo, run["id"]) if final else []
    return DailyRun(
        id=run["id"],
        number=run.get("run_number", 0),
        created_at=_time(run["created_at"]),
        started_by=how,
        cron=cron,
        outcome=outcome(run, jobs, current_run_id),
        url=run.get("html_url", ""),
    )


# The check


def published_today(get: Getter, repo: str, today: date, current_run_id: int) -> DailyRun | None:
    """Another run of Fetch daily on main that fetched and published today, if any."""
    runs, _older = list_runs(get, repo, today)
    for run in runs:
        if run["id"] == current_run_id or _time(run["created_at"]).date() != today:
            continue
        found = daily_run(get, repo, run, current_run_id)
        if found.outcome in UPDATED:
            return found
    return None


def should_fetch(
    get: Getter, repo: str, event: str, how: str, today: date, current_run_id: int
) -> tuple[bool, str]:
    """Whether this run fetches, and why, in words for the run's log."""
    if event != "schedule" and how != TIMER:
        return True, "Started by hand, so it fetches whatever ran earlier today."
    try:
        earlier = published_today(get, repo, today, current_run_id)
    except (DailyRunsError, KeyError, TypeError) as exc:
        return True, f"Could not check earlier runs, so it fetches anyway: {exc}"
    if earlier is None:
        return True, f"No run has fetched and published today ({today}), so this one fetches."
    return False, (
        f"Run {earlier.number} ({STARTED_BY_LABELS[earlier.started_by]}) already fetched and "
        f"published today ({today}), so this run stops without fetching."
    )


# The record


def collect(get: Getter, repo: str, now: datetime, current_run_id: int | None) -> Record:
    window = (now - timedelta(days=RECORD_DAYS - 1)).date()
    runs, older = list_runs(get, repo, window)
    found = [daily_run(get, repo, run, current_run_id) for run in runs]
    first = min((run.created_at.date() for run in found), default=now.date())
    since = window if older else first
    return Record(generated_at=now, since=since, runs=sorted(found, key=lambda r: r.created_at))


def to_json(record: Record) -> str:
    data = {
        "generated_at": record.generated_at.isoformat().replace("+00:00", "Z"),
        "since": record.since.isoformat(),
        "runs": [
            {**asdict(run), "created_at": run.created_at.isoformat().replace("+00:00", "Z")}
            for run in record.runs
        ],
    }
    return json.dumps(data, indent=2) + "\n"


def load_record(path: Path) -> Record:
    """Read a record written by the record command."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        runs = [
            DailyRun(
                id=int(run["id"]),
                number=int(run["number"]),
                created_at=_time(run["created_at"]),
                started_by=run["started_by"],
                cron=run.get("cron"),
                outcome=run["outcome"],
                url=str(run.get("url", "")),
            )
            for run in data["runs"]
        ]
        record = Record(
            generated_at=_time(data["generated_at"]),
            since=date.fromisoformat(data["since"]),
            runs=runs,
        )
    except FileNotFoundError:
        raise DailyRunsError(f"{path} does not exist") from None
    except (KeyError, TypeError, ValueError) as exc:
        raise DailyRunsError(f"{path} is not a daily run record: {exc!r}") from None
    for run in record.runs:
        if run.started_by not in STARTED_BY_LABELS or run.outcome not in OUTCOME_LABELS:
            raise DailyRunsError(f"{path} has a run with an unknown start or outcome")
        if run.url and not run.url.startswith("https://github.com/"):
            raise DailyRunsError(f"{path} has a run link outside GitHub")
    return record


@dataclass(frozen=True)
class Summary:
    days: int
    days_updated: int
    schedule_days: int
    schedule_runs: int
    schedule_on_time: int
    schedule_median_delay: timedelta | None
    timer_since: date | None
    timer_span: int
    timer_days: int


def summarise(record: Record) -> Summary:
    today = record.generated_at.date()
    days = (today - record.since).days + 1

    def days_with(runs: Iterable[DailyRun]) -> int:
        return len({run.created_at.date() for run in runs})

    scheduled = [run for run in record.runs if run.started_by == SCHEDULE]
    delays = [run.delay for run in scheduled if run.delay is not None]
    timer = [run for run in record.runs if run.started_by == TIMER]
    timer_since = min((run.created_at.date() for run in timer), default=None)
    return Summary(
        days=days,
        days_updated=days_with(run for run in record.runs if run.outcome in UPDATED),
        schedule_days=days_with(scheduled),
        schedule_runs=len(scheduled),
        schedule_on_time=sum(delay <= ON_TIME for delay in delays),
        schedule_median_delay=(
            timedelta(seconds=round(statistics.median(d.total_seconds() for d in delays)))
            if delays
            else None
        ),
        timer_since=timer_since,
        timer_span=(today - timer_since).days + 1 if timer_since else 0,
        timer_days=days_with(timer),
    )


def duration(value: timedelta) -> str:
    """A delay in words, such as "6 h 18 min", "1 h" or "4 min"."""
    minutes = max(0, round(value.total_seconds() / 60))
    hours, minutes = divmod(minutes, 60)
    if not hours:
        return f"{minutes} min"
    return f"{hours} h {minutes} min" if minutes else f"{hours} h"


# Command line


def _write_output(name: str, value: str) -> None:
    path = os.environ.get("GITHUB_OUTPUT")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write(f"{name}={value}\n")
    else:
        print(f"{name}={value}")


def main(argv: list[str] | None = None, get: Getter | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m pipeline.daily_runs", description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    check = commands.add_parser("check", help="say whether this run fetches")
    check.add_argument("--event", required=True, help="github.event_name")
    check.add_argument("--started-by", default="", help="the workflow's started_by input")
    record = commands.add_parser("record", help="save the last 30 days of runs")
    record.add_argument("--out", type=Path, required=True)
    for command in (check, record):
        command.add_argument("--repo", default=os.environ.get("GITHUB_REPOSITORY", ""))
        command.add_argument("--run-id", type=int, default=os.environ.get("GITHUB_RUN_ID"))
        command.add_argument("--now", type=datetime.fromisoformat, help="default: now")
    args = parser.parse_args(argv)
    if not args.repo or args.run_id is None:
        parser.error("needs --repo and --run-id, or GITHUB_REPOSITORY and GITHUB_RUN_ID")
    now = (args.now or datetime.now(UTC)).astimezone(UTC).replace(microsecond=0)
    if get is None:
        token = os.environ.get("GH_TOKEN", "")
        if not token:
            parser.error("needs GH_TOKEN with actions: read")
        get = github_getter(token)

    if args.command == "check":
        fetch, why = should_fetch(
            get, args.repo, args.event, args.started_by, now.date(), args.run_id
        )
        print(why)
        _write_output("fetch", "true" if fetch else "false")
        return 0

    try:
        found = collect(get, args.repo, now, args.run_id)
    except (DailyRunsError, KeyError, TypeError) as exc:
        # The fetch carries on; the feed health page says the record was not available.
        print(f"::warning::The daily run record could not be read from GitHub: {exc}")
        return 0
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(to_json(found), encoding="utf-8")
    print(f"Wrote {args.out} ({len(found.runs)} runs since {found.since})")
    return 0


if __name__ == "__main__":
    sys.exit(main())
