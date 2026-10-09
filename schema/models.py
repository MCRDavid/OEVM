"""Normalised models for charge point locations and tariffs.

These are the project's own models, not raw OCPI 2.2.1 objects. Each adapter
converts its source's format into these models and the pipeline publishes them
as JSON. The JSON Schema exported from them (schema/json/) is the contract the
front end relies on.

Rules the models enforce:

- Every Location and Tariff carries Provenance, and its id starts with the
  provenance source_id.
- Timestamps must include a time zone.
- A Tariff's price_state is always derived from its prices. It is
  "free_confirmed" only when the tariff has at least one price component, every
  component is zero and there is no minimum charge. Supplying any other value is
  an error.
- VAT is a percentage. None means "VAT not stated", which is not the same as
  0% VAT.
"""

from datetime import date
from typing import Annotated, Literal

from pydantic import AwareDatetime, BaseModel, ConfigDict, Field, model_validator


class _Model(BaseModel):
    """Base for every model. Unknown fields are errors, so typos fail loudly."""

    model_config = ConfigDict(
        extra="forbid",
        # The exported schema describes published output, where every field is present.
        json_schema_serialization_defaults_required=True,
    )


HttpUrl = Annotated[str, Field(pattern=r"^https?://\S+$")]
SourceId = Annotated[
    str,
    Field(
        pattern=r"^[a-z0-9_]+$",
        description="Operator id from the registry (for example 'chargy'), or a gap-filler "
        "source such as 'osm', 'ocm' or 'reports'.",
    ),
]
RecordId = Annotated[
    str,
    Field(
        pattern=r"^[a-z0-9_]+:[^:]+:[^:]+:.+$",
        description="'{source}:{country}:{party}:{id}', for example 'chargy:GB:CGY:1234'. "
        "Use 'unknown' for a country or party that is not known.",
    ),
]
ClockTime = Annotated[str, Field(pattern=r"^([01]\d|2[0-3]):[0-5]\d$", description="HH:MM")]
ClockTimeEnd = Annotated[
    str, Field(pattern=r"^(([01]\d|2[0-3]):[0-5]\d|24:00)$", description="HH:MM, or 24:00")
]

Access = Literal["public", "customers", "restricted", "unknown"]
EvseStatus = Literal[
    "available",
    "blocked",
    "charging",
    "inoperative",
    "out_of_order",
    "planned",
    "removed",
    "reserved",
    "unknown",
    # Not an OCPI 2.2.1 status: in service, but free or in use is not stated. Used only
    # under the owner's decision recorded in an operator file (nonstandard_statuses).
    "working",
]
ConnectorFormat = Literal["socket", "cable", "unknown"]
PowerType = Literal["ac_1_phase", "ac_2_phase", "ac_2_phase_split", "ac_3_phase", "dc", "unknown"]
PriceState = Literal["priced", "free_confirmed", "unknown"]
PriceComponentType = Literal["energy", "flat", "parking_time", "time"]
DayOfWeek = Literal["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]
Reservation = Literal["reservation", "reservation_expires"]
TariffType = Literal["ad_hoc_payment", "profile_cheap", "profile_fast", "profile_green", "regular"]
Method = Literal[
    "operator_feed",
    "operator_static_file",
    "operator_website",
    "foi",
    "open_charge_map",
    "openstreetmap",
    "user_report",
]
Confidence = Literal["high", "medium_high", "medium", "low"]


def _source_of(record_id: str) -> str:
    return record_id.split(":", 1)[0]


class Provenance(_Model):
    """Where a record came from and how far to trust it."""

    source_id: SourceId
    source_url: HttpUrl = Field(description="The feed, file or page the record came from.")
    licence: str = Field(
        min_length=1,
        description="Licence of the source data, for example 'OGL-3.0', 'ODbL-1.0' or 'CC-BY-4.0'.",
    )
    fetched_at: AwareDatetime = Field(description="When this project retrieved the record.")
    last_confirmed_at: AwareDatetime | None = Field(
        default=None, description="When the source last confirmed the record, if known."
    )
    method: Method
    confidence: Confidence


class Coordinates(_Model):
    latitude: float = Field(ge=-90, le=90)
    longitude: float = Field(ge=-180, le=180)


class Address(_Model):
    street: str | None = Field(default=None, description="Street and house number.")
    city: str | None = None
    postal_code: str | None = None
    country: str | None = Field(
        default=None, pattern=r"^[A-Z]{3}$", description="ISO 3166-1 alpha-3, for example GBR."
    )


class Operator(_Model):
    registry_id: SourceId | None = Field(
        default=None, description="Id in operators/, or null if the operator is not registered."
    )
    name: str | None = None


class RegularHours(_Model):
    weekday: int = Field(ge=1, le=7, description="1 is Monday and 7 is Sunday, as in OCPI.")
    period_begin: ClockTime
    period_end: ClockTimeEnd


class OpeningHours(_Model):
    twenty_four_seven: bool
    regular_hours: list[RegularHours] = Field(default_factory=list)

    @model_validator(mode="after")
    def _no_hours_when_always_open(self) -> "OpeningHours":
        if self.twenty_four_seven and self.regular_hours:
            raise ValueError("regular_hours must be empty when twenty_four_seven is true")
        return self


class Connector(_Model):
    id: str = Field(min_length=1)
    standard: str = Field(
        pattern=r"^[A-Za-z0-9_]+$",
        description="OCPI 2.2.1 ConnectorType value as published, for example "
        "'IEC_62196_T2_COMBO', or 'unknown'.",
    )
    format: ConnectorFormat = "unknown"
    power_type: PowerType = "unknown"
    max_kw: float | None = Field(default=None, ge=0)
    tariff_ids: list[RecordId] = Field(
        default_factory=list, description="Ids of Tariff records that apply to this connector."
    )


class EVSE(_Model):
    uid: str = Field(min_length=1, description="OCPI EVSE uid, unique within its location.")
    evse_id: str | None = Field(
        default=None,
        description="eMI3 EVSE ID (for example 'GB*ABC*E123'), used to match across sources.",
    )
    status: EvseStatus = "unknown"
    status_at: AwareDatetime | None = Field(
        default=None, description="When the status was last reported."
    )
    connectors: list[Connector] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check(self) -> "EVSE":
        if self.status != "unknown" and self.status_at is None:
            raise ValueError("status_at is required when status is not 'unknown'")
        ids = [c.id for c in self.connectors]
        if len(ids) != len(set(ids)):
            raise ValueError(f"duplicate connector ids in EVSE {self.uid!r}")
        return self


class Location(_Model):
    id: RecordId
    name: str | None = None
    address: Address = Field(default_factory=Address)
    coordinates: Coordinates
    time_zone: str | None = Field(
        default=None, description="IANA time zone, for example 'Europe/London'."
    )
    operator: Operator = Field(default_factory=Operator)
    access: Access = "unknown"
    opening_hours: OpeningHours | None = Field(
        default=None, description="Null when the opening hours are unknown."
    )
    evses: list[EVSE] = Field(default_factory=list)
    last_updated: AwareDatetime | None = Field(
        default=None, description="When the source says it last changed this location."
    )
    provenance: Provenance

    @model_validator(mode="after")
    def _check(self) -> "Location":
        if _source_of(self.id) != self.provenance.source_id:
            raise ValueError(
                f"id {self.id!r} must start with provenance source_id {self.provenance.source_id!r}"
            )
        uids = [e.uid for e in self.evses]
        if len(uids) != len(set(uids)):
            raise ValueError(f"duplicate EVSE uids in location {self.id!r}")
        return self


class PriceComponent(_Model):
    type: PriceComponentType
    price: float = Field(
        ge=0,
        description="Price excluding VAT, in the tariff currency: per kWh for energy, per hour "
        "for time and parking_time, per session for flat (OCPI 2.2.1 units).",
    )
    vat: float | None = Field(
        default=None,
        ge=0,
        le=100,
        description="VAT percentage. Null means the source gave no VAT figure, shown as 'VAT not "
        "stated'. OCPI 2.2.1 says an omitted VAT means no VAT is applicable, which is different "
        "from 0% VAT.",
    )
    step_size: int | None = Field(
        default=None, ge=0, description="Billing step as in OCPI. Null when not stated."
    )


class TariffRestrictions(_Model):
    """When a tariff element applies. Times are local to the location."""

    start_time: ClockTime | None = None
    end_time: ClockTime | None = None
    start_date: date | None = None
    end_date: date | None = None
    min_kwh: float | None = Field(default=None, ge=0)
    max_kwh: float | None = Field(default=None, ge=0)
    min_current: float | None = Field(default=None, ge=0, description="Amperes.")
    max_current: float | None = Field(default=None, ge=0, description="Amperes.")
    min_power: float | None = Field(default=None, ge=0, description="Kilowatts.")
    max_power: float | None = Field(default=None, ge=0, description="Kilowatts.")
    min_duration: int | None = Field(default=None, ge=0, description="Seconds.")
    max_duration: int | None = Field(default=None, ge=0, description="Seconds.")
    day_of_week: list[DayOfWeek] = Field(default_factory=list)
    reservation: Reservation | None = Field(
        default=None, description="Set when the element prices a reservation, not charging."
    )


class TariffElement(_Model):
    price_components: list[PriceComponent] = Field(min_length=1)
    restrictions: TariffRestrictions | None = None


def derive_price_state(elements: list[TariffElement], min_price: float | None = None) -> PriceState:
    """Work out a tariff's price_state from its price components and minimum price.

    "free_confirmed" needs at least one component, every component at zero and no minimum
    charge above zero. A tariff with no components at all says nothing about price, so it
    is "unknown".
    """
    components = [c for element in elements for c in element.price_components]
    if not components:
        return "unknown"
    if all(c.price == 0 for c in components) and not min_price:
        return "free_confirmed"
    return "priced"


class Tariff(_Model):
    id: RecordId
    currency: str = Field(pattern=r"^[A-Z]{3}$", description="ISO 4217, for example GBP.")
    type: TariffType | None = Field(
        default=None,
        description="OCPI tariff type, for example 'ad_hoc_payment' for paying at the charger.",
    )
    elements: list[TariffElement] = Field(default_factory=list)
    min_price: float | None = Field(
        default=None, ge=0, description="Minimum cost of a session, excluding VAT."
    )
    max_price: float | None = Field(
        default=None, ge=0, description="Maximum cost of a session, excluding VAT."
    )
    alt_text: str | None = Field(
        default=None, description="The operator's own text description of the tariff."
    )
    alt_url: HttpUrl | None = None
    start_date_time: AwareDatetime | None = None
    end_date_time: AwareDatetime | None = None
    last_updated: AwareDatetime | None = Field(
        default=None, description="When the source says it last changed this tariff."
    )
    price_state: PriceState = Field(
        default="unknown",
        description="Derived from the price components and min_price; never set by hand. "
        "'free_confirmed' only when every component is zero and there is no minimum charge.",
    )
    provenance: Provenance

    @model_validator(mode="after")
    def _check(self) -> "Tariff":
        if _source_of(self.id) != self.provenance.source_id:
            raise ValueError(
                f"id {self.id!r} must start with provenance source_id {self.provenance.source_id!r}"
            )
        derived = derive_price_state(self.elements, self.min_price)
        if "price_state" in self.model_fields_set and self.price_state != derived:
            raise ValueError(
                f"price_state {self.price_state!r} does not match the prices, "
                f"which give {derived!r}"
            )
        self.price_state = derived
        return self
