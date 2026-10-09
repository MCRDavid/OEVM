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
- Sends an operator's requests through the project's relay when the operator file
  records that decision and the relay's address and token are set in the environment.
  The relay gets the same request path and User-Agent; gaps, retries and every message
  still refer to the operator's own host and URLs. Only feeds with no key are relayed.

Timers live in memory, so they cover one run of the program. Runs that use the same host
must not be started in parallel. Within one run, pipeline.run fetches operators on
different hosts at the same time, but never two operators that share a host
(`operator_hosts`).
"""

import os
import re
import threading
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
_HOST_TIMERS_LOCK = threading.Lock()


def host_timer(url: str) -> HostTimer:
    with _HOST_TIMERS_LOCK:
        return _HOST_TIMERS.setdefault(urlsplit(url).netloc.lower(), HostTimer())


def reset_host_timers() -> None:
    """Forget every timer. Tests call this because each test has its own fake clock."""
    with _HOST_TIMERS_LOCK:
        _HOST_TIMERS.clear()


# Stands for the project's relay in operator_hosts: relayed operators all go through the
# one relay Worker, so they are treated as sharing a host and fetched one at a time.
RELAY_HOST = "relay"


def operator_hosts(config: OperatorConfig) -> frozenset[str]:
    """Every host this operator's requests can reach: its endpoints, base URL and relay.

    Paging never leaves an endpoint's host (adapters.ocpi_221.client). An operator with no
    known host gets the empty name, so all such operators count as sharing one host.
    """
    urls = [endpoint.url for endpoint in config.endpoints.values()]
    if config.base_url != "unknown":
        urls.append(config.base_url)
    hosts = {urlsplit(url).netloc.lower() for url in urls if url != "unknown"}
    if config.relay is not None:
        hosts.add(RELAY_HOST)
    return frozenset(hosts or {""})


RELAY_TOKEN_HEADER = "X-Relay-Token"


@dataclass(frozen=True)
class RelayRoute:
    """Where an operator's requests go when they are relayed."""

    base: str
    prefix: str
    token: str
    hosts: frozenset[str]

    def url(self, url: str) -> str:
        """The relay address for an operator URL: same path and query, under the prefix."""
        parts = urlsplit(url)
        return urlunsplit(
            urlsplit(self.base)._replace(
                path=self.base_path + self.prefix + parts.path, query=parts.query
            )
        )

    @property
    def base_path(self) -> str:
        return urlsplit(self.base).path.rstrip("/")


def relay_route(config: OperatorConfig) -> RelayRoute | None:
    """The relay to use for this operator, or None to request its feed directly.

    Relayed only when the operator file records the owner's decision and both the relay's
    address and token are set; one without the other is a mistake worth stopping for.
    """
    relay = config.relay
    if relay is None:
        return None
    base = os.environ.get(relay.url_variable, "").strip()
    token = os.environ.get(relay.secret_name, "").strip()
    if not base and not token:
        return None
    if not base or not token:
        missing = relay.url_variable if not base else relay.secret_name
        raise FeedError(f"{config.id}: the relay needs {missing} as well")
    if urlsplit(base).scheme != "https" or not urlsplit(base).netloc:
        raise FeedError(f"{config.id}: {relay.url_variable} must be an https address")
    urls = [endpoint.url for endpoint in config.endpoints.values()]
    if config.base_url != "unknown":
        urls.append(config.base_url)
    hosts = frozenset(urlsplit(url).netloc.lower() for url in urls)
    return RelayRoute(base=base, prefix=relay.path_prefix, token=token, hosts=hosts)


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
        self._relay = relay_route(config)
        self._secrets = tuple(
            value for value in (secret, self._relay.token if self._relay else None) if value
        )
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

    def describe(self, url: str) -> str:
        """url for messages: credentials removed, and marked when it goes through the relay."""
        relayed = self._relay is not None and urlsplit(url).netloc.lower() in self._relay.hosts
        return redact_url(url) + (" (through the relay)" if relayed else "")

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
        relayed = self._relay is not None and urlsplit(url).netloc.lower() in self._relay.hosts
        headers = {}
        if relayed:
            request_url = self._relay.url(request_url)
            headers = {RELAY_TOKEN_HEADER: self._relay.token}
        via = " (through the relay)" if relayed else ""
        for attempt in range(self.max_retries + 1):
            self._refuse_if_held(timer, url)
            self._wait_turn(timer)
            self.requests_made += 1
            response = None
            try:
                response = self._client.get(request_url, headers=headers)
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
                    f"gave up on {redact_url(url)}{via} after {attempt + 1} attempts: "
                    f"{problem}{asked}"
                )
            if retry_after is None:
                timer.hold_until(now + self.backoff_seconds * 2**attempt)
        raise AssertionError("unreachable")
