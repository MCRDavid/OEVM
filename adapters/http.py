"""A polite HTTP client for operator feeds.

- Identifies the project in the User-Agent header.
- Leaves at least the operator's gap between requests, measured from when the previous
  response finished, so network delays can never squeeze two requests closer together
  at the server's end.
- Keeps one timer per host, shared by every client in the process, so operators served
  from the same host share one gap and one Retry-After. Where the owner has recorded
  limits_per_key in an operator file, that operator's gap is kept for its own key instead,
  while the host still gets one request at a time, at least SHARED_HOST_SECONDS apart, and
  any wait the server asks for holds back every key on it (ADR 0003, amended). Such
  operators may be fetched at the same time (pipeline.run): each waits for its own key's
  gap, then takes the host's turn, so their requests never overlap.
- Retries connection errors, timeouts, HTTP 429 and HTTP 5xx with exponential backoff.
- Honours every Retry-After header, in seconds or as an HTTP date, on any attempt. One
  that cannot be read is treated as a long wait. If the wait is longer than this project
  waits, nothing more is sent to that host until it has passed.
- Reads rate limit headers (RateLimit, RateLimit-*, X-RateLimit-*). When a server says no
  requests are left, nothing more is sent to that host until its reset time; a refusal
  with a reset time but no Retry-After waits for the reset (ADR 0018).
- Treats HTTP 403 part-way through a run, from a host that has already answered, as the
  server's limit rather than a block: it waits a cool-down (the server's own wait if it
  gives one), widens the gap to that host for the rest of the run and tries again, at
  most twice per request (ADR 0018). A 403 to the first request to a host is not retried.
- Adds the operator's key from the environment variable named by `auth.secret_name`,
  and only ever sends it over https. Keys never appear in URLs this module returns, logs
  or raises, and `PoliteClient.redact` removes the key from anything a server sends back.
- For an operator whose auth method is client_credentials, `PoliteClient.request_token`
  posts the client id and secret (from the variables named by `auth.client_id_secret_name`
  and `auth.secret_name`) to `auth.token_url` and sends the access token it gets back with
  every later request. The token request keeps the same gap and retries, and the id,
  secret and token are all removed from anything shown.
- Does not follow redirects, so a key can never be sent on to another site.
- Sends an operator's requests through the project's relay when the operator file
  records that decision and the relay's address and token are set in the environment.
  The relay gets the same request path and User-Agent; gaps, retries and every message
  still refer to the operator's own host and URLs. Only feeds with no key are relayed.
- Reads a feed past one expired TLS certificate only when the operator file records that
  decision (expired_certificate, ADR 0021). The chain and host name are still checked;
  only the dates are not, and a response is used only if the server presented exactly
  that certificate or one in date today. Only feeds with no key.

Timers live in memory, so they cover one run of the program. Runs that use the same host
must not be started in parallel. Within one run, pipeline.run fetches operators on
different hosts at the same time, but never two operators that share a host
(`operator_hosts`).
"""

import hashlib
import os
import re
import ssl
import threading
import time
from collections.abc import Callable, Iterable
from contextlib import nullcontext
from dataclasses import dataclass, field
from datetime import UTC, datetime
from email.utils import parsedate_to_datetime
from urllib.parse import parse_qsl, quote, quote_plus, urlencode, urlsplit, urlunsplit

import httpx

from pipeline.project import NAME, REPOSITORY_URL, VERSION
from schema.operator import (
    LIMIT_MARGIN_SECONDS,
    MIN_SECONDS_BETWEEN_REQUESTS,
    ExpiredCertificate,
    OperatorConfig,
    is_credential_param,
)

USER_AGENT = f"{NAME}/{VERSION} (+{REPOSITORY_URL})"
RETRY_STATUSES = frozenset({429, 500, 502, 503, 504})
MAX_RETRY_WAIT_SECONDS = 600
# Between any two requests to a host whose operators' limits the owner reads per key
# (limits_per_key): the project floor plus the margin, whichever key each request uses.
SHARED_HOST_SECONDS = MIN_SECONDS_BETWEEN_REQUESTS + LIMIT_MARGIN_SECONDS
UNREADABLE_RETRY_AFTER_SECONDS = 3600
# A refusal (HTTP 403) part-way through a run: wait this long when the server does not say,
# then go on with the gap to that host this many times wider (ADR 0018).
REFUSAL_STATUS = 403
REFUSAL_COOL_DOWN_SECONDS = 300
REFUSAL_SLOW_DOWN = 1.5
MAX_REFUSAL_RETRIES = 2
# A reset time this large is a Unix time, not a number of seconds.
EPOCH_THRESHOLD = 1_000_000_000
REDACTED = "REDACTED"


class FeedError(Exception):
    """A feed could not be fetched, or did not return valid data.

    partial, when set, holds what one module fetched before the error
    (adapters.ocpi_221.client.ModuleFetch); modules, when set, every module so far.
    """

    partial = None
    modules: dict | None = None


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


def client_id_value(config: OperatorConfig, key: str | None = None) -> str | None:
    """The client id for an operator whose auth method is client_credentials, else None.

    Read from the environment variable named by auth.client_id_secret_name, unless `key` is
    given (fixture replays and tests only).
    """
    name = config.auth.client_id_secret_name
    if config.auth.method != "client_credentials" or not name:
        return None
    value = key or os.environ.get(name)
    if not value:
        raise FeedError(
            f"{config.id}: the environment variable {name} is not set. "
            "In GitHub Actions, add it as a repository secret with that name."
        )
    return value


def credentials_for(
    config: OperatorConfig, key: str | None = None
) -> tuple[dict[str, str], dict[str, str]]:
    """Headers and query parameters that carry the operator's key.

    None for client_credentials: its header carries an access token, added once
    PoliteClient.request_token has one.
    """
    value = secret_value(config, key)
    if value is None or config.auth.method == "client_credentials":
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


def _header_number(value: str | None) -> float | None:
    if value is None:
        return None
    value = value.strip()
    return float(value) if re.fullmatch(r"[0-9]+(\.[0-9]+)?", value) else None


def _structured_param(value: str, names: tuple[str, ...]) -> float | None:
    for name in names:
        match = re.search(rf"(?:^|[,;\s]){name}=([0-9]+)", value)
        if match:
            return float(match.group(1))
    return None


def rate_limit_state(response: httpx.Response, now: datetime) -> tuple[float | None, float | None]:
    """(requests remaining, seconds until the allowance resets), each None if not stated.

    Reads the IETF RateLimit header in both draft forms ("remaining=0, reset=30" and
    '"default";r=0;t=30') and the common RateLimit-*, X-RateLimit-* and X-Rate-Limit-*
    headers. A reset given as a Unix time is turned into seconds from now.
    """
    headers = response.headers
    remaining = reset = None
    structured = headers.get("RateLimit")
    if structured:
        remaining = _structured_param(structured, ("remaining", "r"))
        reset = _structured_param(structured, ("reset", "t"))
    for prefix in ("RateLimit-", "X-RateLimit-", "X-Rate-Limit-"):
        if remaining is None:
            remaining = _header_number(headers.get(prefix + "Remaining"))
        if reset is None:
            reset = _header_number(headers.get(prefix + "Reset"))
    if reset is not None and reset >= EPOCH_THRESHOLD:
        reset = max(0.0, reset - now.timestamp())
    return remaining, reset


def server_hint(response: httpx.Response) -> str:
    """A short note on who answered, for error messages: the Server header, where a
    redirect points (never followed, so a key is never sent on) and any limits."""
    parts = []
    server = re.sub(r"[^A-Za-z0-9 ./_()-]", "", response.headers.get("Server", ""))[:40]
    if server.strip():
        parts.append(f"server {server.strip()}")
    if response.is_redirect:
        target = redact_url(response.headers["Location"])
        parts.append("redirect to " + re.sub(r"[^A-Za-z0-9:/?&=%._~+-]", "", target)[:120])
    names = sorted(name for name in response.headers if "ratelimit" in name.replace("-", ""))
    if names:
        parts.append("rate limit headers " + ", ".join(names))
    return f" ({'; '.join(parts)})" if parts else ""


@dataclass
class HostTimer:
    """When the last request to one host finished, and the earliest the next may start.

    slow_down widens the gap after the host refused a request part-way through a run;
    answered says the host has answered at least once in this run. turn is held from the
    wait before a request until its answer has been read, so clients that share the
    timer from different threads send one request at a time.
    """

    last_finished_at: float | None = None
    not_before: float | None = None
    slow_down: float = 1.0
    answered: bool = False
    turn: threading.Lock = field(default_factory=threading.Lock, repr=False, compare=False)

    def hold_until(self, moment: float) -> None:
        self.not_before = moment if self.not_before is None else max(self.not_before, moment)


_HOST_TIMERS: dict[str, HostTimer] = {}
_HOST_TIMERS_LOCK = threading.Lock()


def host_timer(url: str, key_name: str | None = None) -> HostTimer:
    """The timer for url's host, or for one key on it when key_name (a secret's name) is
    given, for an operator whose limits the owner reads per key."""
    host = urlsplit(url).netloc.lower()
    with _HOST_TIMERS_LOCK:
        return _HOST_TIMERS.setdefault(f"{host} {key_name}" if key_name else host, HostTimer())


def reset_host_timers() -> None:
    """Forget every timer. Tests call this because each test has its own fake clock."""
    with _HOST_TIMERS_LOCK:
        _HOST_TIMERS.clear()


# Stands for the project's relay in operator_hosts: relayed operators all go through the
# one relay Worker, so they are treated as sharing a host and fetched one at a time.
RELAY_HOST = "relay"


def operator_hosts(config: OperatorConfig) -> frozenset[str]:
    """Every host this operator's requests can reach: its feed URLs, token URL and relay.

    Paging never leaves an endpoint's host (adapters.ocpi_221.client). An operator with no
    known host gets the empty name, so all such operators count as sharing one host.
    """
    urls = config.feed_urls()
    if config.auth.token_url:
        urls.append(config.auth.token_url)
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
    hosts = frozenset(urlsplit(url).netloc.lower() for url in config.feed_urls())
    return RelayRoute(base=base, prefix=relay.path_prefix, token=token, hosts=hosts)


# OpenSSL's X509_V_FLAG_NO_CHECK_TIME: check a certificate chain without checking dates.
# Python's ssl module has no name for it but passes the flag on to OpenSSL as given.
NO_CHECK_TIME = 0x200000


def expired_certificate_context() -> ssl.SSLContext:
    """httpx's usual TLS settings, except that certificate dates are not checked.

    The chain must still lead to a trusted authority and the certificate must still name
    the host. Only for an operator whose file records expired_certificate; the client then
    checks which certificate the server presented (certificate_problem).
    """
    context = httpx.create_ssl_context()
    context.verify_flags |= NO_CHECK_TIME
    if context.verify_mode != ssl.CERT_REQUIRED or not context.check_hostname:
        raise FeedError("TLS checks are not on; refusing to relax only the dates")
    return context


def certificate_fingerprint(der: bytes) -> str:
    """SHA-256 fingerprint of a DER certificate, as '49:82:...' in capitals."""
    digest = hashlib.sha256(der).hexdigest().upper()
    return ":".join(digest[i : i + 2] for i in range(0, len(digest), 2))


def certificate_problem(
    der: bytes | None, details: dict, decision: ExpiredCertificate, now: datetime
) -> tuple[str | None, bool]:
    """(problem, renewed) for the certificate a server presented, under the owner's
    decision to accept one expired certificate.

    problem is None when the response may be used: the certificate is exactly the one the
    decision names, or it is in date now (then renewed is True, and the decision can be
    removed). details is the certificate as Python's ssl module decodes it.
    """
    if not der:
        return "the server presented no certificate", False
    fingerprint = certificate_fingerprint(der)
    if fingerprint == decision.sha256:
        return None, False
    try:
        starts = ssl.cert_time_to_seconds(details["notBefore"])
        ends = ssl.cert_time_to_seconds(details["notAfter"])
    except (KeyError, TypeError, ValueError):
        return f"certificate {fingerprint} has no readable dates", False
    if starts <= now.timestamp() <= ends:
        return None, True
    return (
        f"certificate {fingerprint} is not in date and is not the one the operator file accepts",
        False,
    )


def required_gap(config: OperatorConfig) -> float:
    """The gap the client keeps: never less than the floor or what any limit needs."""
    rate = config.rate_limit
    return max(
        MIN_SECONDS_BETWEEN_REQUESTS,
        rate.min_seconds_between_requests,
        *(limit.min_interval + LIMIT_MARGIN_SECONDS for limit in rate.limits),
    )


class PoliteClient:
    """Requests to one operator, spaced out and retried. Use as a context manager."""

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
        notice: Callable[[str], None] = lambda _text: None,
    ):
        headers, self._auth_params = credentials_for(config, key)
        secret = secret_value(config, key)
        client_id = client_id_value(config, key)
        self._auth = config.auth
        self._client_credentials = (client_id, secret) if client_id else None
        self._relay = relay_route(config)
        self._secrets = tuple(
            value
            for value in (client_id, secret, self._relay.token if self._relay else None)
            if value
        )
        # The owner's decision to read past one expired certificate (ADR 0021). The
        # validator keeps every URL of such an operator on that one host.
        self._expired_certificate = config.expired_certificate
        self._own_transport = transport is None
        self._client = httpx.Client(
            headers={"User-Agent": USER_AGENT, "Accept": "application/json", **headers},
            timeout=timeout_seconds,
            transport=transport,
            follow_redirects=False,
            verify=(
                expired_certificate_context() if self._expired_certificate is not None else True
            ),
        )
        self.min_interval = required_gap(config)
        # The owner's decision to read the limits per key: the gap is kept for this key.
        self._key_name = (
            config.auth.secret_name
            if config.limits_per_key is not None and config.auth.method != "none"
            else None
        )
        self.max_retries = max_retries
        self.backoff_seconds = backoff_seconds
        self._sleep = sleep
        self._clock = clock
        self._wall_clock = wall_clock
        self.requests_made = 0
        self._notice = notice
        # What the client did about refusals and limits, for the run's logged problems.
        self.events: list[str] = []

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

    def _wait_turn(self, timer: HostTimer, host: HostTimer | None) -> None:
        """Wait for this client's gap, and with a per-key timer also for the host's."""
        now = self._clock()
        ready = now
        if timer.last_finished_at is not None:
            ready = max(ready, timer.last_finished_at + self.min_interval * timer.slow_down)
        if timer.not_before is not None:
            ready = max(ready, timer.not_before)
        if host is not None:
            if host.last_finished_at is not None:
                ready = max(ready, host.last_finished_at + SHARED_HOST_SECONDS)
            if host.not_before is not None:
                ready = max(ready, host.not_before)
        if ready > now:
            self._sleep(ready - now)

    def _check_certificate(self, response: httpx.Response, url: str) -> None:
        """Stop unless the server presented the one expired certificate the operator file
        accepts, or one in date today. Called before the body is read."""
        decision = self._expired_certificate
        stream = response.extensions.get("network_stream")
        if stream is None and not self._own_transport:
            return  # a recorded or test response: there was no TLS connection
        tls = stream.get_extra_info("ssl_object") if stream is not None else None
        if tls is None:
            raise FeedError(f"could not read the TLS certificate for {redact_url(url)}")
        problem, renewed = certificate_problem(
            tls.getpeercert(True), tls.getpeercert() or {}, decision, self._wall_clock()
        )
        if problem is not None:
            raise FeedError(f"{redact_url(url)}: {problem}; not using the response")
        if renewed:
            event = (
                f"{decision.host} now presents a certificate that is in date; the "
                "expired_certificate decision in the operator file can be removed"
            )
            if event not in self.events:
                self.events.append(event)
                self._notice(event)

    def _send(
        self, method: str, url: str, headers: dict[str, str], body: dict | None
    ) -> httpx.Response:
        if self._expired_certificate is None:
            return self._client.request(method, url, headers=headers, json=body)
        with self._client.stream(method, url, headers=headers, json=body) as response:
            self._check_certificate(response, url)
            response.read()
        return response

    def get(self, url: str, *, return_at_once: frozenset[int] = frozenset()) -> httpx.Response:
        """GET url, retrying temporary failures. Raises FeedError when retries run out.

        An answer whose status is in return_at_once is returned without retrying, for an
        adapter that handles that error itself.
        """
        return self._request("GET", url, return_at_once=return_at_once)

    def request_token(self, *, id_field: str, secret_field: str, token_field: str) -> None:
        """Exchange the client id and secret for an access token (client_credentials).

        POSTs {id_field: id, secret_field: secret} as JSON to auth.token_url and sends the
        reply's token_field, after auth.scheme, in the header auth.name with every later
        request. Raises FeedError if there is no token.
        """
        if self._client_credentials is None or not self._auth.token_url:
            raise FeedError("this operator's auth method is not client_credentials")
        url = self._auth.token_url
        client_id, secret = self._client_credentials
        response = self._request("POST", url, body={id_field: client_id, secret_field: secret})
        if response.status_code not in (200, 201):
            raise FeedError(
                f"the token request to {redact_url(url)} answered HTTP {response.status_code}"
            )
        try:
            token = response.json().get(token_field)
        except (AttributeError, ValueError):
            token = None
        if not isinstance(token, str) or not token.strip():
            raise FeedError(f"the token request to {redact_url(url)} returned no {token_field}")
        self._secrets = (*self._secrets, token)
        scheme = self._auth.scheme
        self._client.headers[self._auth.name] = f"{scheme} {token}" if scheme else token

    def _request(
        self,
        method: str,
        url: str,
        *,
        body: dict | None = None,
        return_at_once: frozenset[int] = frozenset(),
    ) -> httpx.Response:
        if self._secrets and urlsplit(url).scheme != "https":
            raise FeedError(f"not sending a key over plain http: {redact_url(url)}")
        timer = host_timer(url, self._key_name)
        # With a per-key timer, the host's own timer keeps one request at a time to the
        # host, SHARED_HOST_SECONDS apart, and every wait the server asks for.
        host = host_timer(url) if self._key_name else None
        timers = (timer,) if host is None else (timer, host)

        def hold_until(moment: float) -> None:
            for each in timers:
                each.hold_until(moment)

        request_url = with_params(url, self._auth_params) if self._auth_params else url
        relayed = self._relay is not None and urlsplit(url).netloc.lower() in self._relay.hosts
        headers = {}
        if relayed:
            request_url = self._relay.url(request_url)
            headers = {RELAY_TOKEN_HEADER: self._relay.token}
        via = " (through the relay)" if relayed else ""
        attempt = refusals = 0
        while True:
            for each in timers:
                self._refuse_if_held(each, url)
            if host is not None:
                # This key's own gap first, so a key that is waiting never holds the host.
                self._wait_turn(timer, None)
            # The host's turn, for clients of keys on one host fetched at the same time:
            # held until the answer, and any wait it asks for, has been recorded.
            with host.turn if host is not None else nullcontext():
                if host is not None:
                    self._refuse_if_held(host, url)
                self._wait_turn(timer, host)
                self.requests_made += 1
                response = None
                try:
                    response = self._send(method, request_url, headers, body)
                except httpx.TransportError as exc:
                    problem, retry_after = type(exc).__name__, None
                finally:
                    timer.last_finished_at = self._clock()
                    if host is not None:
                        host.last_finished_at = timer.last_finished_at
                now = timer.last_finished_at
                if response is not None:
                    wall = self._wall_clock()
                    remaining, reset = rate_limit_state(response, wall)
                    if remaining == 0 and reset is not None:
                        hold_until(now + reset + LIMIT_MARGIN_SECONDS)
                    retry_after = retry_after_seconds(response, wall)
                    if retry_after is None and response.status_code >= 400 and reset is not None:
                        retry_after = reset + LIMIT_MARGIN_SECONDS
                    status = response.status_code
                    if (
                        status == REFUSAL_STATUS
                        and timer.answered
                        and refusals < MAX_REFUSAL_RETRIES
                    ):
                        refusals += 1
                        wait = REFUSAL_COOL_DOWN_SECONDS if retry_after is None else retry_after
                        hold_until(now + wait)
                        timer.slow_down *= REFUSAL_SLOW_DOWN
                        gap = self.min_interval * timer.slow_down
                        event = (
                            f"refused {redact_url(url)}{via} with HTTP 403 part-way through; "
                            f"waited {wait:g} s and went on with {gap:g} s between requests"
                        )
                        self.events.append(event)
                        self._notice(event)
                        continue
                    if status not in RETRY_STATUSES or status in return_at_once:
                        if status < 400:
                            timer.answered = True
                        return response
                    problem = f"HTTP {status}"

                if retry_after is not None:
                    hold_until(now + retry_after)
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
                    hold_until(now + self.backoff_seconds * 2**attempt)
                attempt += 1
