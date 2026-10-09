"""Model for one operator registry file (operators/<id>.yaml).

Each file records how to reach one operator's open data and what this project
knows about getting access to it. Anything not yet known is written as
"unknown" or "needs_testing" rather than guessed.

Never put a key, token or password in a registry file. Keys live in GitHub
Actions secrets, and the file gives only the secret's name in auth.secret_name.
URLs that carry credentials are rejected.
"""

import datetime as dt
import re
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

Unknown = Literal["unknown"]
Support = Literal["supported", "not_supported", "needs_testing", "unknown"]
AdapterName = Literal[
    "ocpi_221", "eco_movement_pcpr", "gridserve", "static_file", "custom", "unknown"
]
AuthMethod = Literal["none", "header", "query_param", "unknown"]
EndpointKind = Literal["versions", "locations", "tariffs", "statuses", "download"]
EndpointStatus = Literal["documented", "needs_testing"]
ResponseEnvelope = Literal["ocpi", "data_list"]
FindingKind = Literal["spec_conformance", "data_quality", "access", "documentation"]
FindingStatus = Literal["open", "resolved"]
EngagementStatus = Literal[
    "open_anonymous",
    "open_shared_key",
    "key_on_request",
    "signed_agreement_required",
    "requested_no_reply",
    "requested_awaiting_decision",
    "request_declined",
    "no_public_feed_found",
    "possibly_out_of_scope",
    "unknown",
]

# Neutral wording for the engagement status page (blueprint section 3).
ENGAGEMENT_LABELS: dict[str, str] = {
    "open_anonymous": "Open, no registration",
    "open_shared_key": "Open, published shared key",
    "key_on_request": "Key issued on request",
    "signed_agreement_required": "Signed agreement required",
    "requested_no_reply": "Requested, no reply",
    "requested_awaiting_decision": "Requested, awaiting a decision",
    "request_declined": "Request declined",
    "no_public_feed_found": "No public feed found",
    "possibly_out_of_scope": "Possibly out of scope",
    "unknown": "Not yet established",
}

EngagementAction = Literal[
    "page_checked",
    "feed_searched",
    "request_sent",
    "follow_up_sent",
    "reply_received",
    "agreement_offered",
    "key_granted",
    "request_declined",
]
Channel = Literal["web_form", "email", "support_ticket", "post", "other"]

# Neutral wording for each step in the engagement log.
ENGAGEMENT_ACTIONS: dict[str, str] = {
    "page_checked": "Operator's page checked",
    "feed_searched": "Searched for a feed",
    "request_sent": "Access requested",
    "follow_up_sent": "Follow-up sent",
    "reply_received": "Reply received",
    "agreement_offered": "Agreement offered",
    "key_granted": "Key issued",
    "request_declined": "Request declined",
}
CHANNELS: dict[str, str] = {
    "web_form": "Web form",
    "email": "Email",
    "support_ticket": "Support ticket",
    "post": "Post",
    "other": "Other",
}
# Steps that answer a request. A request counts as unanswered until one of these follows it.
RESPONSES = frozenset({"reply_received", "agreement_offered", "key_granted", "request_declined"})
# Steps this project takes towards an operator, so they must say how they were sent.
SENT = frozenset({"request_sent", "follow_up_sent"})

# Source ids used for gap-filler data, so no operator may take them.
RESERVED_IDS = frozenset({"osm", "ocm", "reports", "unknown"})

# Project policy: never more than one request per second to any operator, whatever
# the operator allows. Operators' own published limits are enforced on top of this.
MIN_SECONDS_BETWEEN_REQUESTS = 1.0
# Extra gap on top of what a published limit needs, so a server counting with inclusive
# windows, or a slightly different clock, still never sees one request too many.
LIMIT_MARGIN_SECONDS = 1.0

# Published text must stay neutral (blueprint section 3): dated facts, no accusations.
# This list is a coarse safety net, not a substitute for careful wording.
_ACCUSATORY = re.compile(
    r"illegal|unlawful|breach|break(s|ing)? the law|broke the law|violat|contraven|"
    r"non-?compliant|not compliant|fail(s|ed|ing)? to comply|offence|fraud|scam|shame",
    re.IGNORECASE,
)


def neutral_text(text: str) -> str:
    """Reject wording that accuses anyone of breaking the law or of bad faith."""
    match = _ACCUSATORY.search(text)
    if match:
        raise ValueError(
            f"wording must stay neutral and factual; avoid {match.group(0)!r}. Describe what "
            "was observed and when, not whether anyone broke a rule"
        )
    return text


NeutralText = Annotated[str, Field(min_length=1), AfterValidator(neutral_text)]

_EMAIL_ADDRESS = re.compile(r"[^\s@<>()]+@[^\s@<>()]+\.[A-Za-z]{2,}")


def no_email_address(text: str) -> str:
    """Reject email addresses, so the log never publishes anyone's contact details."""
    if _EMAIL_ADDRESS.search(text):
        raise ValueError(
            "remove the email address: the engagement log is public and holds no contact "
            "details. Describe the channel instead, for example 'the open data address'"
        )
    return text


LogText = Annotated[NeutralText, AfterValidator(no_email_address)]
EvidenceFile = Annotated[
    str,
    Field(
        pattern=r"^evidence/[a-z0-9_]+/[^/].*$",
        description="Path of a saved copy under evidence/<operator id>/. No personal names "
        "or email addresses.",
    ),
]

_CREDENTIAL_PARAM = re.compile(
    r"key|token|secret|passw|pwd|signature|auth|credential", re.IGNORECASE
)


def is_credential_param(name: str) -> bool:
    """True if a query parameter name looks like it carries a key, token or password."""
    return bool(_CREDENTIAL_PARAM.search(name))


def _reject_credentials_in_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.username or parts.password:
        raise ValueError("URL must not contain a username or password")
    for name, _ in parse_qsl(parts.query, keep_blank_values=True):
        if is_credential_param(name):
            raise ValueError(
                f"URL query parameter {name!r} looks like a credential. Remove it, store the "
                "key as a GitHub Actions secret and give its name in auth.secret_name"
            )
    return url


SafeUrl = Annotated[
    str, Field(pattern=r"^https?://\S+$"), AfterValidator(_reject_credentials_in_url)
]


def _reject_reserved_secret_prefix(name: str) -> str:
    if name.startswith("GITHUB_"):
        raise ValueError("GitHub does not allow secret names starting with GITHUB_")
    return name


SecretName = Annotated[
    str,
    Field(
        pattern=r"^[A-Z][A-Z0-9_]*$",
        description="NAME of the GitHub Actions secret that holds the key, for example "
        "'JOLT_API_KEY'. Never the key itself.",
    ),
    AfterValidator(_reject_reserved_secret_prefix),
]


class _Model(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Auth(_Model):
    method: AuthMethod
    name: str | None = Field(
        default=None,
        description="Header or query parameter that carries the key, for example "
        "'ec-subscription-key' or 'apiKey'. Write 'unknown' if not yet known.",
    )
    secret_name: SecretName | None = None
    scheme: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z][A-Za-z0-9-]*$",
        description="Word sent before the key in a header, such as 'Token' for "
        "'Authorization: Token <key>'. Null if the header holds only the key.",
    )

    @model_validator(mode="after")
    def _check(self) -> "Auth":
        if self.scheme is not None and self.method != "header":
            raise ValueError("scheme only applies when method is 'header'")
        if self.method == "none":
            if self.name is not None or self.secret_name is not None:
                raise ValueError("name and secret_name must be null when method is 'none'")
        elif self.method in ("header", "query_param"):
            if not self.name:
                raise ValueError(f"name is required when method is {self.method!r}")
            if not self.secret_name:
                raise ValueError(f"secret_name is required when method is {self.method!r}")
        return self


class DocumentedLimit(_Model):
    """One rate limit an operator, or the host serving its data, publishes."""

    publisher: str = Field(
        min_length=1,
        description="Who publishes the limit: the operator, or the company hosting its data, "
        "for example 'Eco-Movement'.",
    )
    requests: int = Field(gt=0, description="How many requests are allowed per window.")
    per_seconds: float = Field(gt=0, description="Length of the window in seconds.")
    endpoint: EndpointKind | Literal["all"] = Field(
        default="all", description="The endpoint the limit applies to, or 'all'."
    )
    scope: str | None = Field(
        default=None,
        description="Narrower scope within the endpoint, for example 'single location'.",
    )
    quote: str = Field(min_length=1, description="The operator's own wording, quoted exactly.")
    source_url: SafeUrl
    checked: dt.date | Unknown = Field(
        description="Date the wording was last read at source_url (YYYY-MM-DD), or 'unknown'."
    )

    @property
    def min_interval(self) -> float:
        """The shortest gap between requests that keeps within this limit."""
        return self.per_seconds / self.requests


class RateLimit(_Model):
    min_seconds_between_requests: float = Field(
        default=2,
        ge=MIN_SECONDS_BETWEEN_REQUESTS,
        description="Gap this project leaves between any two requests to the operator's "
        "host, retries included. At least 1 second, and at least 1 second more than every "
        "documented limit needs.",
    )
    limits: list[DocumentedLimit] = Field(
        default_factory=list, description="Limits the operator publishes. Empty if none."
    )
    limits_checked: dt.date | Unknown = Field(
        default="unknown",
        description="Date the operator's pages were last checked for rate limits. With no "
        "limits listed, a date here means none were stated.",
    )
    notes: str | None = Field(default=None, description="Anything else about request rates.")

    @model_validator(mode="after")
    def _within_documented_limits(self) -> "RateLimit":
        for limit in self.limits:
            needed = limit.min_interval + LIMIT_MARGIN_SECONDS
            if self.min_seconds_between_requests < needed:
                raise ValueError(
                    f"min_seconds_between_requests ({self.min_seconds_between_requests:g} s) "
                    f"would break the documented limit of {limit.requests} requests per "
                    f"{limit.per_seconds:g} seconds for {limit.endpoint}, which needs at least "
                    f"{needed:g} s between requests ({limit.min_interval:g} s plus a "
                    f"{LIMIT_MARGIN_SECONDS:g} s safety margin)"
                )
        return self


class Finding(_Model):
    """Something observed about a source: a spec difference, a data quirk or an access issue."""

    date: dt.date = Field(description="Date it was observed (YYYY-MM-DD).")
    kind: FindingKind
    summary: NeutralText = Field(description="One neutral, factual sentence.")
    handling: NeutralText | None = Field(
        default=None, description="What this project does about it."
    )
    evidence_url: SafeUrl | None = None
    status: FindingStatus = "open"
    resolved_date: dt.date | None = None

    @model_validator(mode="after")
    def _check(self) -> "Finding":
        if self.status == "resolved" and self.resolved_date is None:
            raise ValueError("a resolved finding needs resolved_date")
        if self.status == "open" and self.resolved_date is not None:
            raise ValueError("an open finding cannot have resolved_date")
        if self.resolved_date is not None and self.resolved_date < self.date:
            raise ValueError("resolved_date is earlier than date")
        return self


class Endpoint(_Model):
    url: SafeUrl
    status: EndpointStatus = Field(
        description="'documented' if the operator or its host documents this URL, "
        "otherwise 'needs_testing'."
    )
    note: str | None = None


class Source(_Model):
    url: SafeUrl
    note: str | None = None


class Evidence(_Model):
    date: dt.date | Unknown = Field(
        description="Date the evidence was checked (YYYY-MM-DD), or 'unknown'."
    )
    url: SafeUrl | None = None
    file: EvidenceFile | None = None
    note: NeutralText | None = None

    @model_validator(mode="after")
    def _check(self) -> "Evidence":
        if self.url is None and self.file is None:
            raise ValueError("evidence needs a url or a file")
        return self


class Licence(_Model):
    name: str = Field(
        min_length=1,
        description="Licence the data is used under, for example 'OGL-3.0', or 'unknown'.",
    )
    url: SafeUrl | None = Field(default=None, description="Link to the licence text.")
    basis: NeutralText = Field(
        description="Why this licence applies, in plain words, and what the operator's own "
        "pages say about terms.",
    )
    checked: dt.date | Unknown = Field(
        description="Date the operator's own terms were last checked (YYYY-MM-DD), or 'unknown'."
    )


class MissingPublishFlag(_Model):
    """The repository owner's recorded decision to show locations that have no publish flag.

    OCPI 2.2.1 requires every location to have a publish flag, and a location with publish
    set to false may not be shown on a website or app. Without this decision, locations
    with no flag are never kept. A flag set to false is always respected, whatever is
    recorded here.
    """

    decided: dt.date = Field(description="Date the owner made the decision (YYYY-MM-DD).")
    basis: NeutralText = Field(
        description="Why locations with no flag may be shown, for example that the operator "
        "publishes the feed itself as open data under the regulations.",
    )
    evidence_url: SafeUrl = Field(description="Where the operator says the data is public.")


class SwappedCoordinates(_Model):
    """The repository owner's recorded decision to correct obviously wrong coordinates.

    Two mistakes are corrected (ADR 0013). A swap: the published point is outside the UK,
    the same numbers the other way round fall inside the UK, the country is GBR and the
    postcode is a UK postcode. A missing minus sign: the published longitude is positive
    and outside the UK, the same point west of the Greenwich meridian is on the UK's land
    or within 2 km of its coast, the country is GBR and the postcode is a UK postcode or
    none is given. The published point is kept with the location, the map says it was
    corrected, and the operator's findings record it. Without this decision such locations
    are left off the map.
    """

    decided: dt.date = Field(description="Date the owner made the decision (YYYY-MM-DD).")
    basis: NeutralText = Field(description="Why obviously wrong coordinates may be corrected.")


# OCPI 2.2.1 EVSE statuses, which a non-standard reading can never replace.
OCPI_EVSE_STATUSES = frozenset(
    {"AVAILABLE", "BLOCKED", "CHARGING", "INOPERATIVE", "OUTOFORDER", "PLANNED", "REMOVED"}
    | {"RESERVED", "UNKNOWN"}
)


class NonstandardStatuses(_Model):
    """The repository owner's recorded decision on how EVSE statuses that are not OCPI
    2.2.1 values are shown.

    Without this decision such statuses are recorded as unknown. A value may only be read
    as "working" (in service, free or in use not stated) or "out_of_order", so a
    non-standard value is never shown as available or in use.
    """

    decided: dt.date = Field(description="Date the owner made the decision (YYYY-MM-DD).")
    basis: NeutralText = Field(description="Why the values may be read this way.")
    evidence_url: SafeUrl = Field(description="Where the values can be seen in the feed.")
    statuses: dict[str, Literal["working", "out_of_order"]] = Field(
        min_length=1, description="Each value as the feed sends it, and how it is shown."
    )

    @model_validator(mode="after")
    def _not_ocpi(self) -> "NonstandardStatuses":
        for value in self.statuses:
            if value.upper() in OCPI_EVSE_STATUSES:
                raise ValueError(f"{value!r} is an OCPI 2.2.1 status and is read as such")
        return self


class Relay(_Model):
    """The repository owner's recorded decision to fetch this operator through a relay the
    project runs, because the operator's server refused requests from the daily run.

    The relay (relay/worker.js, on Cloudflare Workers) forwards only this operator's own
    feed paths, unchanged, with the project's User-Agent, and the operator's rate limits
    still apply. Records keep the operator's own URLs as their source. Only feeds that need
    no key may be relayed, so no key ever passes through it.
    """

    decided: dt.date = Field(description="Date the owner made the decision (YYYY-MM-DD).")
    reason: NeutralText = Field(description="Why direct requests cannot be used.")
    evidence_url: SafeUrl = Field(description="Where the refusal can be seen, such as a run log.")
    url_variable: SecretName = Field(
        description="Environment variable (a GitHub Actions secret, so it is masked in logs) "
        "holding the relay's https address. Requests go direct only when neither this nor "
        "secret_name is set; one without the other stops the operator's fetch."
    )
    secret_name: SecretName = Field(
        description="Environment variable (a GitHub Actions secret) holding the relay's "
        "access token."
    )
    path_prefix: str = Field(
        pattern=r"^/[a-z0-9-]+$",
        description="The relay path for this operator, for example /geniepoint.",
    )


class EngagementEvent(_Model):
    """One dated step in getting access to an operator's data: a check, a request, a reply."""

    date: dt.date = Field(description="Date of the step (YYYY-MM-DD).")
    action: EngagementAction
    channel: Channel | None = Field(
        default=None,
        description="How a request or follow-up was sent, or how a reply came. Required for "
        "request_sent and follow_up_sent.",
    )
    summary: LogText = Field(
        description="One neutral, factual sentence. No personal names or email addresses."
    )
    quote: LogText | None = Field(
        default=None,
        description="The operator's own words, quoted exactly, with any personal names and "
        "contact details left out. Required for request_declined.",
    )
    evidence_url: SafeUrl | None = None
    evidence_file: EvidenceFile | None = None

    @model_validator(mode="after")
    def _check(self) -> "EngagementEvent":
        if self.action in SENT and self.channel is None:
            raise ValueError(f"{self.action} needs a channel")
        if self.action == "request_declined" and self.quote is None:
            raise ValueError("request_declined needs the operator's words in quote")
        if self.action in RESPONSES and self.evidence_url is None and self.evidence_file is None:
            raise ValueError(
                f"{self.action} needs evidence_url or evidence_file, such as a copy of the "
                "reply saved under evidence/<operator id>/ with names and addresses removed"
            )
        return self


class Engagement(_Model):
    status: EngagementStatus
    evidence: list[Evidence] = Field(default_factory=list)
    log: list[EngagementEvent] = Field(
        default_factory=list,
        description="Dated steps taken to reach the data, oldest first. Shown on the "
        "transparency page.",
    )

    @property
    def as_of(self) -> dt.date | None:
        """Date of the latest evidence or log entry: the date the status was last confirmed."""
        dates = [e.date for e in self.evidence if isinstance(e.date, dt.date)]
        dates += [event.date for event in self.log]
        return max(dates, default=None)

    def _last_sent_index(self) -> int | None:
        return next(
            (i for i in range(len(self.log) - 1, -1, -1) if self.log[i].action in SENT), None
        )

    def last_sent(self) -> EngagementEvent | None:
        """The latest request or follow-up, if any."""
        index = self._last_sent_index()
        return None if index is None else self.log[index]

    def last_response(self) -> EngagementEvent | None:
        """The operator's latest reply, agreement, key or refusal, if any."""
        return next((e for e in reversed(self.log) if e.action in RESPONSES), None)

    def awaiting_reply(self) -> bool:
        """True if the latest request or follow-up has had no response since."""
        index = self._last_sent_index()
        if index is None:
            return False
        return not any(e.action in RESPONSES for e in self.log[index + 1 :])

    @model_validator(mode="after")
    def _check(self) -> "Engagement":
        if self.status != "unknown" and not self.evidence and not self.log:
            raise ValueError(
                f"status {self.status!r} needs at least one evidence entry or log entry"
            )
        dates = [event.date for event in self.log]
        if dates != sorted(dates):
            raise ValueError("engagement.log must be in date order, oldest first")
        actions = {event.action for event in self.log}
        requested = self.status in ("requested_no_reply", "requested_awaiting_decision")
        if requested and "request_sent" not in actions:
            raise ValueError(f"status {self.status!r} needs a request_sent entry in the log")
        if self.status == "requested_no_reply" and self.last_response() is not None:
            raise ValueError(
                "status 'requested_no_reply' does not match the log: a response from the "
                "operator is recorded. Use 'requested_awaiting_decision' or the status the "
                "response gives"
            )
        if self.status == "request_declined" and "request_declined" not in actions:
            raise ValueError("status 'request_declined' needs a request_declined entry in the log")
        return self


class OperatorConfig(_Model):
    id: str = Field(pattern=r"^[a-z0-9_]+$", description="Must match the file name.")
    display_name: str = Field(min_length=1)
    ocpi_country_code: str = Field(pattern=r"^([A-Z]{2}|unknown)$")
    ocpi_party_id: str = Field(pattern=r"^([A-Z0-9]{3}|unknown)$")
    adapter: AdapterName
    base_url: SafeUrl | Unknown
    endpoints: dict[EndpointKind, Endpoint] = Field(
        default_factory=dict,
        description="Specific URLs, recorded only where the source of the URL is known.",
    )
    response_envelope: ResponseEnvelope = Field(
        default="ocpi",
        description="'ocpi' (the default) requires each response to be an OCPI 2.2.1 "
        "response object with a status_code. 'data_list' also accepts an object with a "
        "list of OCPI records in 'data' and no status_code, for feeds whose records are OCPI "
        "but whose wrapper is not. Record the reason as a finding. ocpi_221 only.",
    )
    auth: Auth
    rate_limit: RateLimit = Field(default_factory=RateLimit)
    supports_single_location: Support
    cors: Support
    attribution: str | None = Field(
        default=None, description="Attribution statement shown with this operator's data."
    )
    licence: Licence | None = Field(
        default=None, description="Licence terms for this operator's data. Null if not yet known."
    )
    missing_publish_flag: MissingPublishFlag | None = Field(
        default=None,
        description="Only by the repository owner's decision: show locations that have no "
        "publish flag. Null means such locations are never kept.",
    )
    swapped_coordinates: SwappedCoordinates | None = Field(
        default=None,
        description="Only by the repository owner's decision: correct coordinates that are "
        "obviously the wrong way round. Null means such locations are left off the map.",
    )
    nonstandard_statuses: NonstandardStatuses | None = Field(
        default=None,
        description="Only by the repository owner's decision: how EVSE statuses that are not "
        "OCPI 2.2.1 values are shown. Null means they are recorded as unknown.",
    )
    relay: Relay | None = Field(
        default=None,
        description="Only by the repository owner's decision: fetch through the project's "
        "relay. Null means requests go direct.",
    )
    engagement: Engagement
    access_requested: dt.date | None = None
    access_granted: dt.date | None = None
    sources: list[Source] = Field(
        default_factory=list,
        description="Where the technical facts in this file come from.",
    )
    findings: list[Finding] = Field(
        default_factory=list,
        description="Dated observations shown on the transparency page.",
    )
    notes: NeutralText | None = None
    enabled: bool = Field(description="True if the pipeline should fetch this operator.")

    @model_validator(mode="after")
    def _check(self) -> "OperatorConfig":
        problems = []
        if self.id in RESERVED_IDS:
            problems.append(f"id {self.id!r} is reserved for gap-filler sources")
        log = self.engagement.log
        requested = next((e.date for e in log if e.action == "request_sent"), None)
        granted = next((e.date for e in log if e.action == "key_granted"), None)
        if requested != self.access_requested:
            problems.append(
                "access_requested must be the date of the first request_sent entry in "
                f"engagement.log ({requested or 'none recorded'})"
            )
        if granted != self.access_granted:
            problems.append(
                "access_granted must be the date of the first key_granted entry in "
                f"engagement.log ({granted or 'none recorded'})"
            )
        if (
            self.access_requested is not None
            and self.access_granted is not None
            and self.access_granted < self.access_requested
        ):
            problems.append("access_granted is earlier than access_requested")
        if self.enabled:
            if self.adapter == "unknown":
                problems.append("an enabled operator needs an adapter")
            if self.base_url == "unknown" and not self.endpoints:
                problems.append("an enabled operator needs a base_url or at least one endpoint")
            if self.auth.method == "unknown" or self.auth.name == "unknown":
                problems.append("an enabled operator needs known auth details")
            if not self.attribution:
                problems.append("an enabled operator needs an attribution statement")
            if (
                self.licence is None
                or self.licence.name == "unknown"
                or self.licence.checked == "unknown"
            ):
                problems.append("an enabled operator needs licence terms that have been checked")
        if self.response_envelope != "ocpi" and self.adapter != "ocpi_221":
            problems.append("response_envelope only applies to the ocpi_221 adapter")
        if self.relay is not None:
            if self.auth.method != "none":
                problems.append("only a feed that needs no key may be relayed")
            if self.relay.url_variable == self.relay.secret_name:
                problems.append("relay url_variable and secret_name must differ")
        if self.auth.method in ("header", "query_param"):
            urls = [endpoint.url for endpoint in self.endpoints.values()]
            if self.base_url != "unknown":
                urls.append(self.base_url)
            problems += [
                f"{url} must use https, because requests to it carry a key"
                for url in urls
                if not url.startswith("https://")
            ]
        if problems:
            raise ValueError("; ".join(problems))
        return self
