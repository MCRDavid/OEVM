"""Adapter for standard OCPI 2.2.1 feeds (registry adapter name: ocpi_221).

Fetches the locations and tariffs modules and converts them to the project's models.
Records that cannot be used are skipped and logged, as OCPI 2.2.1 section 4.1.4.1
advises, so one bad record never hides the rest of a feed.

Locations with publish set to false are never kept: OCPI 2.2.1 says such a location may
not be published on a website or app. Locations without a publish flag are skipped too,
unless the operator file records the owner's decision to show them (see
normalise.publish_allowed). Other adapters reuse `convert_records`, so the same rules
apply to every feed.
"""

from dataclasses import dataclass, field
from datetime import UTC, datetime

from pydantic import ValidationError

from adapters.http import FeedError, PoliteClient
from adapters.ocpi_221.client import ModuleFetch, fetch_module
from adapters.ocpi_221.normalise import (
    IssueLog,
    location_from_ocpi,
    location_record_id,
    publish_allowed,
    tariff_from_ocpi,
)
from adapters.progress import NO_PROGRESS, PageProgress
from schema.models import Location, Tariff
from schema.operator import OperatorConfig

MODULES = ("locations", "tariffs")


@dataclass
class AdapterResult:
    operator_id: str
    fetched_at: datetime
    modules: dict[str, ModuleFetch]
    locations: list[Location] = field(default_factory=list)
    tariffs: list[Tariff] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    requests: int = 0
    # Ids of location records the feed sent but this result leaves out: not to be
    # published, or unreadable. A snapshot built from a fetch of changes removes them.
    dropped_location_ids: list[str] = field(default_factory=list)

    @property
    def complete(self) -> bool:
        return all(module.complete for module in self.modules.values())


def endpoint_for(config: OperatorConfig, module: str) -> str:
    if module in config.endpoints:
        return config.endpoints[module].url
    if config.base_url != "unknown":
        return f"{config.base_url.rstrip('/')}/{module}"
    raise FeedError(f"{config.id}: no {module} endpoint or base_url is known")


def _describe(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        error = exc.errors()[0]
        location = ".".join(str(part) for part in error["loc"])
        return f"{location}: {error['msg']}" if location else error["msg"]
    if isinstance(exc, KeyError):
        return f"missing field {exc}"
    return str(exc) or type(exc).__name__


def _latest_by_id(records: list[dict], kind: str, issues: IssueLog) -> list[dict]:
    """Keep one copy of each record; a later copy replaces an earlier one."""
    latest: dict[tuple, dict] = {}
    for raw in records:
        key = (raw.get("country_code"), raw.get("party_id"), raw.get("id"))
        if key in latest:
            issues.add(f"duplicate {kind} record; kept the last copy")
        latest[key] = raw
    return list(latest.values())


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
    if config.adapter != "ocpi_221":
        raise FeedError(f"{config.id} uses the {config.adapter} adapter, not ocpi_221")
    fetched_at = now or datetime.now(UTC).replace(microsecond=0)
    modules: dict[str, ModuleFetch] = {}
    # One URL answers every module (response_envelope by_module): request it once.
    responses = {} if config.response_envelope == "by_module" else None
    for module in MODULES:
        try:
            modules[module] = fetch_module(
                client,
                module,
                endpoint_for(config, module),
                date_from=date_from,
                page_size=page_size,
                max_pages=max_pages,
                progress=progress,
                envelope=config.response_envelope,
                responses=responses,
            )
        except FeedError as exc:
            # Say how far the fetch got, for the run log (pipeline.run.failure_log).
            exc.modules = {**modules, **({module: exc.partial} if exc.partial else {})}
            raise
    result = AdapterResult(operator_id=config.id, fetched_at=fetched_at, modules=modules)
    issues = IssueLog()
    convert_records(
        config,
        result,
        locations=modules["locations"].records,
        tariffs=modules["tariffs"].records,
        issues=issues,
    )
    result.issues = [client.redact(line) for line in issues.lines()]
    return result


def _dropped(result: AdapterResult, raw: dict, config: OperatorConfig) -> None:
    record_id = location_record_id(raw, config)
    if record_id is not None:
        result.dropped_location_ids.append(record_id)


def convert_records(
    config: OperatorConfig,
    result: AdapterResult,
    *,
    locations: list[dict],
    tariffs: list[dict],
    issues: IssueLog,
    tariff_sources: dict[str, str] | None = None,
) -> None:
    """Convert OCPI 2.2.1 location and tariff objects into result, logging any problems.

    tariff_sources maps a tariff id to the URL it was fetched from, for feeds that serve
    one tariff per request; otherwise each record's source is its module's endpoint.
    """
    source = result.modules["locations"].endpoint
    for raw in _latest_by_id(locations, "location", issues):
        if not publish_allowed(raw, config, issues):
            _dropped(result, raw, config)
            continue
        try:
            result.locations.append(
                location_from_ocpi(
                    raw, config, source_url=source, fetched_at=result.fetched_at, issues=issues
                )
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            issues.add(f"location {raw.get('id')!r} skipped: {_describe(exc)}")
            _dropped(result, raw, config)

    endpoint = result.modules["tariffs"].endpoint
    for raw in _latest_by_id(tariffs, "tariff", issues):
        source = (tariff_sources or {}).get(str(raw.get("id")), endpoint)
        try:
            result.tariffs.append(
                tariff_from_ocpi(
                    raw, config, source_url=source, fetched_at=result.fetched_at, issues=issues
                )
            )
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            issues.add(f"tariff {raw.get('id')!r} skipped: {_describe(exc)}")
