"""Adapter for Roam's open data feed (registry: id roam, adapter custom).

Roam, formerly EVC, serves its data from data.evc.ninja in OCPI response objects, one
page per module, but its records use OCPI 2.1.1 names rather than 2.2.1. The
differences, recorded as findings in operators/roam.yaml on 2026-10-26, are:

- Connectors name one tariff in tariff_id and give voltage and amperage, where OCPI 2.2.1
  has the list tariff_ids and max_voltage and max_amperage. The meanings are the same.
- Locations and tariffs have no country_code or party_id, so the operator file's GB and
  EVC are used. Locations have no publish flag.
- Locations give type (OCPI 2.1.1 LocationType) rather than parking_type. Its values
  ON_STREET, PARKING_GARAGE, UNDERGROUND_GARAGE and PARKING_LOT have the same names and
  meanings in OCPI 2.2.1, so type is read as parking_type; OTHER and UNKNOWN are not OCPI
  2.2.1 values and are recorded as unknown by the converter. Every location gave
  ON_STREET on 2026-10-26; the owner decided on 2026-10-30 to show it as published.
- Some EVSEs give two connectors the same id, which OCPI does not allow. By the repository
  owner's decision of 2026-10-29, each connector in such an EVSE takes Roam's own
  connector uuid, which is unique, as its id, so the site is still shown.

Each connector is given its OCPI 2.2.1 names, then every record is converted by
adapters.ocpi_221.convert_records, so the publish rule and every model rule apply.
Tariffs are already in a shape the converter reads. Anything that does not have the
expected shape is passed on unchanged, for the converter to skip or record as unknown.
"""

from datetime import UTC, datetime

from adapters.http import FeedError, PoliteClient
from adapters.ocpi_221 import MODULES, AdapterResult, convert_records
from adapters.ocpi_221.client import ModuleFetch, fetch_module
from adapters.ocpi_221.normalise import IssueLog
from adapters.progress import NO_PROGRESS, PageProgress
from schema.operator import OperatorConfig

RENAMED = (("voltage", "max_voltage"), ("amperage", "max_amperage"))


def _connector(raw: object, issues: IssueLog) -> object:
    """One OCPI 2.1.1 Connector with the OCPI 2.2.1 names for its power and tariff."""
    if not isinstance(raw, dict):
        return raw
    connector = dict(raw)
    for old, new in RENAMED:
        if new not in raw and old in raw:
            connector[new] = raw[old]
    if "tariff_ids" not in raw:
        tariff_id = raw.get("tariff_id")
        if isinstance(tariff_id, str) and tariff_id.strip():
            connector["tariff_ids"] = [tariff_id]
        else:
            if tariff_id is not None:
                issues.add(f"connector tariff_id {tariff_id!r} is not an id; not used")
            connector["tariff_ids"] = []
    return connector


def _text_id(value: object) -> str | None:
    """An id as text: a non-empty string, or a whole number written as text."""
    if isinstance(value, str) and value.strip():
        return value
    if isinstance(value, int) and not isinstance(value, bool):
        return str(value)
    return None


def _connectors(raw: list, issues: IssueLog) -> list:
    """An EVSE's connectors, each with its own Roam uuid as its id if their ids repeat."""
    connectors = [_connector(c, issues) for c in raw]
    ids = [c["id"] for c in connectors if isinstance(c, dict) and c.get("id") is not None]
    if len(set(map(repr, ids))) == len(ids):
        return connectors
    uuids = [_text_id(c.get("uuid")) if isinstance(c, dict) else None for c in connectors]
    if None in uuids or len(set(uuids)) != len(uuids):
        return connectors  # left for the converter to skip, as for any feed
    issues.add("connector ids repeat within an EVSE; Roam's own connector uuid used as each id")
    return [{**c, "id": uuid} for c, uuid in zip(connectors, uuids, strict=True)]


def ocpi_location(raw: object, issues: IssueLog) -> object:
    """Reshape one Roam location into an OCPI 2.2.1 Location."""
    if not isinstance(raw, dict) or not isinstance(raw.get("evses"), list):
        return raw
    evses = []
    for evse in raw["evses"]:
        if isinstance(evse, dict) and isinstance(evse.get("connectors"), list):
            evse = {**evse, "connectors": _connectors(evse["connectors"], issues)}
        evses.append(evse)
    location = {**raw, "evses": evses}
    if "parking_type" not in raw and "type" in raw:
        location["parking_type"] = raw["type"]
    return location


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
    """Fetch Roam's locations, then its tariffs (one page each), and convert them."""
    if date_from is not None or page_size is not None:
        raise FeedError(f"{config.id}: Roam's feed documents no date_from or page size")
    fetched_at = now or datetime.now(UTC).replace(microsecond=0)
    modules: dict[str, ModuleFetch] = {}
    for module in MODULES:
        try:
            modules[module] = fetch_module(
                client,
                module,
                config.endpoints[module].url,
                max_pages=max_pages,
                progress=progress,
            )
        except FeedError as exc:
            # Say how far the fetch got, for the run log (pipeline.run.failure_log).
            if exc.partial:
                modules[module] = exc.partial
            exc.modules = modules
            raise
    result = AdapterResult(config.id, fetched_at, modules)
    issues = IssueLog()
    convert_records(
        config,
        result,
        locations=[ocpi_location(raw, issues) for raw in modules["locations"].records],
        tariffs=modules["tariffs"].records,
        issues=issues,
    )
    result.issues = [client.redact(line) for line in issues.lines()]
    return result
