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
  doubling the step and then halving the gap, so only the failing site (or run of
  failing sites) is skipped. Each skip is logged and the fetch is marked incomplete.
- Since 13 November 2026 a page near the end of the list answers HTTP 504 with
  Retry-After: 120. In the daily fetch a 504 is handled as a 500 is, by the repository
  owner's decision of 2026-11-14: the client waits the 120 seconds after each one, and
  the waits one run may be asked for are capped (MAX_WAIT_SECONDS). The status refresh
  keeps the client's ordinary retries for a 504, as it runs each hour.
- Each Location names its site owner in owner, often a private individual. The field is
  removed from every record as soon as it is read, so owner names are never kept, saved,
  logged or shown.
- Most sites listed have every charger marked REMOVED. OCPI 2.2.1 says "A Location
  without any valid EVSE object can be considered expired and should no longer be
  displayed" (Locations module, Flow and Lifecycle), so those sites are not kept.
- There is no tariffs module. Monta puts OCPI 2.2.1 Tariff objects in each EVSE's own
  tariffs list (a Monta extension), "empty when no OCPI tariff is available for the charge
  point"; few are filled (5 of 4,775 locations on 23 October 2026). The adapter takes the
  tariffs from the sites it keeps, one copy of each, and converts them like any feed's.

Records are then converted by adapters.ocpi_221.convert_records, so the publish rule and
every model rule apply as for any other feed.
"""

from datetime import UTC, datetime

from adapters.http import FeedError, PoliteClient, redact_url, retry_after_seconds, with_params
from adapters.ocpi_221 import AdapterResult, convert_records
from adapters.ocpi_221.client import KEPT_HEADERS, ModuleFetch, Page
from adapters.ocpi_221.normalise import IssueLog, location_record_id
from adapters.progress import NO_PROGRESS, PageProgress
from schema.operator import OperatorConfig

PAGE_SIZES = (100, 10, 1)
# Pages that work in a row before asking for bigger pages again.
BACK_UP_AFTER = 5
# Requests for one run, the token request included, and skips, at most. A full read took
# 81 requests on 23 October 2026; at 7 seconds apart, 300 take 35 minutes.
MAX_REQUESTS = 300
MAX_SKIPS = 30
SERVER_ERROR = 500
GATEWAY_TIMEOUT = 504
# Answers that mean the server cannot send a page: HTTP 504 too in the daily fetch, only
# HTTP 500 in the status refresh (the repository owner's decision of 2026-11-14).
CANNOT_SEND = frozenset({SERVER_ERROR, GATEWAY_TIMEOUT})
CANNOT_SEND_IN_REFRESH = frozenset({SERVER_ERROR})
# The most waiting, in seconds, that those answers may ask for in one run. The client
# waits every wait asked for, so with the requests above a run stays inside the daily
# fetch job's 150 minutes. Skipping one failing site takes the three page sizes, then
# about one and a half failing answers for each doubling of the gap to the site: about 30
# for a gap of 100,000 ids, an hour at 120 seconds each (estimated, not measured).
MAX_WAIT_SECONDS = 80 * 60
# Charge point ids are 64-bit numbers.
MAX_STEP = 2**62
REMOVED_FIELDS = ("owner",)


def _expired(record: object) -> bool:
    """Whether a site has no EVSE that is not REMOVED (OCPI 2.2.1: expired)."""
    if not isinstance(record, dict) or not isinstance(record.get("evses"), list):
        return False
    return all(isinstance(e, dict) and e.get("status") == "REMOVED" for e in record["evses"])


def _tariff_lists(record: dict):
    """The tariffs lists of a site and of each of its EVSEs."""
    yield record.get("tariffs")
    for evse in record.get("evses") or []:
        if isinstance(evse, dict):
            yield evse.get("tariffs")


def _inline_tariffs(records: list[dict], issues: IssueLog) -> list[dict]:
    """One copy of each tariff the sites carry. Where two copies with the same id differ,
    the one updated last is kept."""
    found: dict[tuple, dict] = {}
    for record in records:
        for tariffs in _tariff_lists(record):
            for tariff in tariffs if isinstance(tariffs, list) else []:
                if not isinstance(tariff, dict):
                    issues.add("tariff in an EVSE's tariffs list is not an object; ignored")
                    continue
                key = (tariff.get("country_code"), tariff.get("party_id"), tariff.get("id"))
                kept = found.get(key)
                if kept is not None and kept != tariff:
                    issues.add(
                        "tariff given differently at two chargers; kept the copy updated last"
                    )
                    if str(tariff.get("last_updated")) < str(kept.get("last_updated")):
                        continue
                found[key] = tariff
    return list(found.values())


def _without_owner(record: object) -> object:
    if isinstance(record, dict):
        return {key: value for key, value in record.items() if key not in REMOVED_FIELDS}
    return record


class _Reader:
    """Reads the locations list, page by page, skipping sites the server cannot send."""

    def __init__(
        self,
        client: PoliteClient,
        url: str,
        issues: IssueLog,
        cannot_send: frozenset[int] = CANNOT_SEND,
    ):
        self.client = client
        self.url = url
        self.issues = issues
        self.cannot_send = cannot_send
        self.module = ModuleFetch("locations", url)
        self.skipped = 0
        self.skipped_for: set[int] = set()
        self.waited = 0.0

    def _get(self, after: int | None, size: int):
        params = {"per_page": str(size), "group_by_location": "true"}
        if after is not None:
            params["after"] = str(after)
        url = with_params(self.url, params)
        response = self.client.get(url, return_at_once=self.cannot_send)
        if response.status_code in self.cannot_send:
            # The client waits as long as the answer asks before its next request.
            self.waited += retry_after_seconds(response, datetime.now(UTC)) or 0.0
        return url, response

    def _can_ask(self) -> bool:
        return self.client.requests_made < MAX_REQUESTS and self.waited < MAX_WAIT_SECONDS

    def _skip_past(self, after: int):
        """The first cursor above `after` that answers, with its answer, or None.

        Every cursor from `after` up to the failing site's own id answers HTTP 500 (or
        504 where that counts), and every cursor from that id up to the next site's id
        answers, so the smallest cursor that answers is the failing site's id. Where
        failing sites come one after another, it is the last one's id: one skip passes
        them all, and how many there were cannot be known.
        """
        low, step, found = after, 1, None
        while step <= MAX_STEP and self._can_ask():
            url, response = self._get(after + step, 1)
            if response.status_code == 200:
                found = (after + step, url, response)
                break
            if response.status_code not in self.cannot_send:
                raise FeedError(f"{redact_url(url)} returned HTTP {response.status_code}")
            low, step = after + step, step * 2
        if found is None:
            return None
        high, url, response = found
        while high - low > 1 and self._can_ask():
            middle = (low + high) // 2
            middle_url, middle_response = self._get(middle, 1)
            if middle_response.status_code == 200:
                high, url, response = middle, middle_url, middle_response
            elif middle_response.status_code in self.cannot_send:
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
            if self.waited >= MAX_WAIT_SECONDS:
                self.issues.add(
                    f"stopped after the server asked for {MAX_WAIT_SECONDS // 60} minutes of "
                    "waits on pages it could not send; the rest of the list was not read"
                )
                return self.module
            url, response = self._get(after, PAGE_SIZES[level])
            status = response.status_code
            if status in self.cannot_send and level < len(PAGE_SIZES) - 1:
                level, streak = level + 1, 0
                continue
            if status in self.cannot_send:
                if after is None:
                    raise FeedError(f"{redact_url(url)} returned HTTP {status} for the first site")
                if self.skipped >= MAX_SKIPS:
                    self.issues.add(
                        f"stopped after skipping {MAX_SKIPS} times past sites the server could not "
                        "send; the rest of the list was not read"
                    )
                    return self.module
                skip = self._skip_past(after)
                if skip is None and not self._can_ask():
                    continue  # the checks at the top say why the run stops
                if skip is None:
                    self.issues.add(
                        "stopped: no cursor past a site the server could not send answered"
                    )
                    return self.module
                after, url, response = skip
                self.skipped += 1
                self.skipped_for.add(status)
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
            progress.page(
                "locations", pages=len(self.module.pages), records=len(self.module.records)
            )
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
    statuses_only: bool = False,
) -> AdapterResult:
    """Request a token, then read every site in the list, 100 at a time. A status refresh
    (statuses_only) makes the same requests, as the list is the only place statuses are,
    and reads no tariff from it."""
    if date_from is not None or page_size is not None:
        raise FeedError(f"{config.id}: this adapter sets its own page size and has no date_from")
    fetched_at = now or datetime.now(UTC).replace(microsecond=0)
    issues = IssueLog()
    # Field names in Monta's token request and reply, not values.
    client.request_token(
        id_field="clientId",
        secret_field="clientSecret",  # pragma: allowlist secret
        token_field="accessToken",
    )
    url = config.endpoints["locations"].url
    reader = _Reader(client, url, issues, CANNOT_SEND_IN_REFRESH if statuses_only else CANNOT_SEND)
    locations = reader.read(max_pages, progress)
    if reader.skipped:
        answered = " or ".join(str(status) for status in sorted(reader.skipped_for))
        issues.add(
            f"skipped {reader.skipped} time(s) past sites the server answered HTTP {answered} "
            "for, even asked for one at a time (at least one site each time)"
        )
    progress.module_done(
        "locations",
        pages=len(locations.pages),
        records=len(locations.records),
        complete=locations.complete,
    )
    # No tariffs module: the tariffs come from the EVSEs of the sites kept, below.
    tariffs = ModuleFetch("tariffs", url, complete=True)
    modules = {"locations": locations}
    if not statuses_only:
        modules["tariffs"] = tariffs
    result = AdapterResult(config.id, fetched_at, modules, statuses_only=statuses_only)
    current = []
    for record in locations.records:
        if _expired(record):
            issues.add(
                "location not kept: it has no EVSE that is not REMOVED (OCPI 2.2.1: expired)"
            )
            record_id = location_record_id(record, config)
            if record_id is not None:
                result.dropped_location_ids.append(record_id)
        else:
            current.append(record)
    if not statuses_only:
        tariffs.records = _inline_tariffs(current, issues)
    convert_records(config, result, locations=current, tariffs=tariffs.records, issues=issues)
    result.issues = [client.redact(line) for line in issues.lines()]
    return result
