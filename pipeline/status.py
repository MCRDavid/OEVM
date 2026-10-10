"""Build the feed health page from run logs (blueprint task 8).

    uv run python -m pipeline.run --fixtures --log-dir logs
    uv run python -m pipeline.status --runs logs --out build [--previous old-status.json]

writes build/status/index.html and build/data/status.json. Each run is added to the
history from --previous (the status.json last published), keeping one entry per day for
30 days, so the daily fetch (blueprint task 10) builds up a trend.

The page reports what this project received from each operator, counted automatically,
with neutral, dated wording. It does not say whether anyone has met their legal duties.
Sources, findings and engagement evidence are on the transparency page. It has no
scripts, no cookies and no third-party files.
"""

import argparse
import json
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from pipeline.registry import ROOT, RegistryError, load_registry
from pipeline.transparency import LINKS, STYLE, _e, _link, short_disclaimer
from schema.operator import OperatorConfig
from schema.published import HistoryPoint, OperatorStatus, StatusFile
from schema.runlog import RunLog

HISTORY_DAYS = 30


class StatusError(Exception):
    """The run logs or the previous status file cannot be used."""


def load_runs(directory: Path) -> dict[str, RunLog]:
    """Read run logs written by pipeline.run --log-dir.

    Each log must match schema.runlog.RunLog exactly and be named after its operator, so
    the page only ever publishes the fields that model allows.
    """
    runs = {}
    for path in sorted(directory.glob("*.json")):
        try:
            run = RunLog.model_validate_json(path.read_text(encoding="utf-8"))
        except ValidationError as exc:
            problem = exc.errors()[0]
            where = ".".join(str(part) for part in problem["loc"]) or "the file"
            raise StatusError(
                f"{path.name} is not a valid run log: {where}: {problem['msg']}"
            ) from None
        if run.operator != path.stem:
            raise StatusError(
                f"{path.name} is the run log for {run.operator!r}; name it {run.operator}.json"
            )
        runs[run.operator] = run
    return runs


def _pct(part: int, whole: int) -> float | None:
    return round(100 * part / whole, 1) if whole else None


def _when(run: RunLog) -> datetime:
    return datetime.fromisoformat(run.fetched_at.replace("Z", "+00:00"))


def history_point(run: RunLog) -> HistoryPoint:
    health = run.health
    return HistoryPoint(
        date=_when(run).date(),
        fetched_at=_when(run),
        failed=run.failed,
        complete=run.complete,
        locations=run.kept.locations,
        connectors_with_tariff_pct=(
            _pct(health.connectors_with_tariff, health.connectors) if health else None
        ),
        evses_with_status_pct=_pct(health.evses_with_status, health.evses) if health else None,
    )


def build(
    operators: dict[str, OperatorConfig],
    runs: dict[str, RunLog],
    previous: StatusFile | None,
    now: datetime,
) -> StatusFile:
    """The new status: previous history plus these runs, for every switched-on operator."""
    enabled = {i: c for i, c in operators.items() if c.enabled}
    unknown = sorted(set(runs) - set(enabled))
    if unknown:
        raise StatusError(f"run logs for operators not switched on: {', '.join(unknown)}")
    cutoff = (now - timedelta(days=HISTORY_DAYS - 1)).date()
    statuses = {}
    for operator_id, config in sorted(enabled.items()):
        before = previous.operators.get(operator_id) if previous else None
        history = {p.date: p for p in (before.history if before else [])}
        last_attempt = before.last_attempt if before else None
        last_success = before.last_success if before else None
        latest = before.latest if before else None
        run = runs.get(operator_id)
        if run is not None:
            point = history_point(run)
            if point.date not in history or history[point.date].fetched_at <= point.fetched_at:
                history[point.date] = point
            if last_attempt is None or point.fetched_at >= last_attempt:
                last_attempt, latest = point.fetched_at, run
            if not run.failed and (last_success is None or point.fetched_at >= last_success):
                last_success = point.fetched_at
        statuses[operator_id] = OperatorStatus(
            name=config.display_name,
            last_attempt=last_attempt,
            last_success=last_success,
            latest=latest,
            history=[history[d] for d in sorted(history) if d >= cutoff],
        )
    return StatusFile(generated_at=now, operators=statuses)


# HTML


def _time(value: datetime | None) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%d %H:%M UTC") if value else "Not yet"


def _share(part: int, whole: int) -> str:
    if not whole:
        return "None received"
    return f"{part} of {whole} ({_pct(part, whole):g}%)"


def result_label(status: OperatorStatus) -> str:
    run = status.latest
    if run is None:
        return "Not fetched yet"
    if run.failed and run.kept_copy is not None:
        kept_at = datetime.fromisoformat(run.kept_copy.fetched_at.replace("Z", "+00:00"))
        return (
            f"Fetch failed; the map still shows its last good copy, fetched {_time(kept_at)} "
            f"({run.kept_copy.locations} locations)"
        )
    if run.failed:
        return "Fetch failed"
    return "Fetched" if run.complete else "Fetched, incomplete"


def _latest_table(data: StatusFile) -> str:
    rows = []
    for status in data.operators.values():
        run = status.latest
        health = run.health if run else None
        cells = ["", "", "", "", ""]
        if health:
            age = health.median_last_updated_days
            cells = [
                _share(health.locations_in_uk, health.locations),
                _share(health.evses_with_status, health.evses),
                _share(health.connectors_with_tariff, health.connectors),
                "Not given" if age is None else f"{age:g} days",
                "<br>".join(_e(issue) for issue in run.issues) or "None",
            ]
        elif run:
            cells[4] = "<br>".join(_e(issue) for issue in run.issues)
        rows.append(
            "<tr>"
            f'<th scope="row">{_e(status.name)}</th>'
            f"<td>{_e(result_label(status))}</td>"
            f"<td>{_e(_time(status.last_attempt))}</td>"
            f"<td>{_e(_time(status.last_success))}</td>"
            + "".join(f"<td>{cell}</td>" for cell in cells)
            + "</tr>"
        )
    return (
        "<table><caption>Latest run for each operator</caption><thead><tr>"
        '<th scope="col">Operator</th><th scope="col">Result</th>'
        '<th scope="col">Last attempt</th><th scope="col">Last success</th>'
        '<th scope="col">Locations with UK coordinates</th>'
        '<th scope="col">EVSEs with a status</th>'
        '<th scope="col">Connectors with a tariff that was found</th>'
        '<th scope="col">Median age of locations&rsquo; last update</th>'
        '<th scope="col">Problems logged</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _point_label(point: HistoryPoint) -> str:
    if point.failed:
        return "Fetch failed"
    return "Fetched" if point.complete else "Fetched, incomplete"


def _percent(value: float | None) -> str:
    return "" if value is None else f"{value:g}%"


def _trend(status: OperatorStatus) -> str:
    points = status.history
    if not points:
        return f"<h3>{_e(status.name)}</h3><p>No runs recorded yet.</p>"
    ok = sum(not p.failed for p in points)
    counts = [p.locations for p in points if not p.failed]
    span = (
        f"; locations received ranged from {min(counts)} to {max(counts)}"
        if counts and min(counts) != max(counts)
        else (f"; {counts[0]} locations received each time" if counts else "")
    )
    rows = "".join(
        "<tr>"
        f"<td>{_e(p.date)}</td>"
        f"<td>{_point_label(p)}</td>"
        f"<td>{_e(p.locations)}</td>"
        f"<td>{_percent(p.connectors_with_tariff_pct)}</td>"
        f"<td>{_percent(p.evses_with_status_pct)}</td>"
        "</tr>"
        for p in reversed(points)
    )
    return (
        f"<h3>{_e(status.name)}</h3>"
        f"<p>{ok} of {len(points)} daily runs fetched data{_e(span)}.</p>"
        '<details><summary>Day by day</summary><div class="table-wrap"><table>'
        f"<caption>{_e(status.name)}: the last {HISTORY_DAYS} days</caption>"
        '<thead><tr><th scope="col">Date</th><th scope="col">Result</th>'
        '<th scope="col">Locations</th><th scope="col">Connectors with a tariff</th>'
        '<th scope="col">EVSEs with a status</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div></details>"
    )


def render_html(data: StatusFile) -> str:
    links = "".join(f"<li>{_link(url, text)}</li>" for text, url in LINKS)
    trends = "".join(_trend(status) for status in data.operators.values())
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Feed health: OEVM</title>
<style>{STYLE}</style>
</head>
<body>
<header>
<h1>Feed health</h1>
<p>Generated {_e(_time(data.generated_at))}. These figures are counted automatically from
the data each operator published, as this project received it. They describe that data;
they do not say whether anyone has met their legal duties. Sources, findings and
evidence are on the <a href="../transparency/">transparency page</a>.</p>
</header>
<main>
<h2>Latest runs</h2>
<div class="table-wrap">{_latest_table(data)}</div>
<h2>The last {HISTORY_DAYS} days</h2>
{trends}
</main>
<footer>
<p class="note">{_e(short_disclaimer())}</p>
<ul>{links}</ul>
<p>This page has no cookies, no tracking and no scripts.</p>
</footer>
</body>
</html>
"""


def render_json(data: StatusFile) -> str:
    return json.dumps(data.model_dump(mode="json"), indent=2, ensure_ascii=False) + "\n"


def outputs(runs_dir: Path, out_dir: Path, previous: Path | None, now: datetime) -> dict[Path, str]:
    if out_dir.resolve() == (ROOT / "site").resolve():
        raise StatusError("write to a build folder, not the committed site/ folder")
    before = None
    if previous is not None and previous.exists():
        try:
            before = StatusFile.model_validate_json(previous.read_text(encoding="utf-8"))
        except ValidationError as exc:
            problem = exc.errors()[0]["msg"]
            raise StatusError(f"{previous} is not a valid status file: {problem}") from None
    data = build(load_registry(), load_runs(runs_dir), before, now)
    page, json_text = render_html(data), render_json(data)
    StatusFile.model_validate_json(json_text)
    return {out_dir / "status" / "index.html": page, out_dir / "data" / "status.json": json_text}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.status", description=__doc__)
    parser.add_argument("--runs", type=Path, required=True, help="run logs from --log-dir")
    parser.add_argument("--out", type=Path, required=True, help="build folder (not site/)")
    parser.add_argument("--previous", type=Path, help="the status.json last published")
    parser.add_argument(
        "--now", type=datetime.fromisoformat, help="time to stamp the page (default: now)"
    )
    args = parser.parse_args(argv)
    now = args.now or datetime.now(UTC).replace(microsecond=0)
    if now.tzinfo is None:
        parser.error("--now needs a time zone, for example 2026-10-08T12:00:00+00:00")
    try:
        files = outputs(args.runs, args.out, args.previous, now)
    except (RegistryError, StatusError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    for path, text in files.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        print(f"Wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
