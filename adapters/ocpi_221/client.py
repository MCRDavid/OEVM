"""Fetch every page of an OCPI 2.2.1 list endpoint (locations or tariffs).

Paging follows OCPI 2.2.1 section 4.1.4.1 ("GET", under "Pagination"): follow the
Link header with rel="next"; if a server sends X-Total-Count but no Link, step on with
offset instead. date_from and limit are sent on the first request; servers keep them in
their Link.
"""

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime
from urllib.parse import urlencode, urljoin, urlsplit

import httpx

from adapters.http import FeedError, PoliteClient, redact_url, with_params

KEPT_HEADERS = ("content-type", "link", "x-total-count", "x-limit", "retry-after")
PAGE_SAFETY_LIMIT = 10_000


@dataclass
class Page:
    """One response, kept so it can be saved as a fixture. Contains no credentials."""

    url: str
    status_code: int
    headers: dict[str, str]
    body: object

    def to_exchange(self) -> dict:
        return {
            "request": {"method": "GET", "url": self.url},
            "response": {
                "status_code": self.status_code,
                "headers": self.headers,
                "body": self.body,
            },
        }


@dataclass
class ModuleFetch:
    module: str
    endpoint: str
    records: list[dict] = field(default_factory=list)
    pages: list[Page] = field(default_factory=list)
    total_reported: int | None = None
    complete: bool = False


def format_ocpi_datetime(value: datetime) -> str:
    return value.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def _int_header(response: httpx.Response, name: str) -> int | None:
    value = response.headers.get(name, "").strip()
    return int(value) if re.fullmatch(r"[0-9]+", value) else None


def _same_site(url: str, other: str) -> bool:
    a, b = urlsplit(url), urlsplit(other)
    return (a.scheme, a.netloc) == (b.scheme, b.netloc)


def _ocpi_data(body: object, url: str) -> list:
    if not isinstance(body, dict) or "status_code" not in body:
        raise FeedError(f"{redact_url(url)} did not return an OCPI response object")
    if not 1000 <= int(body["status_code"]) <= 1999:
        raise FeedError(
            f"{redact_url(url)} returned OCPI status {body['status_code']}: "
            f"{body.get('status_message')}"
        )
    data = body.get("data")
    if not isinstance(data, list):
        raise FeedError(f"{redact_url(url)} returned no list of records in 'data'")
    return data


def fetch_module(
    client: PoliteClient,
    module: str,
    endpoint: str,
    *,
    date_from: datetime | None = None,
    page_size: int | None = None,
    max_pages: int | None = None,
) -> ModuleFetch:
    """Fetch all pages of one module, or the first `max_pages` pages."""
    params = {}
    if date_from is not None:
        params["date_from"] = format_ocpi_datetime(date_from)
    if page_size is not None:
        params["limit"] = str(page_size)
    url: str | None = f"{endpoint}?{urlencode(params, safe=':')}" if params else endpoint

    result = ModuleFetch(module=module, endpoint=endpoint)
    seen_urls: set[str] = set()
    received = 0
    while url is not None:
        if max_pages is not None and len(result.pages) >= max_pages:
            return result
        if url in seen_urls or len(result.pages) >= PAGE_SAFETY_LIMIT:
            raise FeedError(f"paging did not finish at {redact_url(url)}")
        seen_urls.add(url)

        response = client.get(url)
        if response.status_code != 200:
            raise FeedError(f"{redact_url(url)} returned HTTP {response.status_code}")
        try:
            body = response.json()
        except ValueError as exc:
            raise FeedError(f"{redact_url(url)} did not return JSON") from exc
        data = _ocpi_data(body, url)

        result.records.extend(data)
        result.pages.append(
            Page(
                url=redact_url(url),
                status_code=response.status_code,
                headers={k: response.headers[k] for k in KEPT_HEADERS if k in response.headers},
                body=body,
            )
        )
        result.total_reported = _int_header(response, "X-Total-Count")
        received += len(data)

        next_link = response.links.get("next", {}).get("url")
        if next_link:
            url = urljoin(url, next_link)
            if not _same_site(url, endpoint):
                raise FeedError(f"next page link leaves {endpoint}: {redact_url(url)}")
        elif data and result.total_reported is not None and received < result.total_reported:
            url = with_params(url, {"offset": str(received)})
        else:
            url = None

    result.complete = True
    return result
