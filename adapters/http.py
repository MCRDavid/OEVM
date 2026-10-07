"""A polite HTTP client for operator feeds.

- Identifies the project in the User-Agent header.
- Leaves at least `rate_limit.min_seconds_between_requests` between requests.
- Retries connection errors, timeouts, HTTP 429 and HTTP 5xx with exponential backoff,
  honouring a Retry-After header given in seconds.
- Adds the operator's key from the environment variable named by `auth.secret_name`.
  Keys never appear in URLs this module returns, logs or raises.
- Does not follow redirects, so a key can never be sent on to another site.
"""

import os
import time
from collections.abc import Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from schema.operator import OperatorConfig, is_credential_param

USER_AGENT = "OEVM/0.1 (+https://github.com/MCRDavid/OEVM)"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_WAIT_SECONDS = 600


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


def credentials_for(config: OperatorConfig) -> tuple[dict[str, str], dict[str, str]]:
    """Headers and query parameters that carry the operator's key."""
    auth = config.auth
    if auth.method == "none":
        return {}, {}
    if auth.method == "unknown" or auth.name in (None, "unknown") or not auth.secret_name:
        raise FeedError(f"{config.id}: auth details are not known yet")
    value = os.environ.get(auth.secret_name)
    if not value:
        raise FeedError(
            f"{config.id}: the environment variable {auth.secret_name} is not set. "
            "In GitHub Actions, add it as a repository secret with that name."
        )
    if auth.method == "header":
        return {auth.name: value}, {}
    return {}, {auth.name: value}


def _retry_after_seconds(response: httpx.Response) -> float | None:
    value = response.headers.get("Retry-After", "")
    return float(value) if value.strip().isdigit() else None


class PoliteClient:
    """GET requests to one operator, spaced out and retried. Use as a context manager."""

    def __init__(
        self,
        config: OperatorConfig,
        *,
        transport: httpx.BaseTransport | None = None,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        max_retries: int = 3,
        backoff_seconds: float = 5.0,
        timeout_seconds: float = 60.0,
    ):
        headers, self._auth_params = credentials_for(config)
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json", **headers},
            timeout=timeout_seconds,
            transport=transport,
            follow_redirects=False,
        )
        self.min_interval = config.rate_limit.min_seconds_between_requests
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._clock = clock
        self._last_request_at: float | None = None
        self.requests_made = 0

    def __enter__(self) -> "PoliteClient":
        return self

    def __exit__(self, *exc_info: object) -> None:
        self._client.close()

    def _wait_turn(self) -> None:
        if self._last_request_at is not None:
            remaining = self.min_interval - (self._clock() - self._last_request_at)
            if remaining > 0:
                self._sleep(remaining)
        self._last_request_at = self._clock()

    def get(self, url: str) -> httpx.Response:
        """GET url, retrying temporary failures. Raises FeedError when retries run out."""
        request_url = with_params(url, self._auth_params) if self._auth_params else url
        for attempt in range(self.max_retries + 1):
            self._wait_turn()
            self.requests_made += 1
            try:
                response = self._client.get(request_url)
            except httpx.TransportError as exc:
                problem, retry_after = type(exc).__name__, None
            else:
                if response.status_code not in RETRY_STATUSES:
                    return response
                problem, retry_after = (
                    f"HTTP {response.status_code}",
                    _retry_after_seconds(response),
                )
            if attempt == self.max_retries:
                raise FeedError(
                    f"gave up on {redact_url(url)} after {attempt + 1} attempts: {problem}"
                )
            delay = retry_after if retry_after is not None else self.backoff_seconds * 2**attempt
            self._sleep(min(delay, MAX_RETRY_WAIT_SECONDS))
        raise AssertionError("unreachable")
