"""A status refresh: each charge point's status, read between the daily fetches (Phase 3,
docs/PHASE3_PLAN.md).

A refresh never reads a tariff and never changes what the map says about a location. It
reads each EVSE's status by the same rules as the daily fetch (evse_status in
adapters.ocpi_221.normalise), through the same polite client and rate limits.

- Eco-Movement's PCPR API has an endpoint for statuses alone
  (adapters.eco_movement.fetch_statuses): one request for a whole network.
- No other feed has one, so its locations module is fetched alone (an adapter's
  statuses_only option) and each EVSE's status is taken from the locations it gives.
- A copy an operator sent (sent_copy, ADR 0029) is never refreshed: a file sent once says
  nothing about now, so its statuses stay unknown.
"""

from dataclasses import dataclass, field
from datetime import datetime

from adapters.ocpi_221 import AdapterResult
from adapters.ocpi_221.client import ModuleFetch
from adapters.ocpi_221.normalise import (
    IssueLog,
    evse_status,
    excluded_evses,
    parse_ocpi_datetime,
)
from schema.live import LiveEvse
from schema.operator import OperatorConfig


@dataclass
class StatusResult:
    """What one operator's status refresh gave."""

    operator_id: str
    fetched_at: datetime
    modules: dict[str, ModuleFetch]
    # Each location's EVSEs, by the project's id for the location (schema.models.Location
    # id). When ocpi_ids is true they are instead by the location's OCPI id as the feed
    # sends it, for a feed whose statuses do not say which party a location belongs to;
    # pipeline.live_snapshot matches those to the locations on the map.
    statuses: dict[str, list[LiveEvse]] = field(default_factory=dict)
    ocpi_ids: bool = False
    # Ids of location records the feed sent that are not to be shown (publish flag false,
    # left off by the owner, or unreadable), so a snapshot drops them at once.
    dropped_location_ids: list[str] = field(default_factory=list)
    issues: list[str] = field(default_factory=list)
    requests: int = 0

    @property
    def complete(self) -> bool:
        return all(module.complete for module in self.modules.values())


def from_locations(result: AdapterResult) -> StatusResult:
    """The statuses in a fetch of the locations module alone (statuses_only)."""
    return StatusResult(
        operator_id=result.operator_id,
        fetched_at=result.fetched_at,
        modules=result.modules,
        statuses={
            location.id: [
                LiveEvse(uid=evse.uid, status=evse.status, status_at=evse.status_at)
                for evse in location.evses
            ]
            for location in result.locations
        },
        dropped_location_ids=list(result.dropped_location_ids),
        issues=list(result.issues),
        requests=result.requests,
    )


def _time(raw: dict, issues: IssueLog) -> datetime | None:
    try:
        return parse_ocpi_datetime(raw.get("last_updated"))
    except (TypeError, ValueError):
        issues.add("location last_updated is not a valid date and time; recorded as unknown")
        return None


def from_status_records(
    records: list, config: OperatorConfig, issues: IssueLog
) -> dict[str, list[LiveEvse]]:
    """Each location's EVSE statuses from records of the form Eco-Movement's statuses
    endpoint gives: {"id", "last_updated", "evses": [{"uid", "status", "last_updated"}]}.

    Keyed by the location's OCPI id as sent. An EVSE the owner left off (excluded_locations)
    is left out, a status that is not an OCPI 2.2.1 value is read by the operator file's
    rules, and a record that cannot be read is skipped and logged, never guessed.
    """
    statuses: dict[str, list[LiveEvse]] = {}
    for raw in records:
        if not isinstance(raw, dict) or raw.get("id") in (None, ""):
            issues.add("status record skipped: it has no location id")
            continue
        location_id = str(raw["id"])
        if location_id in statuses:
            issues.add("duplicate status record; kept the last copy")
        fallback = _time(raw, issues)
        left_off = excluded_evses(raw, config)
        evses: dict[str, LiveEvse] = {}
        for evse in raw.get("evses") or []:
            if not isinstance(evse, dict) or evse.get("uid") in (None, ""):
                issues.add("EVSE status skipped: it has no uid")
                continue
            uid = str(evse["uid"])
            if uid in left_off:
                continue
            status, status_at = evse_status(evse, fallback, issues, config)
            evses[uid] = LiveEvse(uid=uid, status=status, status_at=status_at)
        statuses[location_id] = list(evses.values())
    return statuses
