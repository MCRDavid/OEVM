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

_CREDENTIAL_PARAM = re.compile(
    r"key|token|secret|passw|pwd|signature|auth|credential", re.IGNORECASE
)


def _reject_credentials_in_url(url: str) -> str:
    parts = urlsplit(url)
    if parts.username or parts.password:
        raise ValueError("URL must not contain a username or password")
    for name, _ in parse_qsl(parts.query, keep_blank_values=True):
        if _CREDENTIAL_PARAM.search(name):
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

    @model_validator(mode="after")
    def _check(self) -> "Auth":
        if self.method == "none":
            if self.name is not None or self.secret_name is not None:
                raise ValueError("name and secret_name must be null when method is 'none'")
        elif self.method in ("header", "query_param"):
            if not self.name:
                raise ValueError(f"name is required when method is {self.method!r}")
            if not self.secret_name:
                raise ValueError(f"secret_name is required when method is {self.method!r}")
        return self


class RateLimit(_Model):
    min_seconds_between_requests: float = Field(
        default=2,
        gt=0,
        description="Delay this project leaves between requests. Our own politeness setting, "
        "kept at or above any limit the operator documents.",
    )
    documented: str | None = Field(
        default=None,
        description="The operator's published limit and where it was found. Null if none known.",
    )


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
    note: str | None = None

    @model_validator(mode="after")
    def _check(self) -> "Evidence":
        if self.url is None and self.file is None:
            raise ValueError("evidence needs a url or a file")
        return self


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
    engagement: Engagement
    access_requested: dt.date | None = None
    access_granted: dt.date | None = None
    sources: list[Source] = Field(
        default_factory=list,
        description="Where the technical facts in this file come from.",
    )
    notes: str | None = None
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
        if problems:
            raise ValueError("; ".join(problems))
        return self
