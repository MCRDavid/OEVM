"""One-off recording of Eco-Movement's PCPR API (temporary; removed before the PR is ready).

For each of the nine networks whose token is in the environment (the eight in
Eco-Movement's emails of 27 October 2026, and Shell Recharge): one page of up to 1000
locations and one page of up to 1000 tariffs, through the project's polite client, so
requests with the same token are at least 125 seconds apart and requests to
open-chargepoints.com are sent one at a time (limits_per_key, the owner's decision of
29 October 2026). 18 requests at most, fewer than the 30 an hour published even if the
limit counted per address. Each response is saved under raw/<id>/ with the token
removed, and a summary is printed and saved to raw/summary.json. Never prints a token.
"""

import json
import os
import time
from collections import Counter
from pathlib import Path

from adapters.http import FeedError
from pipeline import run
from pipeline.registry import load_registry

IDS = [
    "drax_group",
    "gfx_gb_drax",
    "drax_ista",
    "aldi",
    "travis_perkins",
    "volvo",
    "wccc_edgbaston",
    "southampton_apartment_hotels",
    "shell_recharge",
]
OUT = Path("raw")


def counts(values) -> dict:
    return {str(k): n for k, n in Counter(values).most_common(25)}


def describe_locations(records: list[dict]) -> dict:
    evses = [e for r in records for e in (r.get("evses") or [])]
    connectors = [c for e in evses for c in (e.get("connectors") or [])]
    return {
        "records": len(records),
        "distinct_ids": len(
            {(r.get("country_code"), r.get("party_id"), r.get("id")) for r in records}
        ),
        "country_party": counts((r.get("country_code"), r.get("party_id")) for r in records),
        "publish": counts(r.get("publish") for r in records),
        "country": counts(r.get("country") for r in records),
        "operator_name": counts((r.get("operator") or {}).get("name") for r in records),
        "suboperator_name": counts((r.get("suboperator") or {}).get("name") for r in records),
        "owner_present": counts(bool((r.get("owner") or {}).get("name")) for r in records),
        "time_zone": counts(r.get("time_zone") for r in records),
        "coordinate_types": counts(
            type((r.get("coordinates") or {}).get("latitude")).__name__ for r in records
        ),
        "energy_mix_types": counts(type(r.get("energy_mix")).__name__ for r in records),
        "parking_type": counts(r.get("parking_type") for r in records),
        "facilities": counts(f for r in records for f in (r.get("facilities") or [])),
        "evses": len(evses),
        "evse_status": counts(e.get("status") for e in evses),
        "evse_parking_restrictions": counts(
            p for e in evses for p in (e.get("parking_restrictions") or [])
        ),
        "connectors": len(connectors),
        "standard": counts(c.get("standard") for c in connectors),
        "power_type": counts(c.get("power_type") for c in connectors),
        "max_electric_power_zero": sum(1 for c in connectors if c.get("max_electric_power") == 0),
        "connectors_without_tariff_ids": sum(1 for c in connectors if not c.get("tariff_ids")),
        "fields": counts(k for r in records for k in r),
    }


def describe_tariffs(records: list[dict]) -> dict:
    elements = [el for t in records for el in (t.get("elements") or [])]
    components = [p for el in elements for p in (el.get("price_components") or [])]
    return {
        "records": len(records),
        "country_party": counts((t.get("country_code"), t.get("party_id")) for t in records),
        "currency": counts(t.get("currency") for t in records),
        "type": counts(t.get("type") for t in records),
        "component_types": counts(p.get("type") for p in components),
        "vat_stated": counts(p.get("vat") is not None for p in components),
        "zero_price_components": sum(1 for p in components if p.get("price") in (0, 0.0)),
        "fields": counts(k for t in records for k in t),
    }


def describe_pages(modules: dict) -> dict:
    return {
        name: [{"url": p.url, "status": p.status_code, "headers": p.headers} for p in m.pages]
        for name, m in modules.items()
    }


def save_pages(modules: dict, directory: Path) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    for module in modules.values():
        for number, page in enumerate(module.pages, start=1):
            path = directory / f"{module.module}_page{number}.json"
            path.write_text(json.dumps(page.to_exchange(), indent=2) + "\n", encoding="utf-8")


operators = load_registry()
OUT.mkdir(exist_ok=True)
summary: dict = {"started": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
# A previous run of this check may have ended moments ago: keep the gap across runs too.
time.sleep(125)
for op_id in IDS:
    config = operators[op_id]
    secret = config.auth.secret_name
    if not os.environ.get(secret):
        print(f"{op_id}: {secret} is not set; skipped with no request", flush=True)
        summary[op_id] = {"skipped": f"{secret} not set"}
        continue
    print(f"{op_id}: fetching at {time.strftime('%H:%M:%S', time.gmtime())} UTC", flush=True)
    try:
        result = run.run_operator(
            config,
            page_size=1000,
            max_pages=1,
            notice=lambda text, i=op_id: print(f"{i}: {text}", flush=True),
        )
    except FeedError as exc:
        modules = exc.modules or {}
        save_pages(modules, OUT / op_id)
        summary[op_id] = {
            "failed": str(exc),
            "requests": getattr(exc, "requests", None),
            "pages": describe_pages(modules),
        }
        print(f"{op_id}: failed: {exc}", flush=True)
        continue
    run.save_raw(result, OUT / op_id)
    print(run.report(result), flush=True)
    summary[op_id] = {
        "requests": result.requests,
        "pages": describe_pages(result.modules),
        "total_reported": {n: m.total_reported for n, m in result.modules.items()},
        "complete": {n: m.complete for n, m in result.modules.items()},
        "kept": {"locations": len(result.locations), "tariffs": len(result.tariffs)},
        "locations": describe_locations(result.modules["locations"].records),
        "tariffs": describe_tariffs(result.modules["tariffs"].records),
        "issues": result.issues,
    }
summary["finished"] = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
(OUT / "summary.json").write_text(json.dumps(summary, indent=1) + "\n", encoding="utf-8")
print(json.dumps(summary, indent=1))
