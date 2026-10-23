"""Adapter for Monta's UK open data (registry: id monta, adapter custom).

Monta publishes the open data of the UK charge points run on its platform through one
endpoint of its Public API, in OCPI 2.2.1 Location format. The differences, recorded as
findings in operators/monta.yaml on 2026-10-22 and 2026-10-23, are:

- Reading needs an access token, requested once per run with the client id and secret
  of an application registered in the Monta portal (auth method client_credentials).
- Each page is {"data": [...], "meta": {"pagination": {"after": ..., "has_more": ...}}},
  with a cursor rather than the OCPI response format and Link headers. With
  group_by_location=true each site is one Location, and the cursor is the lowest charge
  point id in a site: after=N returns the sites whose lowest id is above N.
- The server answers HTTP 500 for some sites, and for any page that holds one. A page
  that fails is asked for again as pages of 10, then 1. When one site fails on its own,
  the adapter looks for the smallest cursor past the last good one that answers,
  doubling the step and then halving the gap, so only that site is skipped. Each skip
  is logged and the fetch is marked incomplete.
- Each Location names its site owner in owner, often a private individual. The field is
  removed from every record as soon as it is read, so owner names are never kept, saved,
  logged or shown.
- No tariffs are given (every EVSE's tariffs list is empty), so prices are unknown.

Records are then converted by adapters.ocpi_221.convert_records, so the publish rule and
every model rule apply as for any other feed.
"""

from datetime import UTC, datetime

from adapters.http import FeedError, PoliteClient, redact_url, with_params
from adapters.ocpi_221 import AdapterResult, convert_records
from adapters.ocpi_221.client import KEPT_HEADERS, ModuleFetch, Page
from adapters.ocpi_221.normalise import IssueLog
from adapters.progress import NO_PROGRESS, PageProgress
from schema.operator import OperatorConfig

PAGE_SIZES = (100, 10, 1)
# Pages that work in a row before asking for bigger pages again.
BACK_UP_AFTER = 5
# Requests for one run, the token request included, and sites skipped, at most. At 7
# seconds apart, 450 requests take under an hour.
MAX_REQUESTS = 450
MAX_SKIPS = 30
SERVER_ERROR = 500
# Charge point ids are 64-bit numbers.
MAX_STEP = 2**62
REMOVED_FIELDS = ("owner",)


def _without_owner(record: object) -> object:
    if isinstance(record, dict):
        return {key: value for key, value in record.items() if key not in REMOVED_FIELDS}
    return record


class _Reader:
    """Reads the locations list, page by page, skipping sites the server cannot send."""

    def __init__(self, client: PoliteClient, url: str, issues: IssueLog):
        self.client = client
        self.url = url
        self.issues = issues
        self.module = ModuleFetch("locations", url)
        self.skipped = 0

    def _get(self, after: int | None, size: int):
        params = {"per_page": str(size), "group_by_location": "true"}
        if after is not None:
            params["after"] = str(after)
        url = with_params(self.url, params)
        return url, self.client.get(url, return_at_once=frozenset({SERVER_ERROR}))

    def _skip_past(self, after: int):
        """The first cursor above `after` that answers, with its answer, or None.

        Every cursor from `after` up to the failing site's own id answers HTTP 500, and
        every cursor from that id up to the next site's id answers, so the smallest
        cursor that answers is the failing site's id.
        """
        low, step, found = after, 1, None
        while step <= MAX_STEP and self.client.requests_made < MAX_REQUESTS:
            url, response = self._get(after + step, 1)
            if response.status_code == 200:
                found = (after + step, url, response)
                break
            if response.status_code != SERVER_ERROR:
                raise FeedError(f"{redact_url(url)} returned HTTP {response.status_code}")
            low, step = after + step, step * 2
        if found is None:
            return None
        high, url, response = found
        while high - low > 1 and self.client.requests_made < MAX_REQUESTS:
            middle = (low + high) // 2
            middle_url, middle_response = self._get(middle, 1)
            if middle_response.status_code == 200:
                high, url, response = middle, middle_url, middle_response
            elif middle_response.status_code == SERVER_ERROR:
                low = middle
            else:
                raise FeedError(
                    f"{redact_url(middle_url)} returned HTTP {middle_response.status_code}"
                )
        return high, url, response

    def read(self, max_pages: int | None, progress: PageProgress) -> ModuleFetch:
        after: int | None = None
        level = streak = 0
        while max_pages is None or len(self.module.pages) < max_pages:
            if self.client.requests_made >= MAX_REQUESTS:
                self.issues.add(
                    f"stopped after {MAX_REQUESTS} requests, the most for one run; "
                    "the rest of the list was not read"
                )
                return self.module
            url, response = self._get(after, PAGE_SIZES[level])
            if response.status_code == SERVER_ERROR and level < len(PAGE_SIZES) - 1:
                level, streak = level + 1, 0
                continue
            if response.status_code == SERVER_ERROR:
                if after is None:
                    raise FeedError(f"{redact_url(url)} returned HTTP 500 for the first site")
                if self.skipped >= MAX_SKIPS:
                    self.issues.add(
                        f"stopped after skipping {MAX_SKIPS} sites the server could not "
                        "send; the rest of the list was not read"
                    )
                    return self.module
                skip = self._skip_past(after)
                if skip is None:
                    self.issues.add(
                        "stopped: no cursor past a site the server could not send answered"
                    )
                    return self.module
                after, url, response = skip
                self.skipped += 1
                level = streak = 0
            elif response.status_code != 200:
                raise FeedError(f"{redact_url(url)} returned HTTP {response.status_code}")
            else:
                streak += 1
            try:
                body = response.json()
            except ValueError as exc:
                raise FeedError(f"{redact_url(url)} did not return JSON") from exc
            records = body.get("data") if isinstance(body, dict) else None
            if not isinstance(records, list):
                raise FeedError(f"{redact_url(url)} returned no list of locations")
            records = [_without_owner(record) for record in records]
            pagination = (body.get("meta") or {}).get("pagination") or {}
            self.module.records += records
            headers = {k: response.headers[k] for k in KEPT_HEADERS if k in response.headers}
            kept = {"data": records, "meta": body.get("meta")}
            page = Page(redact_url(url), 200, self.client.redact(headers), self.client.redact(kept))
            self.module.pages.append(page)
            progress.page("locations", pages=len(self.module.pages), records=len(records))
            if level and streak >= BACK_UP_AFTER:
                level, streak = level - 1, 0
            next_after = pagination.get("after")
            if not pagination.get("has_more") or not records:
                self.module.complete = self.skipped == 0
                return self.module
            if not isinstance(next_after, int) or isinstance(next_after, bool):
                raise FeedError(f"{redact_url(url)} gave no cursor for the next page")
            if after is not None and next_after <= after:
                raise FeedError(f"{redact_url(url)} gave a cursor that does not move forward")
            after = next_after
        return self.module


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
    """Request a token, then read every site in the list, 100 at a time."""
    if date_from is not None or page_size is not None:
        raise FeedError(f"{config.id}: this adapter sets its own page size and has no date_from")
    fetched_at = now or datetime.now(UTC).replace(microsecond=0)
    issues = IssueLog()
    client.request_token(
        id_field="clientId", secret_field="clientSecret", token_field="accessToken"
    )
    url = config.endpoints["locations"].url
    reader = _Reader(client, url, issues)
    locations = reader.read(max_pages, progress)
    if reader.skipped:
        issues.add(
            f"{reader.skipped} site(s) skipped: the server answered HTTP 500 for each, "
            "even asked for on its own"
        )
    progress.module_done(
        "locations",
        pages=len(locations.pages),
        records=len(locations.records),
        complete=locations.complete,
    )
    # Monta's open data has no tariffs; every EVSE's tariffs list is empty.
    tariffs = ModuleFetch("tariffs", url, complete=True)
    result = AdapterResult(config.id, fetched_at, {"locations": locations, "tariffs": tariffs})
    convert_records(config, result, locations=locations.records, tariffs=[], issues=issues)
    result.issues = [client.redact(line) for line in issues.lines()]
    return result
