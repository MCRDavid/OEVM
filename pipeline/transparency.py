"""Build the transparency page: where the data comes from, how it is fetched, what limits
apply, and what has been found.

    uv run python -m pipeline.transparency            # write the page and its JSON
    uv run python -m pipeline.transparency --check    # fail if the committed files are stale

The page is built only from the operator registry (operators/*.yaml), so it is the same
on every build. It has no scripts, no cookies and no third-party files. Wording comes from
the registry, where it is checked for neutral language, or from this module. The results
of each run are on the feed health page (pipeline/status.py).
"""

import argparse
import html
import json
import math
import sys
from datetime import date
from pathlib import Path

from pipeline.project import REPOSITORY_URL
from pipeline.registry import ROOT, RegistryError, load_registry
from schema.operator import ENGAGEMENT_LABELS, DocumentedLimit, OperatorConfig

PAGE_PATH = ROOT / "site" / "transparency" / "index.html"
JSON_PATH = ROOT / "site" / "data" / "transparency.json"
DISCLAIMER_PATH = ROOT / "DISCLAIMER.md"

REGULATION = {
    "summary": (
        "The Public Charge Point Regulations 2023 set no limit on how often data users may "
        "request the data. Regulation 10(5) requires the data to be available free of charge "
        "without terms on its use. DfT's guidance allows terms covering the means of access, "
        "which is where operators' rate limits come from."
    ),
    "quotes": [
        {
            "text": (
                "terms and conditions covering the means of access to the data and API(s) "
                "are permissible"
            ),
            "source": "DfT, Public Charge Point Regulations 2023 guidance",
            "url": (
                "https://www.gov.uk/government/publications/the-public-charge-point-"
                "regulations-2023-guidance/public-charge-point-regulations-2023-guidance"
            ),
        },
    ],
}

FINDING_KINDS = {
    "spec_conformance": "Differs from OCPI 2.2.1",
    "data_quality": "Data quirk",
    "access": "Access",
    "documentation": "Documentation",
}
LINKS = (
    ("Disclaimer", f"{REPOSITORY_URL}/blob/main/DISCLAIMER.md"),
    ("Data sources and licences", f"{REPOSITORY_URL}/blob/main/DATA_LICENCES.md"),
    ("Privacy and cookies", "../privacy/"),
    ("Security policy", f"{REPOSITORY_URL}/blob/main/SECURITY.md"),
    ("Report a mistake", f"{REPOSITORY_URL}/issues/new/choose"),
    ("Source code", REPOSITORY_URL),
)


def short_disclaimer(path: Path = DISCLAIMER_PATH) -> str:
    """The quoted short version under "## Short version" in DISCLAIMER.md."""
    lines, inside = [], False
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("## "):
            inside = line.strip() == "## Short version"
        elif inside and line.startswith(">"):
            lines.append(line.lstrip("> ").strip())
    if not lines:
        raise ValueError(f"no short version found in {path}")
    return " ".join(lines)


def human_seconds(seconds: float) -> str:
    for size, unit in ((86400, "day"), (3600, "hour"), (60, "minute"), (1, "second")):
        if seconds >= size and seconds % size == 0:
            count = int(seconds // size)
            return f"{count} {unit}" if count == 1 else f"{count} {unit}s"
    return f"{seconds:g} seconds"


def describe_limit(limit: DocumentedLimit) -> str:
    where = "all requests" if limit.endpoint == "all" else f"the {limit.endpoint} endpoint"
    if limit.scope:
        where += f" ({limit.scope})"
    return f"{limit.requests} per {human_seconds(limit.per_seconds)} for {where}"


def max_per_hour(gap: float) -> int:
    """Most requests that can start within any one hour when each is gap seconds apart."""
    return math.ceil(3600 / gap - 1e-9)


def rate_limit_view(config: OperatorConfig) -> dict:
    """Our setting next to the operator's published limits, and how they compare."""
    rate = config.rate_limit
    gap = rate.min_seconds_between_requests
    per_hour = max_per_hour(gap)
    ours = (
        f"At least {gap:g} s between requests to the operator's host, measured from the end "
        f"of the previous request (at most {per_hour} in any hour), retries included."
    )
    if rate.limits:
        needed = max(limit.min_interval for limit in rate.limits)
        comparison = (
            f"Within every published limit. The strictest needs {needed:g} s between "
            f"requests; this project waits {gap:g} s, which includes a safety margin."
        )
        difference = (
            "The operator sets a limit; the regulations set none. DfT guidance allows such "
            "terms on access."
        )
    elif rate.limits_checked != "unknown":
        comparison = (
            f"No limit published (checked {rate.limits_checked}). The gap is our own choice."
        )
        difference = "Neither the operator nor the regulations set a limit."
    else:
        comparison = "The operator's pages have not been checked for limits yet."
        difference = "Not known yet."
    return {
        "our_gap_seconds": gap,
        "our_max_per_hour": per_hour,
        "ours": ours,
        "published": [
            {
                "text": describe_limit(limit),
                "publisher": limit.publisher,
                "quote": limit.quote,
                "source_url": limit.source_url,
                "checked": str(limit.checked),
            }
            for limit in rate.limits
        ],
        "limits_checked": str(rate.limits_checked),
        "comparison": comparison,
        "difference_from_regulations": difference,
        "notes": rate.notes,
    }


def operator_view(config: OperatorConfig) -> dict:
    feeds = [
        {"kind": kind, "url": endpoint.url, "status": endpoint.status}
        for kind, endpoint in config.endpoints.items()
    ]
    if not feeds and config.base_url != "unknown":
        feeds = [{"kind": "base", "url": config.base_url, "status": "documented"}]
    return {
        "id": config.id,
        "name": config.display_name,
        "enabled": config.enabled,
        "adapter": config.adapter,
        "engagement": {
            "status": config.engagement.status,
            "label": ENGAGEMENT_LABELS[config.engagement.status],
            "evidence": [
                {"date": str(e.date), "url": e.url, "file": e.file, "note": e.note}
                for e in config.engagement.evidence
            ],
        },
        "feeds": feeds,
        "licence": (
            {
                "name": config.licence.name,
                "url": config.licence.url,
                "checked": str(config.licence.checked),
            }
            if config.licence
            else None
        ),
        "attribution": config.attribution,
        "missing_publish_flag": (
            {
                "decided": str(config.missing_publish_flag.decided),
                "basis": config.missing_publish_flag.basis,
                "evidence_url": config.missing_publish_flag.evidence_url,
            }
            if config.missing_publish_flag
            else None
        ),
        "relay": (
            {
                "decided": str(config.relay.decided),
                "reason": config.relay.reason,
                "evidence_url": config.relay.evidence_url,
            }
            if config.relay
            else None
        ),
        "rate_limit": rate_limit_view(config),
        "findings": [
            {
                "date": str(f.date),
                "kind": f.kind,
                "kind_label": FINDING_KINDS[f.kind],
                "summary": f.summary,
                "handling": f.handling,
                "evidence_url": f.evidence_url,
                "status": f.status,
                "resolved_date": str(f.resolved_date) if f.resolved_date else None,
            }
            for f in config.findings
        ],
    }


def last_reviewed(operators: dict[str, OperatorConfig]) -> str:
    """The latest date recorded anywhere in the registry, so the page is reproducible."""
    dates: list[date] = []
    for config in operators.values():
        candidates = [
            config.rate_limit.limits_checked,
            config.licence.checked if config.licence else "unknown",
            *(e.date for e in config.engagement.evidence),
            *(f.date for f in config.findings),
            *(f.resolved_date for f in config.findings),
            *(limit.checked for limit in config.rate_limit.limits),
            config.access_requested,
            config.access_granted,
            config.missing_publish_flag.decided if config.missing_publish_flag else None,
        ]
        dates += [d for d in candidates if isinstance(d, date)]
    return max(dates).isoformat() if dates else "unknown"


def build(operators: dict[str, OperatorConfig]) -> dict:
    ordered = sorted(operators.values(), key=lambda c: (not c.enabled, c.display_name.lower()))
    return {
        "last_reviewed": last_reviewed(operators),
        "disclaimer": short_disclaimer(),
        "regulation": REGULATION,
        "operators": [operator_view(c) for c in ordered],
    }


# HTML


def _e(value: object) -> str:
    return html.escape(str(value), quote=True)


def _link(url: str | None, text: str) -> str:
    return f'<a href="{_e(url)}">{_e(text)}</a>' if url else _e(text)


def _feed_url(url: str) -> str:
    """A link, unless the URL is a template such as .../tariffs/{tariffId}."""
    return f"<code>{_e(url)}</code>" if "{" in url else _link(url, url)


def _sources_table(data: dict) -> str:
    rows = []
    for op in data["operators"]:
        feeds = (
            "<br>".join(
                f"{_e(f['kind'])}: {_feed_url(f['url'])}"
                + ("" if f["status"] == "documented" else " (needs testing)")
                for f in op["feeds"]
            )
            or "None known"
        )
        licence = op["licence"]
        licence_text = (
            f"{_link(licence['url'], licence['name'])}, terms checked {_e(licence['checked'])}"
            if licence
            else "Not checked yet"
        )
        decision = op["missing_publish_flag"]
        no_flag = (
            f"Shown: {_e(decision['basis'])} (decided {_e(decision['decided'])}, "
            f"{_link(decision['evidence_url'], 'evidence')})"
            if decision
            else "Not shown"
        )
        evidence = (
            "<br>".join(
                _link(e["url"], "date not recorded" if e["date"] == "unknown" else e["date"])
                + (f": {_e(e['note'])}" if e["note"] else "")
                for e in op["engagement"]["evidence"]
            )
            or "None yet"
        )
        relay = op["relay"]
        fetched = "Yes" if op["enabled"] else "No"
        if op["enabled"] and relay:
            fetched += (
                f", through the project's relay since {_e(relay['decided'])}: "
                f"{_e(relay['reason'])} ({_link(relay['evidence_url'], 'evidence')})"
            )
        rows.append(
            "<tr>"
            f'<th scope="row">{_e(op["name"])}</th>'
            f"<td>{_e(op['engagement']['label'])}</td>"
            f"<td>{fetched}</td>"
            f"<td>{feeds}</td>"
            f"<td>{licence_text}</td>"
            f"<td>{no_flag}</td>"
            f"<td>{evidence}</td>"
            "</tr>"
        )
    return (
        "<table><caption>Sources and how each one publishes its data</caption>"
        '<thead><tr><th scope="col">Operator</th><th scope="col">How data is published</th>'
        '<th scope="col">Fetched by this project</th><th scope="col">Feeds</th>'
        '<th scope="col">Licence</th><th scope="col">Locations with no publish flag</th>'
        '<th scope="col">Evidence</th></tr></thead>'
        f"<tbody>{''.join(rows)}</tbody></table>"
    )


def _rate_table(data: dict) -> str:
    rows = []
    for op in data["operators"]:
        rate = op["rate_limit"]
        published = "<br>".join(
            f"{_e(p['text'])}, published by {_e(p['publisher'])}: "
            f"&ldquo;{_e(p['quote'])}&rdquo; "
            f"({_link(p['source_url'], 'source')}, checked {_e(p['checked'])})"
            for p in rate["published"]
        ) or (
            f"None published (checked {_e(rate['limits_checked'])})"
            if rate["limits_checked"] != "unknown"
            else "Not checked yet"
        )
        notes = f"<br>{_e(rate['notes'])}" if rate["notes"] else ""
        rows.append(
            "<tr>"
            f'<th scope="row">{_e(op["name"])}</th>'
            f"<td>{published}</td>"
            f"<td>{_e(rate['ours'])}</td>"
            f"<td>{_e(rate['comparison'])}{notes}</td>"
            f"<td>{_e(rate['difference_from_regulations'])}</td>"
            "</tr>"
        )
    return (
        "<table><caption>Rate limits: what each operator publishes and what this project "
        "does</caption>"
        '<thead><tr><th scope="col">Operator</th><th scope="col">Published limit (operator '
        'or its data host)</th><th scope="col">This project&rsquo;s setting</th>'
        '<th scope="col">Comparison</th><th scope="col">Compared with the regulations</th>'
        f"</tr></thead><tbody>{''.join(rows)}</tbody></table>"
    )


def _findings_section(data: dict) -> str:
    parts = []
    for op in data["operators"]:
        if not op["findings"]:
            continue
        rows = "".join(
            "<tr>"
            f"<td>{_e(f['date'])}</td>"
            f"<td>{_e(f['kind_label'])}</td>"
            f"<td>{_e(f['summary'])}</td>"
            f"<td>{_e(f['handling'] or '')}</td>"
            f"<td>{_e('Resolved ' + f['resolved_date'] if f['resolved_date'] else 'Open')}</td>"
            f"<td>{_link(f['evidence_url'], 'evidence') if f['evidence_url'] else ''}</td>"
            "</tr>"
            for f in op["findings"]
        )
        parts.append(
            f"<table><caption>{_e(op['name'])}</caption>"
            '<thead><tr><th scope="col">Date</th><th scope="col">Type</th>'
            '<th scope="col">What was found</th><th scope="col">How this project handles it'
            '</th><th scope="col">Status</th><th scope="col">Evidence</th></tr></thead>'
            f"<tbody>{rows}</tbody></table>"
        )
    return "".join(parts) or "<p>Nothing recorded yet.</p>"


STYLE = """
:root { color-scheme: light dark; --fg: #1a1a1a; --bg: #ffffff; --muted: #555555;
  --line: #d0d0d0; --link: #0b57a4; --note: #f3f3f3; }
@media (prefers-color-scheme: dark) { :root { --fg: #ececec; --bg: #121212;
  --muted: #b0b0b0; --line: #3a3a3a; --link: #8ab4f8; --note: #1f1f1f; } }
body { margin: 0 auto; max-width: 72rem; padding: 1rem; font: 1rem/1.5 system-ui, sans-serif;
  color: var(--fg); background: var(--bg); }
a { color: var(--link); }
.note { background: var(--note); border-left: 4px solid var(--line); padding: 0.75rem 1rem; }
.table-wrap { overflow-x: auto; }
table { border-collapse: collapse; width: 100%; margin: 1rem 0 2rem; font-size: 0.95rem; }
caption { text-align: left; font-weight: 600; padding-bottom: 0.5rem; }
th, td { border: 1px solid var(--line); padding: 0.5rem; text-align: left; vertical-align: top; }
footer { border-top: 1px solid var(--line); margin-top: 2rem; padding-top: 1rem;
  color: var(--muted); }
footer ul { padding-left: 1.2rem; }
"""


def render_html(data: dict) -> str:
    links = "".join(f"<li>{_link(url, text)}</li>" for text, url in LINKS)
    regulation_quotes = "".join(
        f"<li>&ldquo;{_e(q['text'])}&rdquo; ({_link(q['url'], q['source'])})</li>"
        for q in data["regulation"]["quotes"]
    )
    return f"""<!doctype html>
<html lang="en-GB">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Data sources and transparency: OEVM</title>
<style>{STYLE}</style>
</head>
<body>
<header>
<h1>Data sources and transparency</h1>
<p>Last reviewed: {_e(data["last_reviewed"])}. This page lists every operator source this
project uses or plans to use, how each one publishes its data, the rate limits that apply,
and what has been found while reading the data. It reports what was observed and when. It
does not say whether anyone has met their legal duties.</p>
</header>
<main>
<h2>Sources</h2>
<p>OCPI 2.2.1 says a location whose publish flag is false may not be shown on a website
or app, so those are never shown. Locations with no flag are not shown either, unless the
repository owner has recorded a decision for that operator, with the reason and date
below. A flag set to false is always respected.</p>
<div class="table-wrap">{_sources_table(data)}</div>
<h2>Rate limits</h2>
<p>{_e(data["regulation"]["summary"])}</p>
<ul>{regulation_quotes}</ul>
<p>This project never sends more than one request per second to any operator's host, keeps
within every limit an operator, or the company hosting its data, publishes with a safety
margin on top, and waits as long as
a server asks before contacting it again. Gaps are measured from the end of the previous
request and shared by every operator on the same host. Automated tests check these
rules.</p>
<div class="table-wrap">{_rate_table(data)}</div>
<h2>What has been found</h2>
<p>Differences from the OCPI 2.2.1 standard, quirks in the data and access issues, each
with the date it was seen and what this project does about it. Values that are not valid
are shown as unknown, never guessed. Only prices in pounds sterling are shown.</p>
<div class="table-wrap">{_findings_section(data)}</div>
<h2>Latest runs</h2>
<p>The results of each daily run, with counts, problems logged and a 30-day history, are
on the <a href="../status/">feed health page</a>.</p>
</main>
<footer>
<p class="note">{_e(data["disclaimer"])}</p>
<ul>{links}</ul>
<p>This page has no cookies, no tracking and no scripts.</p>
</footer>
</body>
</html>
"""


def render_json(data: dict) -> str:
    return json.dumps(data, indent=2, ensure_ascii=False) + "\n"


def outputs() -> dict[Path, str]:
    """The page and its JSON, keyed by where they are committed."""
    data = build(load_registry())
    return {PAGE_PATH: render_html(data), JSON_PATH: render_json(data)}


def _shown(path: Path) -> str:
    return str(path.relative_to(ROOT)) if path.is_relative_to(ROOT) else str(path)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.transparency", description=__doc__)
    parser.add_argument("--check", action="store_true", help="fail if committed files are stale")
    args = parser.parse_args(argv)

    try:
        files = outputs()
    except (RegistryError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1

    stale = []
    for path, text in files.items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current == text:
            continue
        if args.check:
            stale.append(_shown(path))
        else:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")
            print(f"Wrote {_shown(path)}")
    if stale:
        print(
            f"Out of date: {', '.join(stale)}. Run 'uv run python -m pipeline.transparency' "
            "and commit the result.",
            file=sys.stderr,
        )
        return 1
    if args.check:
        print("Transparency page is up to date.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
