"""Convert OCPI 2.2.1 Location and Tariff objects into the project's own models.

Field meanings follow OCPI 2.2.1 sections 8 (Locations) and 11 (Tariffs). A value that
is not valid OCPI is recorded as "unknown" and logged as an issue, never guessed.
"""

from collections import Counter
from datetime import UTC, datetime

from schema.models import (
    EVSE,
    Address,
    Connector,
    Coordinates,
    Location,
    OpeningHours,
    Operator,
    PriceComponent,
    Provenance,
    RegularHours,
    Tariff,
    TariffElement,
    TariffRestrictions,
)
from schema.operator import OperatorConfig

EVSE_STATUSES = {
    "AVAILABLE": "available",
    "BLOCKED": "blocked",
    "CHARGING": "charging",
    "INOPERATIVE": "inoperative",
    "OUTOFORDER": "out_of_order",
    "PLANNED": "planned",
    "REMOVED": "removed",
    "RESERVED": "reserved",
    "UNKNOWN": "unknown",
}
POWER_TYPES = {
    "AC_1_PHASE": "ac_1_phase",
    "AC_2_PHASE": "ac_2_phase",
    "AC_2_PHASE_SPLIT": "ac_2_phase_split",
    "AC_3_PHASE": "ac_3_phase",
    "DC": "dc",
}
# Phases to multiply voltage and amperage by. OCPI gives max_voltage line to neutral for
# AC_3_PHASE. It does not say how to read voltage for two-phase supplies, so those are
# only given a power figure when the feed states max_electric_power.
PHASES = {"ac_1_phase": 1, "ac_3_phase": 3, "dc": 1}
FORMATS = {"SOCKET": "socket", "CABLE": "cable"}
DIMENSIONS = {"ENERGY": "energy", "FLAT": "flat", "PARKING_TIME": "parking_time", "TIME": "time"}
TARIFF_TYPES = {
    "AD_HOC_PAYMENT": "ad_hoc_payment",
    "PROFILE_CHEAP": "profile_cheap",
    "PROFILE_FAST": "profile_fast",
    "PROFILE_GREEN": "profile_green",
    "REGULAR": "regular",
}
RESERVATIONS = {"RESERVATION": "reservation", "RESERVATION_EXPIRES": "reservation_expires"}
RESTRICTION_FIELDS = (
    "start_time",
    "end_time",
    "start_date",
    "end_date",
    "min_kwh",
    "max_kwh",
    "min_current",
    "max_current",
    "min_power",
    "max_power",
    "min_duration",
    "max_duration",
)


class IssueLog:
    """Counts data problems, so a feed with thousands of records gives a short report."""

    def __init__(self) -> None:
        self._counts: Counter[str] = Counter()

    def add(self, message: str) -> None:
        self._counts[message] += 1

    def lines(self) -> list[str]:
        return [m if n == 1 else f"{m} ({n} times)" for m, n in sorted(self._counts.items())]


def publish_allowed(raw: dict, config: OperatorConfig, issues: IssueLog) -> bool:
    """Whether a location may be kept, going by its OCPI 2.2.1 publish flag.

    OCPI 2.2.1 says a location with publish set to false may not be shown on a website or
    app, so those are never kept. A location with no flag is skipped too, unless the
    operator file records the owner's decision to show such locations
    (missing_publish_flag). Any other value is skipped.
    """
    publish = raw.get("publish")
    if publish is True:
        return True
    if publish is False:
        issues.add("location not kept: publish is false")
        return False
    if publish is None:
        if config.missing_publish_flag is not None:
            issues.add(
                "location has no publish flag; kept under the decision recorded in the "
                "operator file"
            )
            return True
        issues.add("location not kept: publish flag missing")
        return False
    issues.add(f"location not kept: publish flag {publish!r} is not true or false")
    return False


def parse_ocpi_datetime(value: object) -> datetime | None:
    """OCPI timestamps are UTC; one without a time zone designator means UTC."""
    if value in (None, ""):
        return None
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _party(raw: dict, config: OperatorConfig) -> tuple[str, str]:
    return (
        raw.get("country_code") or config.ocpi_country_code,
        raw.get("party_id") or config.ocpi_party_id,
    )


def location_record_id(raw: dict, config: OperatorConfig) -> str | None:
    """The id location_from_ocpi gives this record, or None if it has no OCPI id."""
    if raw.get("id") in (None, ""):
        return None
    country, party = _party(raw, config)
    return f"{config.id}:{country}:{party}:{raw['id']}"


def _provenance(config: OperatorConfig, source_url: str, fetched_at: datetime) -> Provenance:
    return Provenance(
        source_id=config.id,
        source_url=source_url,
        licence=config.licence.name if config.licence else "unknown",
        fetched_at=fetched_at,
        last_confirmed_at=fetched_at,
        method="operator_feed",
        confidence="high",
    )


def _max_kw(raw: dict, power_type: str, issues: IssueLog) -> float | None:
    watts = raw.get("max_electric_power")
    if watts:
        return round(watts / 1000, 2)
    phases = PHASES.get(power_type)
    volts, amps = raw.get("max_voltage"), raw.get("max_amperage")
    if phases and volts and amps:
        return round(volts * amps * phases / 1000, 2)
    issues.add(f"connector power not calculated for power_type {power_type!r}")
    return None


def _connector(raw: dict, tariff_prefix: str, issues: IssueLog) -> Connector:
    standard = raw.get("standard")
    if not isinstance(standard, str) or not standard.replace("_", "").isalnum():
        issues.add(f"connector standard {standard!r} is not valid; recorded as unknown")
        standard = "unknown"
    power_type = POWER_TYPES.get(raw.get("power_type"), "unknown")
    if power_type == "unknown":
        issues.add(f"connector power_type {raw.get('power_type')!r} is not an OCPI 2.2.1 value")
    return Connector(
        id=raw["id"],
        standard=standard,
        format=FORMATS.get(raw.get("format"), "unknown"),
        power_type=power_type,
        max_kw=_max_kw(raw, power_type, issues),
        tariff_ids=[f"{tariff_prefix}:{tariff_id}" for tariff_id in raw.get("tariff_ids") or []],
    )


def _evse(raw: dict, fallback_time: datetime | None, prefix: str, issues: IssueLog) -> EVSE:
    status = EVSE_STATUSES.get(raw.get("status"))
    if status is None:
        issues.add(
            f"EVSE status {raw.get('status')!r} is not an OCPI 2.2.1 value; recorded as unknown"
        )
        status = "unknown"
    status_at = parse_ocpi_datetime(raw.get("last_updated")) or fallback_time
    if status != "unknown" and status_at is None:
        issues.add("EVSE status has no timestamp; recorded as unknown")
        status = "unknown"
    return EVSE(
        uid=raw["uid"],
        evse_id=raw.get("evse_id"),
        status=status,
        status_at=status_at,
        connectors=[_connector(c, prefix, issues) for c in raw.get("connectors") or []],
    )


def _opening_hours(raw: dict | None, issues: IssueLog) -> OpeningHours | None:
    if not raw:
        return None
    if raw.get("twentyfourseven"):
        return OpeningHours(twenty_four_seven=True)
    regular = [
        RegularHours(
            weekday=hours["weekday"],
            period_begin=hours["period_begin"],
            period_end=hours["period_end"],
        )
        for hours in raw.get("regular_hours") or []
    ]
    if not regular:
        issues.add("opening_times gives no hours; recorded as unknown")
        return None
    return OpeningHours(twenty_four_seven=False, regular_hours=regular)


def _country(value: object, issues: IssueLog) -> str | None:
    if value is None:
        return None
    if isinstance(value, str) and len(value) == 3 and value.isalpha() and value.isupper():
        return value
    issues.add(f"location country {value!r} is not ISO 3166-1 alpha-3; recorded as unknown")
    return None


def location_from_ocpi(
    raw: dict,
    config: OperatorConfig,
    *,
    source_url: str,
    fetched_at: datetime,
    issues: IssueLog,
) -> Location:
    """Convert one OCPI Location. Raises KeyError, TypeError or ValueError if unusable."""
    country, party = _party(raw, config)
    prefix = f"{config.id}:{country}:{party}"
    last_updated = parse_ocpi_datetime(raw.get("last_updated"))
    coordinates = raw["coordinates"]
    return Location(
        id=f"{prefix}:{raw['id']}",
        name=raw.get("name"),
        address=Address(
            street=raw.get("address"),
            city=raw.get("city"),
            postal_code=raw.get("postal_code"),
            country=_country(raw.get("country"), issues),
        ),
        coordinates=Coordinates(
            latitude=float(coordinates["latitude"]), longitude=float(coordinates["longitude"])
        ),
        time_zone=raw.get("time_zone"),
        operator=Operator(
            registry_id=config.id,
            name=(raw.get("operator") or {}).get("name") or config.display_name,
        ),
        opening_hours=_opening_hours(raw.get("opening_times"), issues),
        evses=[_evse(e, last_updated, prefix, issues) for e in raw.get("evses") or []],
        last_updated=last_updated,
        provenance=_provenance(config, source_url, fetched_at),
    )


def _restrictions(raw: dict | None, issues: IssueLog) -> TariffRestrictions | None:
    if not raw:
        return None
    for name in raw:
        if name not in (*RESTRICTION_FIELDS, "day_of_week", "reservation"):
            issues.add(f"tariff restriction {name!r} is not an OCPI 2.2.1 field; ignored")
    reservation = raw.get("reservation")
    if reservation is not None and reservation not in RESERVATIONS:
        raise ValueError(f"unknown reservation restriction {reservation!r}")
    return TariffRestrictions(
        **{name: raw[name] for name in RESTRICTION_FIELDS if raw.get(name) is not None},
        day_of_week=[day.lower() for day in raw.get("day_of_week") or []],
        reservation=RESERVATIONS.get(reservation) if reservation else None,
    )


def _english_text(entries: list[dict] | None) -> str | None:
    if not entries:
        return None
    for entry in entries:
        if str(entry.get("language", "")).lower().startswith("en"):
            return entry.get("text")
    return entries[0].get("text")


def tariff_from_ocpi(
    raw: dict,
    config: OperatorConfig,
    *,
    source_url: str,
    fetched_at: datetime,
    issues: IssueLog,
) -> Tariff:
    """Convert one OCPI Tariff. Raises KeyError, TypeError or ValueError if unusable."""
    country, party = _party(raw, config)
    tariff_type = raw.get("type")
    if tariff_type is not None and tariff_type not in TARIFF_TYPES:
        issues.add(f"tariff type {tariff_type!r} is not an OCPI 2.2.1 value; ignored")
    elements = [
        TariffElement(
            price_components=[
                PriceComponent(
                    type=DIMENSIONS[component["type"]],
                    price=component["price"],
                    vat=component.get("vat"),
                    step_size=component.get("step_size"),
                )
                for component in element["price_components"]
            ],
            restrictions=_restrictions(element.get("restrictions"), issues),
        )
        for element in raw.get("elements") or []
    ]
    return Tariff(
        id=f"{config.id}:{country}:{party}:{raw['id']}",
        currency=raw["currency"],
        type=TARIFF_TYPES.get(tariff_type) if tariff_type else None,
        elements=elements,
        min_price=(raw.get("min_price") or {}).get("excl_vat"),
        max_price=(raw.get("max_price") or {}).get("excl_vat"),
        alt_text=_english_text(raw.get("tariff_alt_text")),
        alt_url=raw.get("tariff_alt_url"),
        start_date_time=parse_ocpi_datetime(raw.get("start_date_time")),
        end_date_time=parse_ocpi_datetime(raw.get("end_date_time")),
        last_updated=parse_ocpi_datetime(raw.get("last_updated")),
        provenance=_provenance(config, source_url, fetched_at),
    )
