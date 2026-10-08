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
from adapters.ocpi_221.client import KEPT_HEADERS, ModuleFetch, Page
from adapters.ocpi_221.normalise import EVSE_STATUSES, IssueLog
from schema.operator import OperatorConfig

STANDARDS = {"CCS2": "IEC_62196_T2_COMBO"}
TARIFF_ID = re.compile(r"[A-Za-z0-9_-]{1,36}")  # OCPI ids are at most 36 characters
MAX_TARIFFS = 100


def _get(client: PoliteClient, url: str) -> tuple[int, object, Page | None]:
    """GET url and parse JSON with the key removed. Body and page are None unless HTTP 200."""
    response = client.get(url)
    if response.status_code != 200:
        return response.status_code, None, None
    if "next" in response.links:
        raise FeedError(f"{redact_url(url)} has a next page link; this adapter reads one page")
    try:
        body = client.redact(response.json())
    except ValueError as exc:
        raise FeedError(f"{redact_url(url)} did not return JSON") from exc
    headers = {k: response.headers[k] for k in KEPT_HEADERS if k in response.headers}
    return 200, body, Page(redact_url(url), 200, client.redact(headers), body)


def _fetch_locations(client: PoliteClient, url: str) -> ModuleFetch:
    status, body, page = _get(client, url)
    if status != 200:
        raise FeedError(f"{redact_url(url)} returned HTTP {status}")
    if not isinstance(body, dict) or not isinstance(body.get("locations"), list):
        raise FeedError(f"{redact_url(url)} returned no list of locations")
    return ModuleFetch("locations", url, body["locations"], [page], complete=True)


def _fetch_tariffs(
    client: PoliteClient, template: str, ids: list[str], max_pages: int | None, issues: IssueLog
) -> ModuleFetch:
    module = ModuleFetch("tariffs", template)
    if len(ids) > MAX_TARIFFS:
        issues.add(f"{len(ids) - MAX_TARIFFS} tariff ids not fetched: more than {MAX_TARIFFS}")
    missed = len(ids) > MAX_TARIFFS
    for number, tariff_id in enumerate(ids[:MAX_TARIFFS]):
        if max_pages is not None and number >= max_pages:
            return module
        status, body, page = _get(client, template.replace("{tariffId}", tariff_id))
        if isinstance(body, dict):
            module.records.append(body)
            module.pages.append(page)
        else:
            missed = True
            problem = f"HTTP {status}" if status != 200 else "not a tariff object"
            issues.add(f"tariff {tariff_id!r} not used: {problem}")
    module.complete = not missed
    return module


def _connector(raw: dict) -> dict:
    standard = raw.get("standard")
    return {
        **raw,
        "id": None if raw.get("id") is None else str(raw["id"]),
        "standard": STANDARDS.get(standard, standard) if isinstance(standard, str) else standard,
    }


def _evse(raw: dict, fetched_at: datetime) -> dict:
    evse = dict(raw)
    status = raw.get("status")
    if isinstance(status, str) and status.upper() in EVSE_STATUSES:
        evse["status"] = status.upper()
    uid, number = raw.get("uid"), raw.get("evse_id")
    evse["uid"] = str(uid) if uid is not None else (None if number is None else str(number))
    # Jolt's evse_id is a number such as 143, not an eMI3 EVSE ID, so it is not kept as one.
    evse["evse_id"] = number if isinstance(number, str) else None
    if not raw.get("last_updated"):
        # The status is as Jolt reported it when fetched; Jolt gives no time of its own.
        evse["last_updated"] = fetched_at.isoformat()
    evse["connectors"] = [_connector(c) for c in raw.get("connectors") or []]
    return evse


def ocpi_location(raw: dict, fetched_at: datetime) -> dict:
    """Reshape one Jolt location into an OCPI 2.2.1 Location. Raises ValueError if unusable."""
    location = dict(raw)
    # Jolt's names, such as BAR004, were unique on 2026-10-08 and stand in for the missing id.
    location["id"] = raw.get("id") or raw.get("name")
    if not isinstance(location["id"], str) or not location["id"].strip():
        raise ValueError("location has no id or name")
    location["evses"] = [_evse(evse, fetched_at) for evse in raw.get("evses") or []]
    return location


def ocpi_tariff(raw: dict) -> dict:
    """Reshape one Jolt tariff into an OCPI 2.2.1 Tariff. Raises ValueError if unusable."""
    tariff = dict(raw)
    alt_text = raw.get("tariff_alt_text")
    if isinstance(alt_text, list):
        tariff["tariff_alt_text"] = [t if isinstance(t, dict) else {"text": t} for t in alt_text]
    for name in ("min_price", "max_price"):
        value = raw.get(name)
        if value is None or isinstance(value, dict):
            continue
        if value == 0 and not isinstance(value, bool):
            tariff[name] = {"excl_vat": 0}
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
) -> AdapterResult:
    """Fetch every Jolt location, then each tariff they refer to (one request each)."""
    if date_from is not None or page_size is not None:
        raise FeedError(f"{config.id}: Jolt's API has no date_from or page size")
    fetched_at = now or datetime.now(UTC).replace(microsecond=0)
    issues = IssueLog()
    locations = _fetch_locations(client, config.endpoints["locations"].url)
    raw_locations = []
    for raw in locations.records:
        try:
            raw_locations.append(ocpi_location(raw, fetched_at))
        except (AttributeError, TypeError, ValueError) as exc:
            issues.add(f"location skipped: {exc}")
    ids = sorted(
        {
            str(tariff_id)
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
    tariffs = _fetch_tariffs(client, config.endpoints["tariffs"].url, ids, max_pages, issues)

    result = AdapterResult(config.id, fetched_at, {"locations": locations, "tariffs": tariffs})
    raw_tariffs = []
    for raw in tariffs.records:
        try:
            raw_tariffs.append(ocpi_tariff(raw))
        except ValueError as exc:
            issues.add(f"tariff {raw.get('id')!r} skipped: {exc}")
    convert_records(config, result, locations=raw_locations, tariffs=raw_tariffs, issues=issues)
    result.issues = [client.redact(line) for line in issues.lines()]
    return result
