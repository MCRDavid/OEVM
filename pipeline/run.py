"""Run operator adapters.

    uv run python -m pipeline.run --fixtures
    uv run python -m pipeline.run --live chargy --max-pages 1

--fixtures replays the recorded responses in tests/fixtures/<operator>/ and never uses
the network. --live calls the operator's real feed, so use it sparingly. It only runs
for operators that are enabled in the registry, which requires their licence terms to
have been checked.
"""

import argparse
import json
import sys
import time
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import httpx

import adapters.ocpi_221
from adapters.http import FeedError, PoliteClient
from adapters.ocpi_221 import AdapterResult
from adapters.replay import ReplayTransport
from pipeline.registry import ROOT, RegistryError, load_registry
from schema.operator import OperatorConfig

FIXTURES_DIR = ROOT / "tests" / "fixtures"
ADAPTERS = {"ocpi_221": adapters.ocpi_221.fetch}


def run_operator(
    config: OperatorConfig,
    *,
    transport: httpx.BaseTransport | None = None,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
    date_from: datetime | None = None,
    page_size: int | None = None,
    max_pages: int | None = None,
) -> AdapterResult:
    fetch = ADAPTERS.get(config.adapter)
    if fetch is None:
        raise FeedError(f"{config.id}: the {config.adapter} adapter is not built yet")
    with PoliteClient(config, transport=transport, sleep=sleep, clock=clock) as client:
        result = fetch(
            config, client, date_from=date_from, page_size=page_size, max_pages=max_pages
        )
        result.requests = client.requests_made
        return result


def report(result: AdapterResult) -> str:
    lines = [f"{result.operator_id}: fetched {result.fetched_at:%Y-%m-%dT%H:%M:%SZ}"]
    for module in result.modules.values():
        total = "unknown" if module.total_reported is None else module.total_reported
        state = "complete" if module.complete else "stopped early (page limit)"
        pages = f"{len(module.pages)} page" + ("" if len(module.pages) == 1 else "s")
        lines.append(
            f"  {module.module}: {pages}, {len(module.records)} records of {total} reported, "
            f"{state}"
        )
    lines.append(f"  kept: {len(result.locations)} locations, {len(result.tariffs)} tariffs")
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


def run_log(result: AdapterResult, mode: str) -> dict:
    """A summary of one run for the transparency page: counts and issues, never records."""
    return {
        "operator": result.operator_id,
        "mode": mode,
        "fetched_at": result.fetched_at.isoformat().replace("+00:00", "Z"),
        "requests": result.requests,
        "complete": result.complete,
        "failed": False,
        "error": None,
        "modules": {
            name: {
                "pages": len(module.pages),
                "records": len(module.records),
                "reported": module.total_reported,
                "complete": module.complete,
            }
            for name, module in result.modules.items()
        },
        "kept": {"locations": len(result.locations), "tariffs": len(result.tariffs)},
        "issues": result.issues,
    }


def failure_log(operator_id: str, mode: str, error: str, when: datetime) -> dict:
    """A summary of a run that stopped with an error, so the failure is visible."""
    return {
        "operator": operator_id,
        "mode": mode,
        "fetched_at": when.astimezone(UTC)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        "requests": None,
        "complete": False,
        "failed": True,
        "error": error,
        "modules": {},
        "kept": {"locations": 0, "tariffs": 0},
        "issues": [f"Run failed: {error}"],
    }


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
        results.append(
            run_operator(
                operators[manifest["operator"]],
                transport=ReplayTransport(manifest_path.parent),
                sleep=lambda _seconds: None,
                date_from=datetime.fromisoformat(date_from) if date_from else None,
                page_size=manifest.get("page_size"),
                max_pages=manifest.get("max_pages"),
            )
        )
    return results


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.run", description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--fixtures", action="store_true", help="replay recorded responses")
    mode.add_argument("--live", metavar="OPERATOR", help="fetch one operator's real feed")
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
        "--log-dir",
        type=Path,
        help="save a run summary per operator here, for the transparency page",
    )
    args = parser.parse_args(argv)

    mode = "fixtures" if args.fixtures else "live"
    try:
        operators = load_registry()
        if args.fixtures:
            results = run_fixtures(operators)
        else:
            config = operators.get(args.live)
            if config is None:
                raise FeedError(f"no operator {args.live!r} in the registry")
            if not config.enabled:
                raise FeedError(
                    f"{config.id} is not enabled in the registry; check its licence terms first"
                )
            try:
                results = [
                    run_operator(
                        config,
                        date_from=args.date_from,
                        page_size=args.page_size,
                        max_pages=args.max_pages,
                    )
                ]
            except FeedError as exc:
                if args.log_dir:
                    write_log(
                        args.log_dir, failure_log(config.id, mode, str(exc), datetime.now(UTC))
                    )
                raise
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
    if not results:
        print("No fixture sets found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
