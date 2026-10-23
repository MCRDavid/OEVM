"""Build the feed health page from run logs (blueprint task 8).

    uv run python -m pipeline.run --fixtures --log-dir logs
    uv run python -m pipeline.status --runs logs --out build [--previous old-status.json]
        [--map build/data/locations.geojson]

writes build/status/index.html and build/data/status.json. Each run is added to the
history from --previous (the status.json last published), keeping one entry per day for
30 days, so the daily fetch (blueprint task 10) builds up a trend. With --map (the map
file just published), the page also lists every location the map hides unless a visitor
asks, because its name marks it private or restricted (pipeline/access.py, ADR 0023), and,
from the manifest beside it, the locations left off as copies of another network's own
feed (own_feed_over_copies, ADR 0027).
With --daily-runs (written by pipeline.daily_runs record), it also shows how the daily
fetch started each day, and how often GitHub's own schedule started it on time (ADR 0024).

The page reports what this project received from each operator, counted automatically,
with neutral, dated wording. It does not say whether anyone has met their legal duties.
Sources, findings and engagement evidence are on the transparency page. It has no
scripts, no cookies and no third-party files.

Each operator also gets a coloured circle for a view at a glance (the owner's request, 11
October 2026): green working, yellow some problems but data on the map, red nothing on
the map, grey switched off or not fetched yet. The colours come only from the run logs
and the registry, so they describe what this project received, not any operator's duties.
"""

import argparse
import json
import sys
from collections.abc import Sequence
from datetime import UTC, datetime, timedelta
from pathlib import Path

from pydantic import ValidationError

from pipeline import daily_runs
from pipeline.registry import ROOT, RegistryError, load_registry
from pipeline.transparency import LINKS, STYLE, _e, _link, short_disclaimer
from schema.operator import OperatorConfig
from schema.published import HistoryPoint, Manifest, MapLayer, OperatorStatus, StatusFile
from schema.runlog import Health, RunLog

HISTORY_DAYS = 30
# A latest run older than this shows yellow, so a day the daily fetch missed is visible.
STALE_AFTER = timedelta(days=2)

GREEN, YELLOW, RED, GREY = "green", "yellow", "red", "grey"
# Unicode has no grey circle emoji, so grey is the white circle, which most systems draw
# light grey with an outline.
CIRCLES = {
    GREEN: "\N{LARGE GREEN CIRCLE}",
    YELLOW: "\N{LARGE YELLOW CIRCLE}",
    RED: "\N{LARGE RED CIRCLE}",
    GREY: "\N{MEDIUM WHITE CIRCLE}",
}
LABELS = {
    GREEN: "Working",
    YELLOW: "Some problems",
    RED: "Not working",
    GREY: "Switched off",
}
# How each colour's count reads in the summary line.
COUNTED = {
    GREEN: "working",
    YELLOW: "with some problems",
    RED: "not working",
    GREY: "switched off or not fetched yet",
}
MEANINGS = {
    GREEN: f"the last fetch received complete data, in the last {STALE_AFTER.days} days. "
    "Data quirks listed under Problems logged do not change the colour.",
    YELLOW: "there is data on the map, but the last fetch was incomplete, failed (so the "
    f"map shows the last good copy) or is more than {STALE_AFTER.days} days old.",
    RED: "the last fetch failed or received no locations, and the map shows nothing from "
    "this operator.",
    GREY: "this project does not fetch the operator's data, or has not fetched it yet.",
}


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
        connectors_with_tariff_from_related_pct=(
            _pct(health.connectors_with_tariff_from_related, health.connectors) if health else None
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


RELATED_FEED = "a related operator&rsquo;s feed"


def _tariff_share(health: Health) -> str:
    """Connectors with a tariff found in the operator's own feed, then any more priced from
    a related operator's feed (ADR 0020), so a feed that names only those does not look as
    if none was found."""
    share = _share(health.connectors_with_tariff, health.connectors)
    more = health.connectors_with_tariff_from_related
    return f"{share} from its own feed<br>{more} more from {RELATED_FEED}" if more else share


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


def colour(status: OperatorStatus, now: datetime) -> str:
    """Green, yellow, red or grey for a switched-on operator, from its latest run."""
    run = status.latest
    if run is None:
        return GREY
    if run.failed:
        return YELLOW if run.kept_copy is not None and run.kept_copy.locations else RED
    if not run.kept.locations:
        return RED
    if not run.complete or now - _when(run) > STALE_AFTER:
        return YELLOW
    return GREEN


def _circle(colour: str, label: str | None = None) -> str:
    label = label or LABELS[colour]
    return (
        f'<span class="circle" role="img" aria-label="{_e(label)}" title="{_e(label)}">'
        f"{CIRCLES[colour]}</span>"
    )


def _operator_circle(status: OperatorStatus, now: datetime) -> str:
    shown = colour(status, now)
    return _circle(shown, "Not fetched yet" if status.latest is None else None)


def _at_a_glance(data: StatusFile, switched_off: Sequence[str]) -> str:
    counts = dict.fromkeys(CIRCLES, 0)
    for status in data.operators.values():
        counts[colour(status, data.generated_at)] += 1
    counts[GREY] += len(switched_off)
    summary = ", ".join(f"{_circle(shade)} {counts[shade]} {COUNTED[shade]}" for shade in CIRCLES)
    key = "".join(
        f"<li>{_circle(shade)} <strong>{LABELS[shade]}</strong>: {_e(MEANINGS[shade])}</li>"
        for shade in CIRCLES
    )
    total = sum(counts.values())
    return f'<p>Of {total} operators in the registry: {summary}.</p><ul class="key">{key}</ul>'


def _switched_off(names: Sequence[str]) -> str:
    if not names:
        return ""
    items = "".join(f"<li>{_circle(GREY)} {_e(name)}</li>" for name in names)
    return (
        "<h2>Switched off</h2>"
        "<p>These operators are in this project&rsquo;s registry, but their data is not "
        "fetched, so none of it is on the map. The "
        '<a href="../transparency/">transparency page</a> gives the status of each one and '
        f'the steps taken so far.</p><ul class="off">{items}</ul>'
    )


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
                _tariff_share(health),
                "Not given" if age is None else f"{age:g} days",
                "<br>".join(_e(issue) for issue in run.issues) or "None",
            ]
        elif run:
            cells[4] = "<br>".join(_e(issue) for issue in run.issues)
        rows.append(
            "<tr>"
            f'<th scope="row">{_operator_circle(status, data.generated_at)} {_e(status.name)}</th>'
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


def _has_related(status: OperatorStatus) -> bool:
    """True when the latest run or any day in the history has a second tariff figure."""
    health = status.latest.health if status.latest else None
    return bool(
        (health and health.connectors_with_tariff_from_related)
        or any(p.connectors_with_tariff_from_related_pct for p in status.history)
    )


def _related_note(data: StatusFile) -> str:
    """Why some operators have a second tariff figure; empty when none has."""
    if not any(_has_related(status) for status in data.operators.values()):
        return ""
    return (
        "<p>Some connectors name a tariff that is not in their own operator&rsquo;s feed but "
        "is in the feed of a related operator fetched in the same run. Where the repository "
        "owner has decided the two operators are related, the map prices those connectors "
        "from that exact tariff, never by its name, and the tables on this page count them "
        "after the figure for the operator&rsquo;s own feed. The "
        '<a href="../transparency/">transparency page</a> names the related operators and '
        "gives the reasons.</p>"
    )


def _point_label(point: HistoryPoint) -> str:
    if point.failed:
        return "Fetch failed"
    return "Fetched" if point.complete else "Fetched, incomplete"


def _percent(value: float | None) -> str:
    return "" if value is None else f"{value:g}%"


def _tariff_percent(point: HistoryPoint) -> str:
    own, more = point.connectors_with_tariff_pct, point.connectors_with_tariff_from_related_pct
    if not more:
        return _percent(own)
    return f"{_percent(own)} from its own feed, {more:g}% from {RELATED_FEED}"


def _trend(status: OperatorStatus, now: datetime) -> str:
    heading = f"<h3>{_operator_circle(status, now)} {_e(status.name)}</h3>"
    points = status.history
    if not points:
        return f"{heading}<p>No runs recorded yet.</p>"
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
        f"<td>{_tariff_percent(p)}</td>"
        f"<td>{_percent(p.evses_with_status_pct)}</td>"
        "</tr>"
        for p in reversed(points)
    )
    return (
        f"{heading}"
        f"<p>{ok} of {len(points)} daily runs fetched data{_e(span)}.</p>"
        '<details><summary>Day by day</summary><div class="table-wrap"><table>'
        f"<caption>{_e(status.name)}: the last {HISTORY_DAYS} days</caption>"
        '<thead><tr><th scope="col">Date</th><th scope="col">Result</th>'
        '<th scope="col">Locations</th><th scope="col">Connectors with a tariff</th>'
        '<th scope="col">EVSEs with a status</th></tr></thead>'
        f"<tbody>{rows}</tbody></table></div></details>"
    )


# One row per hidden location: network, location name, why it is hidden.
PrivateRow = tuple[str, str, str]


def _why_hidden(priv: str | None, taxi: bool) -> str:
    reasons = [f"Its name includes \u201c{priv}\u201d" if priv else None]
    reasons.append("every charge point is marked for taxis only" if taxi else None)
    text = "; ".join(r for r in reasons if r)
    return text[0].upper() + text[1:]


def private_rows(layer: MapLayer, operators: dict[str, OperatorConfig]) -> list[PrivateRow]:
    """Every location in the map file that the map hides unless asked: marked private or
    restricted by its name, or taxis only at every charge point, by network and name."""
    rows = [
        (
            operators[f.properties.op].display_name
            if f.properties.op in operators
            else f.properties.op,
            f.properties.name or "Name not given",
            _why_hidden(f.properties.priv, f.properties.taxi),
        )
        for f in layer.features
        if f.properties.priv or f.properties.taxi
    ]
    return sorted(rows, key=lambda row: (row[0].lower(), row[1].lower()))


def _private_section(rows: list[PrivateRow] | None) -> str:
    intro = (
        '<h2 id="private">Hidden on the map unless asked for</h2>'
        "<p>Locations whose name, as the operator published it, marks them private or "
        "restricted, and locations where the operator marks every charge point for taxis "
        "only. The map hides them unless a visitor ticks &ldquo;Show chargers marked "
        "private or restricted&rdquo;. The phrases looked for, and the owner&rsquo;s "
        'decisions on taxis, are on the <a href="../transparency/#private">transparency '
        "page</a>.</p>"
    )
    if rows is None:
        return intro + "<p>The map files were not available when this page was built.</p>"
    if not rows:
        return intro + "<p>No location in the latest map files is hidden this way.</p>"
    body = "".join(
        f"<tr><td>{_e(network)}</td><td>{_e(name)}</td><td>{_e(why)}</td></tr>"
        for network, name, why in rows
    )
    return (
        f'{intro}<div class="table-wrap"><table><caption>{len(rows)} location'
        f"{'' if len(rows) == 1 else 's'} hidden unless asked for</caption>"
        '<thead><tr><th scope="col">Network</th><th scope="col">Location</th>'
        '<th scope="col">Why</th></tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


# The feed carrying copies, the network whose own feed is shown instead, the ids left off.
CopyRow = tuple[str, str, list[str]]


def copy_rows(manifest: Manifest, operators: dict[str, OperatorConfig]) -> list[CopyRow]:
    """Each feed's locations left off as copies of another network's own feed (ADR 0027)."""

    def name(i: str) -> str:
        return operators[i].display_name if i in operators else i

    rows = []
    for feed, entry in manifest.operators.items():
        for owner in sorted(entry.replaced_by):
            prefix = f"{feed}:"
            if owner in operators:
                config = operators[owner]
                prefix += f"{config.ocpi_country_code}:{config.ocpi_party_id}:"
            ids = [i for i in entry.replaced_ids if i.startswith(prefix)]
            rows.append((name(feed), name(owner), ids))
    return sorted(rows, key=lambda row: (row[0].lower(), row[1].lower()))


def _copies_section(rows: list[CopyRow] | None) -> str:
    intro = (
        '<h2 id="copies">Shown from the network&rsquo;s own feed</h2>'
        "<p>Some feeds also carry another network&rsquo;s locations, under that "
        "network&rsquo;s own country and party codes. Where the repository owner has "
        "decided so for a network, those copies are left off the map while the "
        "network&rsquo;s own feed is on it, so each site is shown once, from its own "
        'operator. The decisions are on the <a href="../transparency/">transparency '
        "page</a>.</p>"
    )
    if rows is None:
        return intro + "<p>The map files were not available when this page was built.</p>"
    if not rows:
        return intro + "<p>No location in the latest map files was left off this way.</p>"
    body = "".join(
        f"<tr><td>{_e(feed)}</td><td>{_e(owner)}</td><td>{len(ids)}"
        "<details><summary>Location ids</summary><ul>"
        + "".join(f"<li>{_e(i)}</li>" for i in ids)
        + "</ul></details></td></tr>"
        for feed, owner, ids in rows
    )
    return (
        f'{intro}<div class="table-wrap"><table><caption>Locations left off as copies'
        '</caption><thead><tr><th scope="col">Feed</th><th scope="col">Network whose own '
        'feed is shown</th><th scope="col">Locations left off</th></tr></thead>'
        f"<tbody>{body}</tbody></table></div>"
    )


def _day(value) -> str:
    return f"{value.day} {value:%B %Y}"


def _daily_runs_section(record: "daily_runs.Record | str") -> str:
    """How the daily fetch started; a string is the reason the record is missing."""
    intro = (
        '<h2 id="daily-runs">How the daily fetch started</h2>'
        "<p>The daily fetch is a GitHub Actions workflow. It can be started by a timer on "
        "this project&rsquo;s Cloudflare Worker, by GitHub&rsquo;s own schedule, or by "
        "hand. GitHub says scheduled runs can be delayed when it is busy, and some dropped, "
        "so its schedule is kept as a backup. When a timer or scheduled run finds that "
        "day&rsquo;s fetch has already run, it stops without fetching. These figures are "
        "read from GitHub&rsquo;s list of the workflow&rsquo;s runs; days are in UTC.</p>"
    )
    if isinstance(record, str):
        return f"{intro}<p>{_e(record)}</p>"
    summary = daily_runs.summarise(record)
    since = _day(record.since)
    items = [f"Days the map was updated: {summary.days_updated} of {summary.days}, since {since}."]
    if summary.schedule_runs:
        median = summary.schedule_median_delay
        items.append(
            f"GitHub&rsquo;s schedule started a run on {summary.schedule_days} of "
            f"{summary.days} days. {summary.schedule_on_time} of its "
            f"{summary.schedule_runs} runs started within "
            f"{daily_runs.duration(daily_runs.ON_TIME)} of the time set"
            + (f"; the median delay was {daily_runs.duration(median)}." if median else ".")
        )
    else:
        items.append(f"GitHub&rsquo;s schedule started no run since {since}.")
    if summary.timer_since:
        items.append(
            f"The Cloudflare timer started a run on {summary.timer_days} of "
            f"{summary.timer_span} days since its first run on "
            f"{_day(summary.timer_since)}."
        )
    else:
        items.append(f"The Cloudflare timer started no run since {since}.")
    by_day: dict = {}
    for run in record.runs:
        by_day.setdefault(run.created_at.date(), []).append(run)
    rows = []
    day = record.generated_at.date()
    while day >= record.since:
        runs = by_day.get(day, [])
        if not runs:
            rows.append(f"<tr><td>{_e(day)}</td><td></td><td></td><td></td><td>No run</td></tr>")
        for run in sorted(runs, key=lambda r: r.created_at, reverse=True):
            delay = run.delay
            number = f"run {run.number}"
            link = _link(run.url or None, number)
            rows.append(
                "<tr>"
                f"<td>{_e(day)}</td>"
                f"<td>{_e(run.created_at.strftime('%H:%M'))}</td>"
                f"<td>{_e(daily_runs.STARTED_BY_LABELS[run.started_by])}</td>"
                f"<td>{_e(daily_runs.duration(delay)) if delay is not None else ''}</td>"
                f"<td>{_e(daily_runs.OUTCOME_LABELS[run.outcome])} ({link})</td>"
                "</tr>"
            )
        day -= timedelta(days=1)
    return (
        f"{intro}<ul>{''.join(f'<li>{item}</li>' for item in items)}</ul>"
        '<details><summary>Run by run</summary><div class="table-wrap"><table>'
        f"<caption>Runs of the daily fetch since {_e(since)}</caption>"
        '<thead><tr><th scope="col">Date</th><th scope="col">Started (UTC)</th>'
        '<th scope="col">Started by</th><th scope="col">Delay after the time set</th>'
        '<th scope="col">Result</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table></div></details>"
    )


# Added to the shared style: the key, and the switched-off list in columns.
EXTRA_STYLE = """
.key, .off { list-style: none; padding-left: 0; }
.off { columns: 16rem; }
.off li { break-inside: avoid; }
"""


def render_html(
    data: StatusFile,
    private: list[PrivateRow] | None = None,
    switched_off: Sequence[str] = (),
    record: "daily_runs.Record | str | None" = None,
    copies: list[CopyRow] | None = None,
) -> str:
    """The page. switched_off is the display names of registry operators not switched on;
    record is the daily run record, or why it is missing (None leaves the section out);
    copies is from copy_rows, or None when the map files were not given."""
    links = "".join(f"<li>{_link(url, text)}</li>" for text, url in LINKS)
    trends = "".join(_trend(status, data.generated_at) for status in data.operators.values())
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Feed health: OEVM</title>
<style>{STYLE}{EXTRA_STYLE}</style>
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
<h2>At a glance</h2>
{_at_a_glance(data, switched_off)}
<h2>Latest runs</h2>
<div class="table-wrap">{_latest_table(data)}</div>
{_related_note(data)}
{_switched_off(switched_off)}
{"" if record is None else _daily_runs_section(record)}
<h2>The last {HISTORY_DAYS} days</h2>
{trends}
{_private_section(private)}
{_copies_section(copies)}
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


def outputs(
    runs_dir: Path,
    out_dir: Path,
    previous: Path | None,
    now: datetime,
    map_layer: Path | None = None,
    daily_runs_file: Path | None = None,
) -> dict[Path, str]:
    if out_dir.resolve() == (ROOT / "site").resolve():
        raise StatusError("write to a build folder, not the committed site/ folder")
    before = None
    if previous is not None and previous.exists():
        try:
            before = StatusFile.model_validate_json(previous.read_text(encoding="utf-8"))
        except ValidationError as exc:
            problem = exc.errors()[0]["msg"]
            raise StatusError(f"{previous} is not a valid status file: {problem}") from None
    operators = load_registry()
    data = build(operators, load_runs(runs_dir), before, now)
    private = copies = None
    if map_layer is not None:
        try:
            layer = MapLayer.model_validate_json(map_layer.read_bytes())
        except FileNotFoundError:
            raise StatusError(f"{map_layer} does not exist") from None
        except ValidationError as exc:
            problem = exc.errors()[0]["msg"]
            raise StatusError(f"{map_layer} is not a valid map file: {problem}") from None
        private = private_rows(layer, operators)
        manifest_path = map_layer.parent / "manifest.json"
        try:
            manifest = Manifest.model_validate_json(manifest_path.read_bytes())
        except FileNotFoundError:
            raise StatusError(f"{manifest_path} does not exist") from None
        except ValidationError as exc:
            problem = exc.errors()[0]["msg"]
            raise StatusError(f"{manifest_path} is not a valid manifest: {problem}") from None
        copies = copy_rows(manifest, operators)
    off = sorted((c.display_name for c in operators.values() if not c.enabled), key=str.casefold)
    record = None
    if daily_runs_file is not None:
        try:
            record = daily_runs.load_record(daily_runs_file)
        except daily_runs.DailyRunsError:
            # The fetch still publishes; the page says the record is missing today.
            record = "The record of runs could not be read from GitHub when this page was built."
    page, json_text = render_html(data, private, off, record, copies), render_json(data)
    StatusFile.model_validate_json(json_text)
    return {out_dir / "status" / "index.html": page, out_dir / "data" / "status.json": json_text}


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.status", description=__doc__)
    parser.add_argument("--runs", type=Path, required=True, help="run logs from --log-dir")
    parser.add_argument("--out", type=Path, required=True, help="build folder (not site/)")
    parser.add_argument("--previous", type=Path, help="the status.json last published")
    parser.add_argument(
        "--map", type=Path, help="the locations.geojson just published, to list private ones"
    )
    parser.add_argument(
        "--daily-runs", type=Path, help="the record from pipeline.daily_runs record"
    )
    parser.add_argument(
        "--now", type=datetime.fromisoformat, help="time to stamp the page (default: now)"
    )
    args = parser.parse_args(argv)
    now = args.now or datetime.now(UTC).replace(microsecond=0)
    if now.tzinfo is None:
        parser.error("--now needs a time zone, for example 2026-10-08T12:00:00+00:00")
    try:
        files = outputs(args.runs, args.out, args.previous, now, args.map, args.daily_runs)
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
