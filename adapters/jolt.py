"""Adapter for Jolt's open data API (registry: id jolt, adapter custom).

Jolt's API is close to OCPI 2.2.1 but not the same. The differences, recorded as findings
in operators/jolt.yaml on 2026-10-08, are:

- GET .../locations returns {"locations": [...]} in one response, with no OCPI response
  wrapper and no paging. GET .../tariffs/{tariffId} returns one bare tariff object.
- Locations have no id and no publish flag. EVSEs have no uid and no last_updated, and
  their statuses are lower case. Some ids are numbers rather than strings.
- Connectors use CCS2 for the connector OCPI calls IEC_62196_T2_COMBO.
- tariff_alt_text is a list of strings, and min_price and max_price are plain numbers.

Each record is reshaped into an OCPI 2.2.1 object, then converted by
adapters.ocpi_221.convert_records, so the publish rule and every model rule apply. Only
differences with one clear meaning are reshaped. Anything else is left for the converter
to record as unknown.
"""

import re
from datetime import UTC, datetime

from adapters.http import FeedError, PoliteClient, redact_url
from adapters.ocpi_221 import AdapterResult, convert_records
from adapters.ocpi_221.client import KEPT_HEADERS, ModuleFetch, Page, _int_header
from adapters.ocpi_221.normalise import EVSE_STATUSES, IssueLog
from adapters.progress import NO_PROGRESS, PageProgress
from schema.operator import OperatorConfig

STANDARDS = {"CCS2": "IEC_62196_T2_COMBO"}
TARIFF_ID = re.compile(r"[A-Za-z0-9_-]{1,36}")  # OCPI ids are at most 36 characters
MAX_TARIFFS = 100
EMI3_EVSE_ID = re.compile(r"[A-Z]{2}\*?[A-Z0-9]{3}\*?E[A-Z0-9*]{1,30}")


def _text_id(value: object) -> str | None:
    """An id as text: a non-empty string, or a whole number written as text."""
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return None


def _get(client: PoliteClient, url: str) -> tuple[int, object, Page | None, int | None]:
    """GET url and parse JSON with the key removed: status, body, page and X-Total-Count.

    Body and page are None unless the reply is HTTP 200.
    """
    response = client.get(url)
    if response.status_code != 200:
        return response.status_code, None, None, None
    if "next" in response.links:
        raise FeedError(f"{redact_url(url)} has a next page link; this adapter reads one page")
    try:
        body = client.redact(response.json())
    except ValueError as exc:
        raise FeedError(f"{redact_url(url)} did not return JSON") from exc
    headers = {k: response.headers[k] for k in KEPT_HEADERS if k in response.headers}
    page = Page(redact_url(url), 200, client.redact(headers), body)
    return 200, body, page, _int_header(response, "X-Total-Count")


def _fetch_locations(client: PoliteClient, url: str, progress: PageProgress) -> ModuleFetch:
    status, body, page, total = _get(client, url)
    if status != 200:
        raise FeedError(f"{redact_url(url)} returned HTTP {status}")
    if not isinstance(body, dict) or not isinstance(body.get("locations"), list):
        raise FeedError(f"{redact_url(url)} returned no list of locations")
    records = body["locations"]
    if total is not None and total > len(records):
        raise FeedError(
            f"{redact_url(url)} reports {total} locations but sent {len(records)}; "
            "this adapter reads one page"
        )
    progress.page("locations", pages=1, records=len(records), total_records=total)
    progress.module_done("locations", pages=1, records=len(records), complete=True)
    return ModuleFetch("locations", url, records, [page], total_reported=total, complete=True)


def _fetch_tariffs(
    client: PoliteClient,
    template: str,
    ids: list[str],
    max_pages: int | None,
    issues: IssueLog,
    progress: PageProgress,
) -> ModuleFetch:
    module = ModuleFetch("tariffs", template)
    if len(ids) > MAX_TARIFFS:
        issues.add(f"{len(ids) - MAX_TARIFFS} tariff ids not fetched: more than {MAX_TARIFFS}")
    missed = len(ids) > MAX_TARIFFS
    limit = MAX_TARIFFS if max_pages is None else max(0, min(MAX_TARIFFS, max_pages))
    wanted = ids[:limit]
    for number, tariff_id in enumerate(wanted, start=1):
        try:
            status, body, page, _ = _get(client, template.replace("{tariffId}", tariff_id))
        except FeedError as exc:
            missed = True
            issues.add(f"tariff {tariff_id!r} not used: {exc}")
        else:
            if isinstance(body, dict):
                module.records.append(body)
                module.pages.append(page)
            else:
                missed = True
                problem = f"HTTP {status}" if status != 200 else "not a tariff object"
                issues.add(f"tariff {tariff_id!r} not used: {problem}")
        progress.page("tariffs", pages=number, records=len(module.records), total_pages=len(wanted))
    stopped = len(wanted) < len(ids[:MAX_TARIFFS])
    module.complete = not missed and not stopped
    progress.module_done(
        "tariffs", pages=len(module.pages), records=len(module.records), complete=module.complete
    )
    return module


def _connector(raw: dict, issues: IssueLog) -> dict:
    standard = raw.get("standard")
    connector = {
        **raw,
        "id": _text_id(raw.get("id")),
        "standard": STANDARDS.get(standard, standard) if isinstance(standard, str) else standard,
    }
    if isinstance(raw.get("tariff_ids"), list):
        connector["tariff_ids"] = [_text_id(t) for t in raw["tariff_ids"] if _text_id(t)]
        for bad in [t for t in raw["tariff_ids"] if not _text_id(t)]:
            issues.add(f"tariff id {bad!r} not used: not an id")
    return connector


def _evse(raw: dict, fetched_at: datetime, issues: IssueLog) -> dict:
    evse = dict(raw)
    status = raw.get("status")
    if isinstance(status, str) and status.upper() in EVSE_STATUSES:
        evse["status"] = status.upper()
    uid, number = raw.get("uid"), raw.get("evse_id")
    evse["uid"] = _text_id(uid) or _text_id(number)
    # Jolt's evse_id is a number such as 143, not an eMI3 EVSE ID, so it is kept only as the
    # uid. A value shaped like an eMI3 EVSE ID (for example GB*JLT*E143) would be kept.
    is_emi3 = isinstance(number, str) and EMI3_EVSE_ID.fullmatch(number)
    evse["evse_id"] = number if is_emi3 else None
    if not raw.get("last_updated"):
        # The status is as Jolt reported it when fetched; Jolt gives no time of its own.
        evse["last_updated"] = fetched_at.isoformat()
    evse["connectors"] = [_connector(c, issues) for c in raw.get("connectors") or []]
    return evse


def ocpi_location(raw: dict, fetched_at: datetime, issues: IssueLog) -> dict:
    """Reshape one Jolt location into an OCPI 2.2.1 Location. Raises ValueError if unusable."""
    location = dict(raw)
    # Jolt's names, such as BAR004, were unique on 2026-10-08 and stand in for the missing id.
    location["id"] = _text_id(raw.get("id")) or _text_id(raw.get("name"))
    if location["id"] is None:
        raise ValueError(
            f"location has no usable id or name (id {raw.get('id')!r}, name {raw.get('name')!r})"
        )
    location["evses"] = [_evse(evse, fetched_at, issues) for evse in raw.get("evses") or []]
    return location


def ocpi_tariff(raw: dict) -> dict:
    """Reshape one Jolt tariff into an OCPI 2.2.1 Tariff. Raises ValueError if unusable."""
    tariff = dict(raw)
    alt_text = raw.get("tariff_alt_text")
    if isinstance(alt_text, str):
        alt_text = [alt_text]
    if isinstance(alt_text, list):
        tariff["tariff_alt_text"] = [t if isinstance(t, dict) else {"text": t} for t in alt_text]
    for name in ("min_price", "max_price"):
        value = raw.get(name)
        if value is None or isinstance(value, dict):
            continue
        if value == 0 and not isinstance(value, bool):
            # No minimum charge; for max_price, no maximum, rather than a maximum of 0.
            tariff[name] = {"excl_vat": 0} if name == "min_price" else None
        else:
            raise ValueError(f"{name} {value!r} does not say whether it includes VAT")
    return tariff


def fetch(
    config: OperatorConfig,
    client: PoliteClient,
    *,
    date_from: datetime | None = None,
    page_size: int | None = None,
    max_pages: int | None = None,
    now: datetime | None = None,
    progress: PageProgress = NO_PROGRESS,
) -> AdapterResult:
    """Fetch every Jolt location, then each tariff they refer to (one request each)."""
    if date_from is not None or page_size is not None:
        raise FeedError(f"{config.id}: Jolt's API has no date_from or page size")
    fetched_at = now or datetime.now(UTC).replace(microsecond=0)
    issues = IssueLog()
    locations = _fetch_locations(client, config.endpoints["locations"].url, progress)
    raw_locations = []
    for raw in locations.records:
        try:
            raw_locations.append(ocpi_location(raw, fetched_at, issues))
        except (AttributeError, TypeError, ValueError) as exc:
            issues.add(f"location skipped: {exc}")
    ids = sorted(
        {
            tariff_id
            for location in raw_locations
            for evse in location["evses"]
            for connector in evse["connectors"]
            if isinstance(connector.get("tariff_ids"), list)
            for tariff_id in connector["tariff_ids"]
        }
    )
    for bad in [tariff_id for tariff_id in ids if not TARIFF_ID.fullmatch(tariff_id)]:
        issues.add(f"tariff id {bad!r} not fetched: unexpected characters")
    ids = [tariff_id for tariff_id in ids if TARIFF_ID.fullmatch(tariff_id)]
    tariffs = _fetch_tariffs(
        client, config.endpoints["tariffs"].url, ids, max_pages, issues, progress
    )

    result = AdapterResult(config.id, fetched_at, {"locations": locations, "tariffs": tariffs})
    raw_tariffs, sources = [], {}
    for raw, page in zip(tariffs.records, tariffs.pages, strict=True):
        try:
            raw_tariffs.append(ocpi_tariff(raw))
        except ValueError as exc:
            issues.add(f"tariff {raw.get('id')!r} skipped: {exc}")
        sources[str(raw.get("id"))] = page.url
    convert_records(
        config,
        result,
        locations=raw_locations,
        tariffs=raw_tariffs,
        issues=issues,
        tariff_sources=sources,
    )
    result.issues = [client.redact(line) for line in issues.lines()]
    return result
