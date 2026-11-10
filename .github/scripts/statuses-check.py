"""One-off recording of Eco-Movement's statuses endpoint (temporary; removed before the PR
is ready).

For three networks whose tokens Eco-Movement sent in October 2026: one request each to the
statuses endpoint recorded in their operator files, through the project's polite client,
so each token keeps its published limit ("1 request per 30 seconds") and the host gets at
most one request at a time here. If the server pages its answer, one more page is read to
see how, and no more. Each response is saved under raw/<id>/ with the token removed, and a
summary is printed and saved to raw/summary.json. Never prints a token.
"""

import json
import os
import time
from collections import Counter
from pathlib import Path

from adapters.http import FeedError, PoliteClient
from adapters.ocpi_221.client import fetch_module
from pipeline.registry import load_registry

# The smallest network, a middling one whose fixtures hold two of its sites, and the largest.
IDS = ["wccc_edgbaston", "aldi", "ubitricity"]
OUT = Path("raw")
MAX_PAGES = 2


def counts(values) -> dict:
    return {str(k): n for k, n in Counter(values).most_common(25)}


def describe(records: list) -> dict:
    entries = [r for r in records if isinstance(r, dict)]
    evses = [e for r in entries for e in (r.get("evses") or []) if isinstance(e, dict)]
    return {
        "records": len(records),
        "record_types": counts(type(r).__name__ for r in records),
        "distinct_ids": len({r.get("id") for r in entries}),
        "fields": counts(k for r in entries for k in r),
        "evses": len(evses),
        "evse_fields": counts(k for e in evses for k in e),
        "evse_status": counts(e.get("status") for e in evses),
        "evses_without_last_updated": sum(1 for e in evses if not e.get("last_updated")),
        "distinct_evse_uids": len({e.get("uid") for e in evses}),
        "sample_ids": [r.get("id") for r in entries[:5]],
    }


def save_pages(module, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for number, page in enumerate(module.pages, start=1):
        path = directory / f"statuses_page{number}.json"
        path.write_text(json.dumps(page.to_exchange(), indent=2) + "\n", encoding="utf-8")


def record(config, url: str) -> dict:
    with PoliteClient(
        config, notice=lambda text, i=config.id: print(f"{i}: {text}", flush=True)
    ) as client:
        try:
            module = fetch_module(client, "statuses", url, max_pages=MAX_PAGES, stop_at_total=True)
        except FeedError as exc:
            if exc.partial is not None:
                save_pages(exc.partial, OUT / config.id)
            return {"failed": str(exc), "url": url, "requests": client.requests_made}
        save_pages(module, OUT / config.id)
        body = module.pages[0].body if module.pages else None
        return {
            "url": url,
            "requests": client.requests_made,
            "complete": module.complete,
            "total_reported": module.total_reported,
            "pages": [
                {"url": p.url, "status": p.status_code, "headers": p.headers} for p in module.pages
            ],
            "body_fields": sorted(body) if isinstance(body, dict) else type(body).__name__,
            "timestamp": body.get("timestamp") if isinstance(body, dict) else None,
            "statuses": describe(module.records),
        }


operators = load_registry()
OUT.mkdir(exist_ok=True)
summary: dict = {"started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
# A previous run of this check may have ended moments ago: keep the limit across runs too.
time.sleep(35)
for op_id in IDS:
    config = operators[op_id]
    secret = config.auth.secret_name
    if not os.environ.get(secret):
        print(f"{op_id}: {secret} is not set; skipped with no request", flush=True)
        summary[op_id] = {"skipped": f"{secret} not set"}
        continue
    url = config.endpoints["statuses"].url
    print(f"{op_id}: asking at {time.strftime('%H:%M:%S', time.gmtime())} UTC", flush=True)
    outcome = record(config, url)
    if "HTTP 307" in outcome.get("failed", "") and not url.endswith("/"):
        # The locations endpoint answers 307 without its trailing slash; see whether this
        # one does too. The client keeps the token's limit before asking again.
        summary[f"{op_id}_without_slash"] = outcome
        outcome = record(config, url + "/")
    summary[op_id] = outcome
    print(f"{op_id}: {json.dumps({k: v for k, v in outcome.items() if k != 'statuses'})}", flush=True)
summary["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
(OUT / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=1))
