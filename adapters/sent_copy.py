"""Adapter for a copy of an operator's data that it sent (registry adapter name: sent_copy).

Some operators send their regulation 10 data as files, for example attached to an email,
rather than publishing it at an address that can be fetched. Where the repository owner
has decided to show such a copy (sent_copy in the operator file, ADR 0029), the files are
kept in the repository exactly as sent, gzipped, under sent_copies/<operator id>/, and
this adapter reads them on every run. It makes no request to the operator.

The files must be OCPI 2.2.1 locations and tariffs responses. They go through the same
conversion as a fetched feed (adapters.ocpi_221.convert_records), so the publish flag
rule and every other rule apply. Two things differ, so nothing looks newer than it is:

- every record carries the time the operator made the copy (made_at), never the time of
  the run, and its provenance method is operator_static_file;
- every charge point status is set to unknown, because a status in a file sent once says
  nothing about now. The run log says how many statuses were set aside.
"""

import gzip
import json
from datetime import UTC, datetime
from pathlib import Path

from adapters.http import FeedError, PoliteClient
from adapters.ocpi_221 import MODULES, AdapterResult, convert_records
from adapters.ocpi_221.client import ModuleFetch
from adapters.ocpi_221.normalise import IssueLog
from adapters.progress import NO_PROGRESS, PageProgress
from pipeline.project import REPOSITORY_URL
from schema.models import Location, Tariff
from schema.operator import OperatorConfig

ROOT = Path(__file__).resolve().parent.parent
# How a copy came, as words to follow "sent this data".
CHANNEL_WORDS = {
    "email": " by email",
    "web_form": " through a web form",
    "support_ticket": " through a support ticket",
    "post": " by post",
    "other": "",
}


def folder_url(path: str) -> str:
    """The repository page that lists a sent copy's files and says where they came from."""
    return f"{REPOSITORY_URL}/tree/main/{Path(path).parent.as_posix()}"


def read_response(path: Path, module: str) -> list[dict]:
    """The records in one OCPI 2.2.1 response file, gzipped or not."""
    opener = gzip.open if path.suffix == ".gz" else open
    try:
        with opener(path, "rt", encoding="utf-8") as file:
            body = json.load(file)
    except FileNotFoundError:
        raise FeedError(f"the sent {module} file {path.name} is missing") from None
    except (OSError, ValueError) as exc:
        raise FeedError(f"the sent {module} file {path.name} cannot be read: {exc}") from None
    if not isinstance(body, dict) or not isinstance(body.get("data"), list):
        raise FeedError(f"the sent {module} file {path.name} is not an OCPI response with a list")
    status = body.get("status_code")
    if not isinstance(status, int) or not 1000 <= status <= 1999:
        raise FeedError(f"the sent {module} file {path.name} has status_code {status!r}")
    return body["data"]


def as_sent(record: Location | Tariff) -> Location | Tariff:
    """The record marked as read from a file the operator sent, not from a feed."""
    provenance = record.provenance.model_copy(update={"method": "operator_static_file"})
    return record.model_copy(update={"provenance": provenance})


def without_statuses(location: Location) -> tuple[Location, int]:
    """The location with every EVSE status unknown, and how many statuses were set aside."""
    known = sum(evse.status != "unknown" for evse in location.evses)
    evses = [
        evse.model_copy(update={"status": "unknown", "status_at": None}) for evse in location.evses
    ]
    return location.model_copy(update={"evses": evses}), known


def fetch(
    config: OperatorConfig,
    client: PoliteClient,
    *,
    date_from: datetime | None = None,
    page_size: int | None = None,
    max_pages: int | None = None,
    progress: PageProgress = NO_PROGRESS,
) -> AdapterResult:
    """Read the copy. The client is never used: a sent copy makes no request."""
    if config.adapter != "sent_copy" or config.sent_copy is None:
        raise FeedError(f"{config.id} has no sent copy recorded by the owner")
    copy = config.sent_copy
    modules = {}
    for module in MODULES:
        path = getattr(copy, module)
        records = read_response(ROOT / path, module)
        modules[module] = ModuleFetch(
            module=module,
            endpoint=folder_url(path),
            records=records,
            total_reported=len(records),
            complete=True,
        )
    made_at = copy.made_at.astimezone(UTC)
    result = AdapterResult(operator_id=config.id, fetched_at=made_at, modules=modules)
    issues = IssueLog()
    convert_records(
        config,
        result,
        locations=modules["locations"].records,
        tariffs=modules["tariffs"].records,
        issues=issues,
    )
    set_aside = 0
    for index, location in enumerate(result.locations):
        result.locations[index], known = without_statuses(as_sent(location))
        set_aside += known
    result.tariffs = [as_sent(tariff) for tariff in result.tariffs]
    lines = issues.lines()
    lines.append(
        f"Read from a copy the operator sent on {copy.received:%Y-%m-%d}, made "
        f"{made_at:%Y-%m-%d %H:%M} UTC; no request was made."
    )
    if set_aside:
        lines.append(f"{set_aside} charge point statuses in the copy shown as unknown.")
    result.issues = lines
    return result
