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
FindingKind = Literal["spec_conformance", "data_quality", "access", "documentation"]
FindingStatus = Literal["open", "resolved"]
EngagementStatus = Literal[
    "open_anonymous",
    "open_shared_key",
    "key_on_request",
    "signed_agreement_required",
    "requested_no_reply",
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
    "request_declined": "Request declined",
    "no_public_feed_found": "No public feed found",
    "possibly_out_of_scope": "Possibly out of scope",
    "unknown": "Not yet established",
}

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
    file: str | None = Field(
        default=None,
        pattern=r"^evidence/[a-z0-9_]+/[^/].*$",
        description="Path of a saved copy under evidence/<operator id>/. No personal names "
        "or email addresses.",
    )
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


class Engagement(_Model):
    status: EngagementStatus
    evidence: list[Evidence] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "Engagement":
        if self.status != "unknown" and not self.evidence:
            raise ValueError(f"status {self.status!r} needs at least one evidence entry")
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
        if self.engagement.status == "requested_no_reply" and self.access_requested is None:
            problems.append("status 'requested_no_reply' needs access_requested")
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
