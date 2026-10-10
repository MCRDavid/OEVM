"""Run operator adapters.

    uv run python -m pipeline.run --fixtures
    uv run python -m pipeline.run --live chargy --max-pages 1
    uv run python -m pipeline.run --live all --log-dir logs --publish build

--fixtures replays the recorded responses in tests/fixtures/<operator>/ and never uses
the network. --live calls the operator's real feed, so use it sparingly. It only runs
for operators that are enabled in the registry, which requires their licence terms to
have been checked.

--live all fetches every enabled operator (the daily workflow). Operators that share a
host are fetched one after another; groups that share no host are fetched at the same
time, so a slow feed no longer holds up the others. If one operator fails, its failure
is logged, the others are still fetched and published, and the map keeps showing the
failed operator's last good copy from --previous (the files last published) when there is
one (ADR 0018). The exit code is 3 when every failed operator kept its last good copy,
and 2 when one was left off the map, so a failure is visible without holding back the
rest. Live runs print how far each operator has got as they go (pipeline.progress).
"""

import argparse
import json
import sys
import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime
from pathlib import Path

import httpx

import adapters.jolt
import adapters.ocpi_221
from adapters.http import FeedError, PoliteClient, operator_hosts
from adapters.ocpi_221 import AdapterResult
from adapters.progress import NO_PROGRESS, PageProgress
from adapters.replay import ReplayTransport
from pipeline import health, publish, tariffs
from pipeline.progress import RunProgress
from pipeline.registry import ROOT, RegistryError, load_registry
from schema.operator import OperatorConfig
from schema.runlog import MAX_ISSUE_LENGTH, RunLog

FIXTURES_DIR = ROOT / "tests" / "fixtures"
ADAPTERS = {"ocpi_221": adapters.ocpi_221.fetch}
# Operators whose registry adapter is "custom", by operator id.
CUSTOM_ADAPTERS = {"jolt": adapters.jolt.fetch}
# Sent in place of a real key when replaying fixtures, which never reach the network.
FIXTURE_KEY = "fixture-replay-not-a-real-key"
# --live ALL_ENABLED fetches every operator that is enabled in the registry.
ALL_ENABLED = "all"
# Exit code when --live all published some operators but at least one failed and is not
# on the map.
EXIT_SOME_FAILED = 2
# Exit code when at least one operator failed and every one that failed kept its last
# good copy on the map.
EXIT_KEPT_LAST_GOOD = 3


def host_groups(configs: list[OperatorConfig]) -> list[list[OperatorConfig]]:
    """Split operators into groups that share no host, keeping the given order.

    Two operators go in the same group when they share a host, directly or through other
    operators, so no host is ever asked by two fetches at once (CLAUDE.md, rate limits).
    """
    groups: list[tuple[set[str], list[OperatorConfig]]] = []
    for config in configs:
        hosts = set(operator_hosts(config))
        members = [config]
        for group in [g for g in groups if g[0] & hosts]:
            groups.remove(group)
            hosts |= group[0]
            members = group[1] + members
        groups.append((hosts, members))
    order = {config.id: number for number, config in enumerate(configs)}
    ordered = [sorted(members, key=lambda c: order[c.id]) for _, members in groups]
    return sorted(ordered, key=lambda members: order[members[0].id])


def run_operator(
    config: OperatorConfig,
    *,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    date_from: datetime | None = None,
    page_size: int | None = None,
    max_pages: int | None = None,
    key: str | None = None,
    progress: PageProgress = NO_PROGRESS,
    notice: Callable[[str], None] = lambda _text: None,
) -> AdapterResult:
    """Fetch one operator. A FeedError raised here carries `requests`, the number made."""
    if config.adapter == "custom":
        fetch = CUSTOM_ADAPTERS.get(config.id)
        if fetch is None:
            raise FeedError(f"{config.id}: its custom adapter is not built yet")
    else:
        fetch = ADAPTERS.get(config.adapter)
        if fetch is None:
            raise FeedError(f"{config.id}: the {config.adapter} adapter is not built yet")
    with PoliteClient(
        config, transport=transport, sleep=sleep, clock=clock, key=key, notice=notice
    ) as client:
        try:
            result = fetch(
                config,
                client,
                date_from=date_from,
                page_size=page_size,
                max_pages=max_pages,
                progress=progress,
            )
        except FeedError as exc:
            exc.requests = client.requests_made
            raise
        result.requests = client.requests_made
        result.issues = [*client.events, *result.issues]
        return result


def report(result: AdapterResult) -> str:
    lines = [f"{result.operator_id}: fetched {result.fetched_at:%Y-%m-%dT%H:%M:%SZ}"]
    for module in result.modules.values():
        total = "unknown" if module.total_reported is None else module.total_reported
        state = "complete" if module.complete else "incomplete (page limit, or see issues)"
        pages = f"{len(module.pages)} page" + ("" if len(module.pages) == 1 else "s")
        lines.append(
            f"  {module.module}: {pages}, {len(module.records)} records of {total} reported, "
            f"{state}"
        )
    lines.append(f"  kept: {len(result.locations)} locations, {len(result.tariffs)} tariffs")
    lines.append(f"  {tariffs.summary(tariffs.price_locations(result.locations, result.tariffs))}")
    lines.append(f"  issues ({len(result.issues)}):")
    lines += [f"    - {issue}" for issue in result.issues] or ["    none"]
    return "\n".join(lines)


def save_raw(result: AdapterResult, directory: Path) -> None:
    """Write each response as a recorded exchange (credentials already removed)."""
    directory.mkdir(parents=True, exist_ok=True)
    for module in result.modules.values():
        for number, page in enumerate(module.pages, start=1):
            path = directory / f"{module.module}_page{number}.json"
            path.write_text(json.dumps(page.to_exchange(), indent=2) + "\n", encoding="utf-8")


def _shorten(text: str) -> str:
    return text if len(text) <= MAX_ISSUE_LENGTH else text[: MAX_ISSUE_LENGTH - 3] + "..."


def _module_summaries(modules: dict) -> dict:
    return {
        name: {
            "pages": len(module.pages),
            "records": len(module.records),
            "reported": module.total_reported,
            "complete": module.complete,
        }
        for name, module in modules.items()
    }


def run_log(result: AdapterResult, mode: str) -> dict:
    """A summary of one run for the transparency page: counts and issues, never records."""
    log = {
        "operator": result.operator_id,
        "mode": mode,
        "fetched_at": result.fetched_at.isoformat().replace("+00:00", "Z"),
        "requests": result.requests,
        "complete": result.complete,
        "failed": False,
        "error": None,
        "modules": _module_summaries(result.modules),
        "kept": {"locations": len(result.locations), "tariffs": len(result.tariffs)},
        "health": health.health(result).model_dump(),
        "issues": [_shorten(issue) for issue in result.issues],
    }
    return RunLog.model_validate(log).model_dump(mode="json")


def failure_log(
    operator_id: str,
    mode: str,
    error: str,
    when: datetime,
    *,
    modules: dict | None = None,
    requests: int | None = None,
    kept_copy: tuple[datetime, int] | None = None,
) -> dict:
    """A summary of a run that stopped with an error, so the failure is visible.

    modules is what each module fetched before the error, requests how many were made,
    and kept_copy the fetch time and location count of the last good copy the map kept
    showing, if any.
    """
    log = {
        "operator": operator_id,
        "mode": mode,
        "fetched_at": _stamp(when),
        "requests": requests,
        "complete": False,
        "failed": True,
        "error": _shorten(error),
        "modules": _module_summaries(modules or {}),
        "kept": {"locations": 0, "tariffs": 0},
        "health": None,
        "issues": [_shorten(f"Run failed: {error}")],
    }
    if kept_copy is not None:
        kept_at, locations = kept_copy
        log["kept_copy"] = {"fetched_at": _stamp(kept_at), "locations": locations}
        log["issues"].append(f"The map kept showing the last good copy, fetched {_stamp(kept_at)}.")
    return RunLog.model_validate(log).model_dump(mode="json")


def _stamp(when: datetime) -> str:
    return when.astimezone(UTC).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _failure_log(
    operator_id: str,
    mode: str,
    failures: dict[str, tuple[str, datetime, dict, int | None]],
    kept_copy: tuple[datetime, int] | None = None,
) -> dict:
    error, when, modules, requests = failures[operator_id]
    return failure_log(
        operator_id,
        mode,
        error,
        when,
        modules=modules,
        requests=requests,
        kept_copy=kept_copy,
    )


def write_log(directory: Path, log: dict) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{log['operator']}.json"
    path.write_text(json.dumps(log, indent=2) + "\n", encoding="utf-8")


def save_output(result: AdapterResult, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for name, records in (("locations", result.locations), ("tariffs", result.tariffs)):
        data = [record.model_dump(mode="json") for record in records]
        (directory / f"{name}.json").write_text(json.dumps(data, indent=2) + "\n", "utf-8")
    (directory / "issues.txt").write_text("\n".join(result.issues) + "\n", encoding="utf-8")


def run_fixtures(operators: dict[str, OperatorConfig]) -> list[AdapterResult]:
    """Replay every fixture folder that has a manifest.json."""
    results = []
    for manifest_path in sorted(FIXTURES_DIR.glob("*/manifest.json")):
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        date_from = manifest.get("date_from")
        # Replays never go through the relay: the recordings hold the operator's own URLs.
        config = operators[manifest["operator"]].model_copy(update={"relay": None})
        results.append(
            run_operator(
                config,
                transport=ReplayTransport(manifest_path.parent),
                sleep=lambda _seconds: None,
                date_from=datetime.fromisoformat(date_from) if date_from else None,
                page_size=manifest.get("page_size"),
                max_pages=manifest.get("max_pages"),
                key=FIXTURE_KEY,
            )
        )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.run", description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixtures", action="store_true", help="replay recorded responses")
    mode.add_argument(
        "--live",
        metavar="OPERATOR",
        help=f"fetch one operator's real feed, or {ALL_ENABLED!r} for every enabled one",
    )
    parser.add_argument("--max-pages", type=int, help="stop after this many pages per module")
    parser.add_argument("--page-size", type=int, help="ask the server for this many records")
    parser.add_argument(
        "--date-from",
        type=datetime.fromisoformat,
        help="only records updated at or after this time, e.g. 2026-10-07T21:00:00+00:00",
    )
    parser.add_argument("--save-raw", type=Path, help="save each response here (use raw/)")
    parser.add_argument("--out", type=Path, help="save converted records here")
    parser.add_argument(
        "--publish",
        type=Path,
        metavar="DIR",
        help="merge the results and write the map files under DIR/data (not site/)",
    )
    parser.add_argument(
        "--previous",
        type=Path,
        metavar="DIR",
        help="the files last published (DIR/data); an operator that fails keeps its copy there",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        help="save a run summary per operator here, for the transparency page",
    )
    args = parser.parse_args(argv)

    mode = "fixtures" if args.fixtures else "live"
    failed: list[str] = []
    # Why each failed operator failed, for its run log: (error, time, modules, requests).
    failures: dict[str, tuple[str, datetime, dict, int | None]] = {}
    try:
        operators = load_registry()
        if args.fixtures:
            results = run_fixtures(operators)
        else:
            if args.live == ALL_ENABLED:
                configs = [operators[i] for i in sorted(operators) if operators[i].enabled]
                if not configs:
                    raise FeedError("no operator is enabled in the registry")
            else:
                config = operators.get(args.live)
                if config is None:
                    raise FeedError(f"no operator {args.live!r} in the registry")
                if not config.enabled:
                    raise FeedError(
                        f"{config.id} is not enabled in the registry; check its licence terms first"
                    )
                configs = [config]
            progress = RunProgress(max_pages=args.max_pages)
            groups = host_groups(configs)
            progress.run_started([[config.id for config in group] for group in groups])
            numbers = {config.id: number for number, config in enumerate(configs, start=1)}

            def fetch_group(group: list[OperatorConfig]) -> list[AdapterResult | str]:
                """Fetch one group, one operator at a time. Failures come back as ids."""
                outcomes: list[AdapterResult | str] = []
                for config in group:
                    try:
                        reporter = progress.operator_started(
                            config, number=numbers[config.id], count=len(configs)
                        )
                        result = run_operator(
                            config,
                            date_from=args.date_from,
                            page_size=args.page_size,
                            max_pages=args.max_pages,
                            progress=reporter,
                            notice=lambda text, i=config.id: print(f"{i}: {text}", flush=True),
                        )
                    except FeedError as exc:
                        progress.operator_failed(config.id)
                        when = datetime.now(UTC)
                        failures[config.id] = (
                            str(exc),
                            when,
                            exc.modules or {},
                            getattr(exc, "requests", None),
                        )
                        if args.log_dir:
                            write_log(args.log_dir, _failure_log(config.id, mode, failures))
                        if len(configs) == 1:
                            raise
                        print(f"Error: {exc}", file=sys.stderr, flush=True)
                        outcomes.append(config.id)
                    else:
                        progress.operator_done(config.id, requests=result.requests)
                        outcomes.append(result)
                return outcomes

            # Groups share no host, so they run at the same time; within a group, one
            # operator at a time (CLAUDE.md, rate limits).
            with ThreadPoolExecutor(max_workers=len(groups)) as pool:
                outcomes = [o for group in pool.map(fetch_group, groups) for o in group]
            fetched = {o.operator_id: o for o in outcomes if not isinstance(o, str)}
            failed = [c.id for c in configs if c.id not in fetched]
            results = [fetched[c.id] for c in configs if c.id in fetched]
            progress.run_done(fetched=len(results), failed=failed)
            if not results:
                raise FeedError(f"every operator failed: {', '.join(failed)}")
    except (FeedError, RegistryError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    for result in results:
        print(report(result))
        if args.save_raw:
            save_raw(result, args.save_raw / result.operator_id)
        if args.out:
            save_output(result, args.out / result.operator_id)
        if args.log_dir:
            write_log(args.log_dir, run_log(result, mode))
    kept: dict[str, datetime] = {}
    if not results:
        print("No fixture sets found.")
    elif args.publish:
        generated_at = max(r.fetched_at for r in results)
        copies = []
        for operator_id in failed:
            copy, why = (None, "no --previous files were given")
            if args.previous is not None:
                copy, why = publish.last_good_copy(
                    args.previous, operator_id, operators[operator_id], generated_at
                )
            if copy is None:
                print(f"{operator_id}: no last good copy to show: {why}", file=sys.stderr)
            else:
                copies.append(copy)
        try:
            published = publish.publish(
                results,
                operators,
                args.publish,
                mode=mode,
                generated_at=generated_at,
                kept=copies,
            )
        except publish.PublishError as exc:
            print(f"Error: {exc}", file=sys.stderr)
            return 1
        print("\n".join(published.report))
        kept = published.kept
        if args.log_dir:
            for copy in copies:
                write_log(
                    args.log_dir,
                    _failure_log(
                        copy.operator_id,
                        mode,
                        failures,
                        kept_copy=(copy.entry.fetched_at, copy.entry.mapped),
                    ),
                )
    left_out = [operator_id for operator_id in failed if operator_id not in kept]
    if kept:
        shown = ", ".join(f"{i} (fetched {kept[i]:%Y-%m-%d %H:%M} UTC)" for i in sorted(kept))
        print(f"Failed, so the map shows the last good copy: {shown}", file=sys.stderr)
    if left_out:
        print(f"Failed, so left out: {', '.join(left_out)}", file=sys.stderr)
        return EXIT_SOME_FAILED
    return EXIT_KEPT_LAST_GOOD if kept else 0


if __name__ == "__main__":
    sys.exit(main())
