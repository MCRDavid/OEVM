"""Model for one operator registry file (operators/<id>.yaml).

Each file records how to reach one operator's open data and what this project
knows about getting access to it. Anything not yet known is written as
"unknown" or "needs_testing" rather than guessed.

Never put a key, token or password in a registry file. Keys live in GitHub
Actions secrets, and the file gives only the secret's name in auth.secret_name (and,
for a feed that exchanges a client id and secret for a token, auth.client_id_secret_name).
URLs that carry credentials are rejected.
"""

import datetime as dt
import re
from typing import Annotated, Literal
from urllib.parse import parse_qsl, urlsplit

from pydantic import AfterValidator, BaseModel, ConfigDict, Field, model_validator

Unknown = Literal["unknown"]

# A UK postcode, with or without its space (the BFPO and overseas territory forms are not
# needed here). Used only to decide whether wrong coordinates are obviously a UK place.
UK_POSTCODE = re.compile(r"^[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}$", re.IGNORECASE)
Support = Literal["supported", "not_supported", "needs_testing", "unknown"]
AdapterName = Literal[
    "ocpi_221", "sent_copy", "eco_movement_pcpr", "gridserve", "static_file", "custom", "unknown"
]
AuthMethod = Literal["none", "header", "query_param", "client_credentials", "unknown"]
EndpointKind = Literal["versions", "locations", "tariffs", "statuses", "download"]
EndpointStatus = Literal["documented", "needs_testing"]
ResponseEnvelope = Literal["ocpi", "data_list", "by_module"]
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
    secret_name: SecretName | None = Field(
        default=None,
        description="NAME of the GitHub Actions secret that holds the key, or, with "
        "client_credentials, the client secret. Never the key itself.",
    )
    scheme: str | None = Field(
        default=None,
        pattern=r"^[A-Za-z][A-Za-z0-9-]*$",
        description="Word sent before the key in a header, such as 'Token' for "
        "'Authorization: Token <key>'. Null if the header holds only the key.",
    )
    client_id_secret_name: SecretName | None = Field(
        default=None,
        description="With client_credentials only: NAME of the GitHub Actions secret that "
        "holds the client id.",
    )
    token_url: SafeUrl | None = Field(
        default=None,
        description="With client_credentials only: the https address where the client id "
        "and secret are exchanged for an access token, which is then sent in the header "
        "`name`, after `scheme`.",
    )

    @property
    def secret_names(self) -> tuple[str, ...]:
        """Every GitHub Actions secret this operator's requests need."""
        return tuple(n for n in (self.client_id_secret_name, self.secret_name) if n)

    @model_validator(mode="after")
    def _check(self) -> "Auth":
        if self.scheme is not None and self.method not in ("header", "client_credentials"):
            raise ValueError("scheme only applies when method is 'header' or 'client_credentials'")
        if self.method == "none":
            if self.name is not None or self.secret_name is not None:
                raise ValueError("name and secret_name must be null when method is 'none'")
        elif self.method in ("header", "query_param", "client_credentials"):
            if not self.name:
                raise ValueError(f"name is required when method is {self.method!r}")
            if not self.secret_name:
                raise ValueError(f"secret_name is required when method is {self.method!r}")
        if self.method == "client_credentials":
            if not self.client_id_secret_name or not self.token_url:
                raise ValueError(
                    "client_id_secret_name and token_url are required when method is "
                    "'client_credentials'"
                )
            if self.client_id_secret_name == self.secret_name:
                raise ValueError("client_id_secret_name and secret_name must differ")
            if not self.token_url.startswith("https://"):
                raise ValueError("token_url must use https, because the request carries a key")
        elif self.client_id_secret_name is not None or self.token_url is not None:
            raise ValueError(
                "client_id_secret_name and token_url only apply when method is 'client_credentials'"
            )
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


class MoreEndpoints(_Model):
    """One more pair of files, read as well as the operator's endpoints (ocpi_221 only)."""

    locations: Endpoint
    tariffs: Endpoint


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

    A longitude missing its minus sign can also leave the point inside the UK, far from the
    place its postcode names. No check can see that, so such a location is corrected only
    when the owner names it in sign_missing (ADR 0013, amended 23 October 2026).
    """

    decided: dt.date = Field(description="Date the owner made the decision (YYYY-MM-DD).")
    basis: NeutralText = Field(description="Why obviously wrong coordinates may be corrected.")
    sign_missing: list["SignMissingLocation"] = Field(
        default_factory=list,
        description="Locations whose longitude is missing its minus sign although the point "
        "as published is inside the UK, each named by the owner by exact OCPI id.",
    )

    @model_validator(mode="after")
    def _unique(self) -> "SwappedCoordinates":
        ids = [location.id for location in self.sign_missing]
        if len(set(ids)) != len(ids):
            raise ValueError("each location may be listed once in sign_missing")
        return self


class SignMissingLocation(_Model):
    """A location the owner found to be missing its longitude's minus sign by its postcode.

    Its minus sign is added only while the feed still sends this postcode and a positive
    longitude, and the point west of the Greenwich meridian is on the UK's land or within
    2 km of its coast.
    """

    id: str = Field(min_length=1, description="The location's OCPI id, exactly as sent.")
    name: str = Field(min_length=1, description="The location's name as the feed sends it.")
    postal_code: str = Field(
        min_length=1, description="The UK postcode the feed sends, which shows where it is."
    )

    @model_validator(mode="after")
    def _uk_postcode(self) -> "SignMissingLocation":
        if not UK_POSTCODE.match(self.postal_code.strip()):
            raise ValueError("postal_code must be a UK postcode")
        return self


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


# OCPI 2.2.1 parking restrictions, which a non-standard reading can never replace.
OCPI_PARKING_RESTRICTIONS = frozenset(
    {"EV_ONLY", "PLUGGED", "DISABLED", "CUSTOMERS", "MOTORCYCLES"}
)


class NonstandardParkingRestrictions(_Model):
    """The repository owner's recorded decision on how EVSE parking restrictions that are
    not OCPI 2.2.1 values are read (ADR 0023).

    Without this decision such values are ignored and logged. A value may only be read as
    "taxis_only": the charge point is labelled "Taxis only", and a location where every
    charge point is taxis only is hidden on the map with private ones unless a visitor asks
    to see them.
    """

    decided: dt.date = Field(description="Date the owner made the decision (YYYY-MM-DD).")
    basis: NeutralText = Field(description="Why the values may be read this way.")
    evidence_url: SafeUrl = Field(description="Where the values can be seen in the feed.")
    restrictions: dict[str, Literal["taxis_only"]] = Field(
        min_length=1, description="Each value as the feed sends it, and how it is read."
    )

    @model_validator(mode="after")
    def _not_ocpi(self) -> "NonstandardParkingRestrictions":
        for value in self.restrictions:
            if value.upper() in OCPI_PARKING_RESTRICTIONS:
                raise ValueError(
                    f"{value!r} is an OCPI 2.2.1 parking restriction and is read as such"
                )
        return self


class ZeroPriceTariffs(_Model):
    """The repository owner's recorded decision that named tariffs whose prices are all zero
    show "Price unknown" rather than "Free" (ADR 0022).

    Without this decision a tariff with at least one price component, every component at
    zero and no minimum charge is confirmed free. A tariff is matched only by its exact OCPI
    id, never by name, and only while its prices are all zero: if the operator gives it a
    price, that price is shown. The tariff itself is published unchanged.
    """

    decided: dt.date = Field(description="Date the owner made the decision (YYYY-MM-DD).")
    basis: NeutralText = Field(description="Why these tariffs are not shown as free.")
    evidence_url: SafeUrl = Field(description="Where the tariffs can be seen in the feed.")
    tariff_ids: list[str] = Field(
        min_length=1,
        description="Each tariff's OCPI id exactly as the feed sends it (CiString(36)).",
    )

    @model_validator(mode="after")
    def _ids(self) -> "ZeroPriceTariffs":
        for item in self.tariff_ids:
            if not re.fullmatch(r"[A-Za-z0-9._-]{1,36}", item):
                raise ValueError(f"{item!r} is not an OCPI tariff id")
        if len(set(self.tariff_ids)) != len(self.tariff_ids):
            raise ValueError("tariff_ids lists a tariff twice")
        return self


class VatNotStated(_Model):
    """The repository owner's recorded decision that this operator's prices exclude VAT
    although its feed gives no VAT figure, so VAT is added at add_percent (ADR 0003,
    amended 22 October 2026).

    OCPI 2.2.1 prices exclude VAT, and each price component can give a VAT rate; an
    omitted rate means no VAT applies. Without this decision such prices are shown as
    published and marked "VAT not stated". With it, every price component of this
    operator's tariffs that gives no VAT figure has add_percent added, and the price says
    the project added it. A component that gives its own figure keeps it. The tariffs
    themselves are published unchanged.
    """

    decided: dt.date = Field(description="Date the owner made the decision (YYYY-MM-DD).")
    basis: NeutralText = Field(
        description="Why the prices are read as excluding VAT, with the evidence checked."
    )
    evidence_url: SafeUrl = Field(description="Where the prices with no VAT figure can be seen.")
    add_percent: float = Field(
        gt=0, le=100, description="The VAT rate added, in percent (UK standard rate: 20)."
    )


class VatInPrice(_Model):
    """The repository owner's recorded decision that the VAT this operator's feed states is
    already in its prices, so it is not added again (ADR 0003, amended 23 October 2026).

    OCPI 2.2.1 prices exclude VAT, and each price component can give the VAT rate to add.
    Some feeds also show the price drivers see, and it can equal the price with no VAT
    added, or every price can be whole pence as published. Without this decision VAT at
    the stated rate is added, as OCPI says. With it, each price is shown as published,
    marked as reading the stated VAT as already in the price.
    The tariffs themselves are published unchanged.
    """

    decided: dt.date = Field(description="Date the owner made the decision (YYYY-MM-DD).")
    basis: NeutralText = Field(
        description="Why the prices are read as including VAT, with the evidence checked."
    )
    evidence_url: SafeUrl = Field(description="Where the prices and their VAT can be seen.")


class OwnFeedOverCopies(_Model):
    """The repository owner's recorded decision that this operator's own feed is shown in
    place of copies of its locations in other operators' feeds (ADR 0027).

    A platform's feed can carry a network's locations under the network's own OCPI country
    and party codes, while the network publishes them itself too. While this operator's own
    locations are on the map, from this run or its last good copy, every location that a
    named operator's feed sends under this operator's ocpi_country_code and ocpi_party_id
    is left off the map. Each is counted and listed on the feed health page; nothing in
    either feed is changed. When this operator has nothing on the map, the copies are shown.
    Where the copies are sent under other codes than this operator's own feed uses, such as
    the network's registered party while its own feed uses another, copies_country_code
    and copies_party_id name them (amended 29 October 2026).
    """

    decided: dt.date = Field(description="Date the owner made the decision (YYYY-MM-DD).")
    basis: NeutralText = Field(
        description="Why the other feeds' records are copies of this operator's, with the "
        "evidence checked."
    )
    evidence_url: SafeUrl = Field(description="Where the copies can be seen.")
    operators: list[str] = Field(
        min_length=1,
        description="Ids of the operators whose feeds carry the copies. Each must be in the "
        "registry.",
    )
    copies_country_code: str | None = Field(
        default=None,
        pattern=r"^[A-Z]{2}$",
        description="The OCPI country code the copies are sent under, where it differs from "
        "this operator's own; given with copies_party_id. Null means this operator's own.",
    )
    copies_party_id: str | None = Field(
        default=None,
        pattern=r"^[A-Z0-9]{3}$",
        description="The OCPI party id the copies are sent under, where it differs from this "
        "operator's own; given with copies_country_code. Null means this operator's own.",
    )

    @model_validator(mode="after")
    def _ids(self) -> "OwnFeedOverCopies":
        for item in self.operators:
            if not re.fullmatch(r"[a-z0-9_]+", item):
                raise ValueError(f"{item!r} is not an operator id")
        if len(set(self.operators)) != len(self.operators):
            raise ValueError("each operator may be named once")
        if (self.copies_country_code is None) != (self.copies_party_id is None):
            raise ValueError("copies_country_code and copies_party_id are given together")
        return self

    def copies_codes(self, country_code: str, party_id: str) -> tuple[str, str]:
        """The country and party codes the copies are sent under, given the operator's own."""
        if self.copies_country_code and self.copies_party_id:
            return self.copies_country_code, self.copies_party_id
        return country_code, party_id


class LimitsPerKey(_Model):
    """The repository owner's recorded decision that this operator's published rate limits
    apply to each key, not to everyone using its host (ADR 0003, amended 29 October 2026).

    A platform can serve many networks from one host, each with its own key, and publish
    limits without saying whether they count per key or per address. Without this decision
    every operator on the host shares one gap, the strictest reading. With it, this
    operator's gap is kept for its own key; requests to the host, from whichever operator,
    are still sent one at a time and at least the floor plus the margin apart, and a
    server's request to wait still holds back every key on the host.
    """

    decided: dt.date = Field(description="Date the owner made the decision (YYYY-MM-DD).")
    basis: NeutralText = Field(
        description="Why the limits are read per key, and what the publisher says about them."
    )
    evidence_url: SafeUrl = Field(description="Where the limits are published.")


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


class TariffsFrom(_Model):
    """The repository owner's recorded decision that this operator's connectors may be priced
    from tariffs in a related operator's feed (ADR 0020).

    Some networks publish their charge points and their tariffs in separate feeds from one
    back office, so a connector can name a tariff that only a sister network's response
    holds. A connector is priced from a named operator only when the OCPI id it names is in
    the form of a UUID, its own operator's tariffs do not have that OCPI id under any
    country or party code, exactly one tariff across the named operators' tariffs has that
    exact OCPI id with the same country code, and that operator was fetched in the same
    run. Names and descriptions are never matched. The details on the map say which feed
    the price came from. Without this decision such connectors show "Price unknown".
    """

    decided: dt.date = Field(description="Date the owner made the decision (YYYY-MM-DD).")
    basis: NeutralText = Field(
        description="Why the operators are related, for example that one company runs both "
        "networks and publishes both feeds from the same host."
    )
    evidence_url: SafeUrl = Field(description="Where the relationship can be seen.")
    operators: list[str] = Field(
        min_length=1,
        description="Ids of the related operators whose tariffs may be used. Each must be in "
        "the registry and publish its feeds on the same host as this operator.",
    )

    @model_validator(mode="after")
    def _ids(self) -> "TariffsFrom":
        for item in self.operators:
            if not re.fullmatch(r"[a-z0-9_]+", item):
                raise ValueError(f"{item!r} is not an operator id")
        if len(set(self.operators)) != len(self.operators):
            raise ValueError("each operator may be named once")
        return self


class ExpiredCertificate(_Model):
    """The repository owner's recorded decision to read this operator's feed past one
    expired TLS certificate (ADR 0021).

    Requests to the host still check the certificate chain against the usual trusted
    authorities and check the host name; only the certificate's dates are not checked. A
    response is then used only if the server presented exactly the certificate named by
    sha256, or one that is in date today, which means the certificate has been renewed and
    this decision can be removed. Anything else stops the fetch. Only feeds that need no
    key, all on this one host, so no key is ever sent over such a connection. Without this
    decision an expired certificate stops the fetch.
    """

    decided: dt.date = Field(description="Date the owner made the decision (YYYY-MM-DD).")
    basis: NeutralText = Field(description="Why the feed may be read past the certificate.")
    evidence_url: SafeUrl = Field(description="Where the operator links the feed.")
    host: str = Field(
        pattern=r"^[a-z0-9]([a-z0-9-]*[a-z0-9])?(\.[a-z0-9]([a-z0-9-]*[a-z0-9])?)+$",
        description="The host whose certificate has expired, for example "
        "'ocpi-pcpr.hubeleon.net'. Every feed URL in the file must be on it.",
    )
    sha256: str = Field(
        pattern=r"^([0-9A-F]{2}:){31}[0-9A-F]{2}$",
        description="SHA-256 fingerprint of the one expired certificate accepted, as "
        "'49:82:...', in capitals.",
    )
    expired: dt.date = Field(description="The day the certificate expired (YYYY-MM-DD).")


SentCopyFile = Annotated[
    str,
    Field(
        pattern=r"^sent_copies/[a-z0-9_]+/[^/]+\.json\.gz$",
        description="Path of the file as the operator sent it, gzipped, under "
        "sent_copies/<operator id>/.",
    ),
]


class SentCopy(_Model):
    """The repository owner's recorded decision to show a copy of this operator's data that
    it sent to this project, because it publishes none at an address that can be fetched
    (ADR 0029). Used with the sent_copy adapter.

    The copy is OCPI 2.2.1 location and tariff responses, kept in the repository exactly
    as sent (gzipped) and read as they are on every run, with no request to the operator.
    Its records carry the time the operator made the copy, never the time of the run, so
    nothing looks newer than it is, and the map says the data is a copy, when it was sent
    and that it is not updated. Every charge point status is shown as unknown, because a
    status from a file sent once says nothing about now. Without this decision a copy an
    operator sends is kept as evidence only and never shown.
    """

    decided: dt.date = Field(description="Date the owner made the decision (YYYY-MM-DD).")
    basis: NeutralText = Field(description="Why the copy may be shown, and until when.")
    evidence_file: EvidenceFile = Field(
        description="The operator's message that came with the copy, saved under "
        "evidence/<operator id>/ with names and addresses removed."
    )
    channel: Channel = Field(description="How the copy came, for example 'email'.")
    received: dt.date = Field(description="Date the copy came (YYYY-MM-DD).")
    made_at: dt.datetime = Field(
        description="When the operator made the copy, to the second, with its time zone: "
        "the timestamp its OCPI responses carry. Shown as the date of the data."
    )
    locations: SentCopyFile = Field(description="The OCPI 2.2.1 locations response.")
    tariffs: SentCopyFile = Field(description="The OCPI 2.2.1 tariffs response.")

    @model_validator(mode="after")
    def _check(self) -> "SentCopy":
        if self.made_at.tzinfo is None:
            raise ValueError("made_at needs a time zone, for example 2026-10-26T14:22:52Z")
        if self.made_at.date() > self.received:
            raise ValueError("made_at is later than the day the copy was received")
        if self.decided < self.received:
            raise ValueError("decided is earlier than the day the copy was received")
        if self.locations == self.tariffs:
            raise ValueError("locations and tariffs must be different files")
        return self


class ExcludedLocation(_Model):
    id: str = Field(min_length=1, description="The location's OCPI id, exactly as sent.")
    name: str = Field(min_length=1, description="The location's name as the feed sends it.")
    evse_uids: list[Annotated[str, Field(min_length=1)]] = Field(
        default_factory=list,
        description="Only these EVSEs, by their exact uid, are left off, and the rest of the "
        "location stays on the map. Empty (the default) leaves off the whole location.",
    )

    @model_validator(mode="after")
    def _unique_evses(self) -> "ExcludedLocation":
        if len(set(self.evse_uids)) != len(self.evse_uids):
            raise ValueError("each EVSE may be listed once")
        return self


class ExcludedLocations(_Model):
    """The repository owner's recorded decision to leave named locations off the map, such
    as test sites an operator's feed marks for publishing, or only named EVSEs at them,
    such as a test charger at a site that is otherwise in use.

    Only the listed OCPI location ids are left off, or, where a location lists evse_uids,
    only those EVSEs. Each is logged as an issue in the run, and the transparency page
    lists them. Without this decision every location the feed marks for publishing is kept
    whole.
    """

    decided: dt.date = Field(description="Date the owner made the decision (YYYY-MM-DD).")
    basis: NeutralText = Field(description="Why these locations are left off.")
    evidence_url: SafeUrl = Field(description="Where the locations can be seen in the feed.")
    locations: list[ExcludedLocation] = Field(min_length=1)

    @model_validator(mode="after")
    def _unique(self) -> "ExcludedLocations":
        ids = [location.id for location in self.locations]
        if len(set(ids)) != len(ids):
            raise ValueError("each location may be listed once")
        return self


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
    more_endpoints: list[MoreEndpoints] = Field(
        default_factory=list,
        description="Further location and tariff files, for an operator that publishes its "
        "data in several files of the same form, such as one pair for each site. Each pair "
        "is read like 'endpoints' and the records are added together, each keeping the URL "
        "it came from. Needs locations and tariffs in 'endpoints'. ocpi_221 only.",
    )
    response_envelope: ResponseEnvelope = Field(
        default="ocpi",
        description="'ocpi' (the default) requires each response to be an OCPI 2.2.1 "
        "response object with a status_code. 'data_list' also accepts an object with a "
        "list of OCPI records in 'data' and no status_code, for feeds whose records are OCPI "
        "but whose wrapper is not. 'by_module' is for one URL that answers every module: "
        "'data' is an object keyed by module name, each value an OCPI response object; "
        "give each module that same URL, and it is fetched once. Record the reason as a "
        "finding. ocpi_221 only.",
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
    nonstandard_parking_restrictions: NonstandardParkingRestrictions | None = Field(
        default=None,
        description="Only by the repository owner's decision: how EVSE parking restrictions "
        "that are not OCPI 2.2.1 values are read. Null means they are ignored.",
    )
    relay: Relay | None = Field(
        default=None,
        description="Only by the repository owner's decision: fetch through the project's "
        "relay. Null means requests go direct.",
    )
    tariffs_from: TariffsFrom | None = Field(
        default=None,
        description="Only by the repository owner's decision: price connectors that name a "
        "tariff only a related operator's feed holds from that feed. Null means such "
        "connectors show 'Price unknown'.",
    )
    zero_price_tariffs: ZeroPriceTariffs | None = Field(
        default=None,
        description="Only by the repository owner's decision: tariffs, by exact OCPI id, "
        "whose prices are all zero but which show 'Price unknown' rather than 'Free'. Null "
        "means a tariff whose prices are all zero shows as free.",
    )
    vat_not_stated: VatNotStated | None = Field(
        default=None,
        description="Only by the repository owner's decision: add VAT at a set rate to "
        "price components that give no VAT figure. Null means such prices are shown as "
        "published and marked 'VAT not stated'.",
    )
    vat_in_price: VatInPrice | None = Field(
        default=None,
        description="Only by the repository owner's decision: read the VAT the feed states "
        "as already in its prices. Null means the stated VAT is added, as OCPI 2.2.1 says.",
    )
    own_feed_over_copies: OwnFeedOverCopies | None = Field(
        default=None,
        description="Only by the repository owner's decision: leave off the map the "
        "locations other operators' feeds send under this operator's country and party "
        "codes, while this operator's own are on it. Null means both are shown.",
    )
    limits_per_key: LimitsPerKey | None = Field(
        default=None,
        description="Only by the repository owner's decision: read the published rate "
        "limits as applying to this operator's own key, so its gap is not shared with other "
        "operators on the host. Null means every operator on the host shares one gap.",
    )
    expired_certificate: ExpiredCertificate | None = Field(
        default=None,
        description="Only by the repository owner's decision: read the feed past one "
        "expired TLS certificate, still checking its chain and host name. Null means an "
        "expired certificate stops the fetch.",
    )
    excluded_locations: ExcludedLocations | None = Field(
        default=None,
        description="Only by the repository owner's decision: OCPI location ids to leave off "
        "the map, such as test sites. Null means every location marked for publishing is "
        "kept.",
    )
    sent_copy: SentCopy | None = Field(
        default=None,
        description="Only by the repository owner's decision, with the sent_copy adapter: "
        "show a copy of the operator's data that it sent, dated as made, with every charge "
        "point status unknown (ADR 0029). Null means a sent copy is never shown.",
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

    def feed_urls(self) -> list[str]:
        """Every feed URL in this file: its endpoints, more_endpoints and base URL."""
        urls = [endpoint.url for endpoint in self.endpoints.values()]
        urls += [pair.locations.url for pair in self.more_endpoints]
        urls += [pair.tariffs.url for pair in self.more_endpoints]
        if self.base_url != "unknown":
            urls.append(self.base_url)
        return urls

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
            if self.base_url == "unknown" and not self.endpoints and self.sent_copy is None:
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
        if (self.adapter == "sent_copy") != (self.sent_copy is not None):
            problems.append("the sent_copy adapter and a sent_copy decision go together")
        if self.sent_copy is not None:
            folder = f"sent_copies/{self.id}/"
            problems += [
                f"sent_copy file {path} must be under {folder}"
                for path in (self.sent_copy.locations, self.sent_copy.tariffs)
                if not path.startswith(folder)
            ]
            if self.feed_urls():
                problems.append("a sent copy is read from the repository, so it has no feed URLs")
            if self.auth.method != "none":
                problems.append("a sent copy is never fetched, so its auth method is none")
            if self.relay is not None or self.expired_certificate is not None:
                problems.append("a sent copy is never fetched, so it has no relay or certificate")
        if self.response_envelope != "ocpi" and self.adapter != "ocpi_221":
            problems.append("response_envelope only applies to the ocpi_221 adapter")
        if self.response_envelope == "by_module" and (
            not {"locations", "tariffs"} <= set(self.endpoints)
            or self.endpoints["locations"].url != self.endpoints["tariffs"].url
        ):
            problems.append("response_envelope by_module needs one URL for locations and tariffs")
        if self.more_endpoints:
            if self.adapter != "ocpi_221":
                problems.append("more_endpoints only applies to the ocpi_221 adapter")
            if not {"locations", "tariffs"} <= set(self.endpoints):
                problems.append("more_endpoints needs locations and tariffs in endpoints")
            if self.response_envelope == "by_module":
                problems.append("more_endpoints cannot be used with response_envelope by_module")
            urls = self.feed_urls()
            problems += [
                f"{url} is given more than once in endpoints and more_endpoints"
                for url in sorted({url for url in urls if urls.count(url) > 1})
            ]
        if self.relay is not None:
            if self.auth.method != "none":
                problems.append("only a feed that needs no key may be relayed")
            if self.relay.url_variable == self.relay.secret_name:
                problems.append("relay url_variable and secret_name must differ")
        if self.tariffs_from is not None and self.id in self.tariffs_from.operators:
            problems.append("tariffs_from cannot name the operator itself")
        if self.vat_in_price is not None and self.vat_not_stated is not None:
            problems.append("vat_in_price and vat_not_stated cannot both be recorded")
        if self.own_feed_over_copies is not None:
            if self.id in self.own_feed_over_copies.operators:
                problems.append("own_feed_over_copies cannot name the operator itself")
            if "unknown" in (self.ocpi_country_code, self.ocpi_party_id):
                problems.append("own_feed_over_copies needs a known ocpi_country_code and party")
        if self.limits_per_key is not None and (
            self.auth.method == "none" or not self.auth.secret_name
        ):
            problems.append("limits_per_key needs a key of the operator's own (auth.secret_name)")
        if self.expired_certificate is not None:
            if self.auth.method != "none":
                problems.append("only a feed that needs no key may be read past a certificate")
            if self.relay is not None:
                problems.append("a relayed feed cannot also be read past a certificate")
            urls = self.feed_urls()
            problems += [
                f"{url} must be an https URL on {self.expired_certificate.host}, the host "
                "named in expired_certificate"
                for url in urls
                if urlsplit(url).scheme != "https"
                or urlsplit(url).netloc.lower() != self.expired_certificate.host
            ]
            if not urls:
                problems.append("expired_certificate needs the feed URLs on its host")
        if self.auth.method in ("header", "query_param", "client_credentials"):
            problems += [
                f"{url} must use https, because requests to it carry a key"
                for url in self.feed_urls()
                if not url.startswith("https://")
            ]
        if problems:
            raise ValueError("; ".join(problems))
        return self
