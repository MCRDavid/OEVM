"""A polite HTTP client for operator feeds.

- Identifies the project in the User-Agent header.
- Leaves at least the operator's gap between requests, measured from when the previous
  response finished, so network delays can never squeeze two requests closer together
  at the server's end.
- Keeps one timer per host, shared by every client in the process, so operators served
  from the same host share one gap and one Retry-After.
- Retries connection errors, timeouts, HTTP 429 and HTTP 5xx with exponential backoff.
- Honours every Retry-After header, in seconds or as an HTTP date, on any attempt. One
  that cannot be read is treated as a long wait. If the wait is longer than this project
  waits, nothing more is sent to that host until it has passed.
- Adds the operator's key from the environment variable named by `auth.secret_name`,
  and only ever sends it over https. Keys never appear in URLs this module returns, logs
  or raises, and `PoliteClient.redact` removes the key from anything a server sends back.
- Does not follow redirects, so a key can never be sent on to another site.

Timers live in memory, so they cover one run of the program. Runs that use the same host
must not be started in parallel.
"""

import os
import re
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlsplit, urlunsplit

import httpx

from pipeline.project import NAME, REPOSITORY_URL, VERSION
from schema.operator import (
    LIMIT_MARGIN_SECONDS,
    MIN_SECONDS_BETWEEN_REQUESTS,
    OperatorConfig,
    is_credential_param,
)

USER_AGENT = f"{NAME}/{VERSION} (+{REPOSITORY_URL})"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_WAIT_SECONDS = 600
UNREADABLE_RETRY_AFTER_SECONDS = 3600
REDACTED = "REDACTED"


class FeedError(Exception):
    """A feed could not be fetched, or did not return valid data."""


def redact_url(url: str) -> str:
    """Replace the value of any credential-like query parameter with REDACTED."""
    parts = urlsplit(url)
    query = [
        (name, "REDACTED" if is_credential_param(name) else value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
    ]
    return urlunsplit(parts._replace(query=urlencode(query, safe=":")))


def with_params(url: str, params: dict[str, str]) -> str:
    """Return url with each of `params` set, replacing any existing value."""
    parts = urlsplit(url)
    query = [
        (name, value)
        for name, value in parse_qsl(parts.query, keep_blank_values=True)
        if name not in params
    ]
    query.extend(params.items())
    return urlunsplit(parts._replace(query=urlencode(query, safe=":")))


def secret_value(config: OperatorConfig, key: str | None = None) -> str | None:
    """The operator's key, or None if the feed needs no key.

    The key comes from the environment variable named by auth.secret_name, unless `key` is
    given. Only fixture replays and tests pass `key`, with a made-up value.
    """
    auth = config.auth
    if auth.method == "none":
        return None
    if auth.method == "unknown" or auth.name in (None, "unknown") or not auth.secret_name:
        raise FeedError(f"{config.id}: auth details are not known yet")
    value = key or os.environ.get(auth.secret_name)
    if not value:
        raise FeedError(
            f"{config.id}: the environment variable {auth.secret_name} is not set. "
            "In GitHub Actions, add it as a repository secret with that name."
        )
    return value


def credentials_for(
    config: OperatorConfig, key: str | None = None
) -> tuple[dict[str, str], dict[str, str]]:
    """Headers and query parameters that carry the operator's key."""
    value = secret_value(config, key)
    if value is None:
        return {}, {}
    auth = config.auth
    if auth.method == "header":
        return {auth.name: f"{auth.scheme} {value}" if auth.scheme else value}, {}
    return {}, {auth.name: value}


def scrub(value: object, secrets: Iterable[str]) -> object:
    """value with every secret, as sent or URL-encoded, replaced by REDACTED.

    Works through strings, lists and dict keys and values, so a whole response body can be
    cleaned before it is saved or shown.
    """
    forms = sorted(
        {
            form
            for secret in secrets
            if secret
            for form in (secret, quote(secret, safe=""), quote_plus(secret))
        },
        key=len,
        reverse=True,
    )
    if not forms:
        return value

    def clean(item: object) -> object:
        if isinstance(item, str):
            for form in forms:
                item = item.replace(form, REDACTED)
            return item
        if isinstance(item, list):
            return [clean(part) for part in item]
        if isinstance(item, dict):
            return {clean(key): clean(part) for key, part in item.items()}
        return item

    return clean(value)


def retry_after_seconds(response: httpx.Response, now: datetime) -> float | None:
    """Seconds the server asked this project to wait, or None if it did not say.

    RFC 9110 allows a whole number of seconds or an HTTP date. A value that cannot be
    read is treated as a long wait, never as no wait.
    """
    value = response.headers.get("Retry-After")
    if value is None:
        return None
    value = value.strip()
    if re.fullmatch(r"[0-9]+", value):
        return float(value)
    try:
        when = parsedate_to_datetime(value)
    except (TypeError, ValueError, IndexError):
        return float(UNREADABLE_RETRY_AFTER_SECONDS)
    if when.tzinfo is None:
        when = when.replace(tzinfo=UTC)
    return max(0.0, (when - now).total_seconds())


@dataclass
class HostTimer:
    """When the last request to one host finished, and the earliest the next may start."""

    last_finished_at: float | None = None
    not_before: float | None = None

    def hold_until(self, moment: float) -> None:
        self.not_before = moment if self.not_before is None else max(self.not_before, moment)


_HOST_TIMERS: dict[str, HostTimer] = {}


def host_timer(url: str) -> HostTimer:
    return _HOST_TIMERS.setdefault(urlsplit(url).netloc.lower(), HostTimer())


def reset_host_timers() -> None:
    """Forget every timer. Tests call this because each test has its own fake clock."""
    _HOST_TIMERS.clear()


def required_gap(config: OperatorConfig) -> float:
    """The gap the client keeps: never less than the floor or what any limit needs."""
    rate = config.rate_limit
    return max(
        MIN_SECONDS_BETWEEN_REQUESTS,
        rate.min_seconds_between_requests,
        *(limit.min_interval + LIMIT_MARGIN_SECONDS for limit in rate.limits),
    )


class PoliteClient:
    """GET requests to one operator, spaced out and retried. Use as a context manager."""

    def __init__(
        self,
        config: OperatorConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        wall_clock: Callable[[], datetime] = lambda: datetime.now(UTC),
        max_retries: int = 3,
        backoff_seconds: float = 5.0,
        timeout_seconds: float = 60.0,
        key: str | None = None,
    ):
        headers, self._auth_params = credentials_for(config, key)
        secret = secret_value(config, key)
        self._secrets = (secret,) if secret else ()
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json", **headers},
            timeout=timeout_seconds,
            transport=transport,
            follow_redirects=False,
        )
        self.min_interval = required_gap(config)
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._clock = clock
        self._wall_clock = wall_clock
        self.requests_made = 0

    def __enter__(self) -> "PoliteClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._client.close()

    def redact(self, value: object) -> object:
        """value with this operator's key removed, wherever a server may have echoed it."""
        return scrub(value, self._secrets)

    def _refuse_if_held(self, timer: HostTimer, url: str) -> None:
        if timer.not_before is None:
            return
        wait = timer.not_before - self._clock()
        if wait > MAX_RETRY_WAIT_SECONDS:
            raise FeedError(
                f"not requesting {redact_url(url)}: the server asked this project to wait "
                f"another {wait:g} s, longer than it waits ({MAX_RETRY_WAIT_SECONDS} s); "
                "try later"
            )

    def _wait_turn(self, timer: HostTimer) -> None:
        now = self._clock()
        ready = now
        if timer.last_finished_at is not None:
            ready = max(ready, timer.last_finished_at + self.min_interval)
        if timer.not_before is not None:
            ready = max(ready, timer.not_before)
        if ready > now:
            self._sleep(ready - now)

    def get(self, url: str) -> httpx.Response:
        """GET url, retrying temporary failures. Raises FeedError when retries run out."""
        if self._secrets and urlsplit(url).scheme != "https":
            raise FeedError(f"not sending a key over plain http: {redact_url(url)}")
        timer = host_timer(url)
        request_url = with_params(url, self._auth_params) if self._auth_params else url
        for attempt in range(self.max_retries + 1):
            self._refuse_if_held(timer, url)
            self._wait_turn(timer)
            self.requests_made += 1
            response = None
            try:
                response = self._client.get(request_url)
            except httpx.TransportError as exc:
                problem, retry_after = type(exc).__name__, None
            finally:
                timer.last_finished_at = self._clock()
            if response is not None:
                if response.status_code not in RETRY_STATUSES:
                    return response
                problem = f"HTTP {response.status_code}"
                retry_after = retry_after_seconds(response, self._wall_clock())

            now = self._clock()
            if retry_after is not None:
                timer.hold_until(now + retry_after)
            if attempt == self.max_retries:
                asked = (
                    f"; the server asked to wait {retry_after:g} s"
                    if retry_after is not None
                    else ""
                )
                raise FeedError(
                    f"gave up on {redact_url(url)} after {attempt + 1} attempts: {problem}{asked}"
                )
            if retry_after is None:
                timer.hold_until(now + self.backoff_seconds * 2**attempt)
        raise AssertionError("unreachable")
