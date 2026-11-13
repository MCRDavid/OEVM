"""Refresh charge point statuses between the daily fetches (Phase 3, docs/PHASE3_PLAN.md).

    uv run python -m pipeline.refresh --fixtures --map build --out build
    uv run python -m pipeline.refresh --live all --map build --out out --previous last

Run by the Refresh statuses workflow (.github/workflows/refresh-statuses.yml), which the
relay Worker's timer starts each hour. pipeline.live_site packs what this writes for the site.

For each operator that is switched on and on the published map (--map DIR, the map files
under DIR/data), it reads every EVSE's status and writes DIR/live/<operator>.json
(schema.live.LiveSnapshot) and DIR/live/refresh.json, a record of the run. It never reads a
tariff, never changes the map files and never adds a location: a status is laid over a
location the daily fetch published (pipeline.live_snapshot.from_statuses).

It keeps the same rules as the daily fetch, with the same client (adapters.http):

- Eco-Movement's networks are asked for statuses alone, one request each, at the endpoint
  in their operator files, within its published limit. Other feeds have no such endpoint,
  so their locations module is fetched alone. A copy an operator sent is never refreshed.
- Operators that share a host are fetched one after another, and hosts at the same time,
  as in pipeline.run; operators whose limits the owner reads per key take turns.
- The client's timers last one run, so this keeps each host's gap across runs too: a host
  is not asked again until its gap has passed since the last refresh of it finished
  (--previous) and since the last run of any kind ended (--last-run-ended, from the
  workflow's run history). Without that time, the daily fetch that made the map files is
  taken to have been asking feeds for as long as its job may run, because its files say
  when its last fetch started and not when it ended. Such an operator, and one whose
  refresh fails or does not finish, keeps its last snapshot.

--fixtures replays tests/fixtures and never uses the network; an Eco-Movement network is
replayed only where a statuses response was recorded.
"""

import argparse
import json
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx

import adapters.eco_movement
from adapters import statuses
from adapters.http import FeedError, PoliteClient, required_gap
from adapters.replay import ReplayTransport
from adapters.statuses import StatusResult
from pipeline import live_snapshot
from pipeline.live_snapshot import SnapshotError
from pipeline.registry import RegistryError, load_registry
from pipeline.run import (
    ADAPTERS,
    ALL_ENABLED,
    CUSTOM_ADAPTERS,
    FIXTURE_KEY,
    FIXTURES_DIR,
    host_groups,
    takes_turns,
)
from schema.live import LiveSnapshot, RefreshEntry, RefreshLog
from schema.operator import OperatorConfig

# Feeds with an endpoint for statuses alone, by registry adapter name.
STATUS_ENDPOINTS = {"eco_movement_pcpr": adapters.eco_movement.fetch_statuses}
# Exit code when at least one operator's refresh failed; the others were still written.
EXIT_SOME_FAILED = 2
# The longest the daily fetch's job may run (.github/workflows/fetch-daily.yml, the fetch
# job's timeout-minutes; a test keeps the two in step).
DAILY_FETCH_LIMIT = timedelta(minutes=150)


def refreshable(config: OperatorConfig) -> bool:
    """Whether an operator's statuses can be refreshed at all: switched on, and fetched
    from a feed rather than read from a copy it sent."""
    return config.enabled and config.licence is not None and config.sent_copy is None


def cool_down(group: list[OperatorConfig]) -> float:
    """Seconds to leave after this project last finished asking a host before a new run
    asks it again: the longest gap any operator on the host keeps, which is never less
    than any limit recorded for it needs, plus the margin (adapters.http.required_gap)."""
    return max(required_gap(config) for config in group)


def refresh_operator(
    config: OperatorConfig,
    *,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    key: str | None = None,
    page_size: int | None = None,
    max_pages: int | None = None,
    now: datetime | None = None,
    notice: Callable[[str], None] = lambda _text: None,
) -> StatusResult:
    """Read one operator's statuses. A FeedError raised here carries `requests`."""
    if not refreshable(config):
        raise FeedError(f"{config.id}: its statuses cannot be refreshed")
    with PoliteClient(
        config, transport=transport, sleep=sleep, clock=clock, key=key, notice=notice
    ) as client:
        try:
            endpoint = STATUS_ENDPOINTS.get(config.adapter)
            if endpoint is not None:
                result = endpoint(config, client, max_pages=max_pages, now=now)
            else:
                fetch = (
                    CUSTOM_ADAPTERS.get(config.id)
                    if config.adapter == "custom"
                    else ADAPTERS.get(config.adapter)
                )
                if fetch is None:
                    raise FeedError(f"{config.id}: its adapter is not built yet")
                result = statuses.from_locations(
                    fetch(
                        config,
                        client,
                        page_size=page_size,
                        max_pages=max_pages,
                        now=now,
                        statuses_only=True,
                    )
                )
        except FeedError as exc:
            exc.requests = client.requests_made
            raise
        result.requests = client.requests_made
        result.issues = [*client.events, *result.issues]
        return result


def refresh_fixtures(
    operators: dict[str, OperatorConfig], *, now: datetime | None = None
) -> dict[str, StatusResult]:
    """Replay every fixture folder whose operator can be refreshed and has a recording of
    what a refresh asks for."""
    results = {}
    for manifest_path in sorted(FIXTURES_DIR.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        config = operators[manifest["operator"]].model_copy(update={"relay": None})
        if not refreshable(config):
            continue
        folder = manifest_path.parent
        if config.adapter in STATUS_ENDPOINTS and not (folder / "statuses_page1.json").exists():
            continue
        results[config.id] = refresh_operator(
            config,
            transport=ReplayTransport(folder),
            sleep=lambda _seconds: None,
            key=FIXTURE_KEY,
            page_size=manifest.get("page_size"),
            max_pages=manifest.get("max_pages"),
            now=now,
        )
    return results


def refresh_live(
    configs: list[OperatorConfig], *, max_pages: int | None = None
) -> dict[str, StatusResult | FeedError]:
    """Refresh each operator, never two on one host at once unless they take turns. A
    failure comes back in place of the result, so the others still finish."""

    def one(config: OperatorConfig) -> StatusResult | FeedError:
        print(f"{config.id}: asking for statuses", flush=True)
        try:
            return refresh_operator(
                config,
                max_pages=max_pages,
                notice=lambda text, i=config.id: print(f"{i}: {text}", flush=True),
            )
        except FeedError as exc:
            return exc

    def group(members: list[OperatorConfig]) -> list[StatusResult | FeedError]:
        if takes_turns(members):
            with ThreadPoolExecutor(max_workers=len(members)) as pool:
                return list(pool.map(one, members))
        return [one(config) for config in members]

    groups = host_groups(configs)
    with ThreadPoolExecutor(max_workers=max(1, len(groups))) as pool:
        outcomes = [outcome for outcomes in pool.map(group, groups) for outcome in outcomes]
    ordered = [config for members in groups for config in members]
    return {config.id: outcome for config, outcome in zip(ordered, outcomes, strict=True)}


def _previous_log(previous: Path | None) -> RefreshLog | None:
    if previous is None:
        return None
    path = previous / "live" / "refresh.json"
    return RefreshLog.model_validate_json(path.read_bytes()) if path.exists() else None


def _daily_fetch_until(shown: live_snapshot.OnMap) -> datetime:
    """The latest the daily fetch that made the map files can have asked a feed.

    The map files carry when its last operator's fetch started (generated_at), not when
    the run ended, so the whole of the job's time limit is added.
    """
    return shown.generated_at + DAILY_FETCH_LIMIT


def _when(text: str) -> datetime:
    when = datetime.fromisoformat(text)
    if when.tzinfo is None:
        raise ValueError(f"{text!r} needs a time zone, such as 2026-11-12T05:00:00Z")
    return when


def too_soon(
    configs: list[OperatorConfig],
    *,
    now: datetime,
    last_contact: dict[str, datetime],
    last_run: datetime | None,
    sharing: list[OperatorConfig] | None = None,
) -> dict[str, datetime]:
    """Operators whose host was asked too recently, with the time each may be asked again.

    A host's last contact is the latest of its operators' last refreshes and last_run,
    the latest another run can have asked any host. Its gap is the longest any of its
    operators keeps (cool_down). `sharing` names every operator that may share a host
    with these ones, so that an operator left out of this run still holds its host back.
    """
    asked = {config.id for config in configs}
    everyone = {config.id: config for config in [*(sharing or []), *configs]}
    waiting: dict[str, datetime] = {}
    for members in host_groups(list(everyone.values())):
        times = [last_contact[c.id] for c in members if c.id in last_contact]
        if last_run is not None:
            times.append(last_run)
        if not times:
            continue
        ready = max(times) + timedelta(seconds=cool_down(members))
        if now < ready:
            waiting |= {config.id: ready for config in members if config.id in asked}
    return waiting


def _carried(operator_id: str, previous: Path | None, shown: dict[str, str]) -> LiveSnapshot | None:
    """The operator's last snapshot, without any location the map no longer shows."""
    if previous is None:
        return None
    path = previous / "live" / f"{operator_id}.json"
    if not path.exists():
        return None
    snapshot = LiveSnapshot.model_validate_json(path.read_bytes())
    keys = set(shown.values())
    kept = {key: evses for key, evses in snapshot.locations.items() if key in keys}
    return snapshot.model_copy(update={"locations": kept})


def _stamp(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%d %H:%M:%S UTC")


def main(argv: list[str] | None = None, *, now: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.refresh", description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixtures", action="store_true", help="replay recorded responses")
    mode.add_argument(
        "--live",
        metavar="OPERATOR",
        help=f"refresh one operator's statuses, or {ALL_ENABLED!r} for every enabled one",
    )
    parser.add_argument("--map", type=Path, required=True, help="the map files (DIR/data)")
    parser.add_argument("--out", type=Path, required=True, help="where to write DIR/live")
    parser.add_argument("--previous", type=Path, help="the last refresh's files (DIR/live)")
    parser.add_argument(
        "--last-run-ended",
        metavar="WHEN",
        help="when the last run that asked feeds ended, the daily fetch or a refresh "
        "(ISO 8601 with a time zone); without it the daily fetch is given its whole time limit",
    )
    parser.add_argument("--max-pages", type=int, help="stop after this many pages per module")
    args = parser.parse_args(argv)

    started = now or datetime.now(UTC).replace(microsecond=0)
    try:
        operators = load_registry()
        shown = live_snapshot.on_map(args.map)
        log = _previous_log(args.previous)
        if args.fixtures:
            outcomes: dict[str, StatusResult | FeedError] = dict(
                refresh_fixtures(operators, now=now)
            )
            waiting: dict[str, datetime] = {}
        else:
            if args.live == ALL_ENABLED:
                configs = [c for _, c in sorted(operators.items()) if refreshable(c)]
            elif args.live not in operators or not refreshable(operators[args.live]):
                raise FeedError(f"{args.live!r} is not an operator whose statuses can be refreshed")
            else:
                configs = [operators[args.live]]
            configs = [config for config in configs if shown.keys.get(config.id)]
            last_contact = {
                operator_id: entry.last_contact_at
                for operator_id, entry in (log.operators if log else {}).items()
                if entry.last_contact_at is not None
            }
            waiting = too_soon(
                configs,
                now=started,
                last_contact=last_contact,
                last_run=(
                    _when(args.last_run_ended) if args.last_run_ended else _daily_fetch_until(shown)
                ),
                sharing=[
                    config
                    for config in operators.values()
                    if refreshable(config) or config.id in last_contact
                ],
            )
            outcomes = refresh_live(
                [config for config in configs if config.id not in waiting],
                max_pages=args.max_pages,
            )
    except (FeedError, RegistryError, SnapshotError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    finished = now or datetime.now(UTC).replace(microsecond=0)
    # An operator left out of this run keeps its place in the record while it is still on
    # the map, so its host's last contact is never forgotten.
    left_out = {
        operator_id
        for operator_id in (log.operators if log else {})
        if operator_id not in outcomes
        and operator_id not in waiting
        and operator_id in operators
        and refreshable(operators[operator_id])
        and shown.keys.get(operator_id)
    }
    entries: dict[str, RefreshEntry] = {}
    failed = []
    for operator_id in sorted({*outcomes, *waiting, *left_out}):
        config = operators[operator_id]
        on_map = shown.keys.get(operator_id, {})
        outcome = outcomes.get(operator_id)
        before = log.operators.get(operator_id) if log else None
        note, requests, laid = None, None, None
        snapshot = None
        if operator_id in left_out:
            note = "not asked: not part of this run"
        elif operator_id in waiting:
            note = f"not asked: too soon after the last run (until {_stamp(waiting[operator_id])})"
        elif isinstance(outcome, FeedError):
            note, requests = f"failed: {outcome}", getattr(outcome, "requests", None)
        else:
            requests = outcome.requests
            try:
                # The trimmed fixtures stop after a few pages on purpose.
                snapshot, laid = live_snapshot.from_statuses(
                    outcome, config, on_map, partial_ok=args.fixtures
                )
            except SnapshotError as exc:
                note = f"failed: {exc}"
        asked = operator_id not in waiting and operator_id not in left_out
        if snapshot is None:
            failed += [operator_id] if asked else []
            snapshot = _carried(operator_id, args.previous, on_map)
        try:
            if snapshot is not None:
                live_snapshot.write(snapshot, args.out)
        except SnapshotError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        entries[operator_id] = RefreshEntry(
            fetched_at=snapshot.fetched_at if snapshot else None,
            last_contact_at=finished if asked else (before.last_contact_at if before else None),
            refreshed=laid is not None,
            requests=requests,
            locations=len(snapshot.locations) if snapshot else 0,
            evses=sum(len(e) for e in snapshot.locations.values()) if snapshot else 0,
            not_on_map=laid.not_on_map if laid else 0,
            not_in_feed=laid.not_in_feed if laid else 0,
            ambiguous=laid.ambiguous if laid else 0,
            note=note,
        )
        line = entries[operator_id]
        print(
            f"{operator_id}: "
            + (
                f"{line.locations:,} locations, {line.evses:,} EVSEs, {requests} request(s)"
                f"; {line.not_on_map:,} not on the map, {line.not_in_feed:,} not in the feed"
                if line.refreshed
                else f"{note}"
                + ("; kept its last snapshot" if snapshot is not None else "; no snapshot")
            ),
            flush=True,
        )
    record = RefreshLog(
        generated_at=finished, map_generated_at=shown.generated_at, operators=entries
    )
    path = args.out / "live" / "refresh.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(record.model_dump_json(indent=1) + "\n", encoding="utf-8")
    print(f"{sum(e.refreshed for e in entries.values())} of {len(entries)} refreshed; {path}")
    return EXIT_SOME_FAILED if failed else 0


if __name__ == "__main__":
    sys.exit(main())
