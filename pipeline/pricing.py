"""How prices are shown to people using the map.

The site is for a UK audience, so prices are only ever shown in pounds and pence. The
regulations describe the price in reference data as "the price in pence per kilowatt hour"
(Public Charge Point Regulations 2023, regulation 10(6)(d)(iv)).

- A tariff published in any currency other than GBP is shown as "Price unknown", with the
  reason. Prices are never converted: a converted figure is not what the operator charges.
- "Free" is shown only for a GBP tariff whose price_state is free_confirmed.
- Energy prices are shown in pence per kWh, as the blueprint asks. VAT is added only when
  every component that costs something states it. Otherwise prices are shown as
  published (OCPI prices exclude VAT) and marked "excluding VAT, VAT not stated".
- Sums are done in exact decimal arithmetic, so half pennies round up as expected.
- Reservation fees are not shown as charging prices.
- Prices that apply only at some times or after some time are shown with their
  conditions, read as OCPI 2.2.1 section 11 describes them: for each kind of charge, the
  first tariff element whose restrictions match applies, and an element with no
  restrictions after the others is the price "otherwise".
- When a site lists several tariffs, each is shown with how it is paid for (its OCPI
  type), what its price depends on, and, when energy prices can be compared on the same
  VAT basis, which listed tariff has the lowest energy price. Other charges are never
  folded into that comparison, so it says so.
"""

from collections.abc import Sequence
from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal, Protocol

from schema.models import PriceComponent, Tariff, TariffElement, TariffRestrictions

DISPLAY_CURRENCY = "GBP"
NON_ENERGY_UNITS = (
    ("flat", "per session"),
    ("time", "per hour charging"),
    ("parking_time", "per hour parked"),
)
# OCPI 2.2.1 section 11.4.7 (TariffType), in plain words.
TARIFF_KINDS = {
    "ad_hoc_payment": "Pay at the charger, for example by card",
    "regular": "With an account, app or card from a charging provider",
    "profile_cheap": "When the session is set to the cheapest charging",
    "profile_fast": "When the session is set to the fastest charging",
    "profile_green": "When the session is set to the greenest charging",
}
UNSTATED_KIND = "How to pay is not stated"
WEEK = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")


@dataclass(frozen=True)
class PriceDisplay:
    state: Literal["priced", "free", "unknown"]
    text: str
    reason: str | None = None


def _decimal(amount: float | Decimal) -> Decimal:
    return amount if isinstance(amount, Decimal) else Decimal(str(amount))


def pence(amount: float | Decimal) -> str:
    """0.45 becomes "45p"; 0.4917 becomes "49.2p"."""
    value = (_decimal(amount) * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return f"{value:f}".rstrip("0").rstrip(".") + "p"


def pounds(amount: float | Decimal) -> str:
    """1.5 becomes "£1.50"."""
    return f"£{_decimal(amount).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP):f}"


def _span(values: list[Decimal], fmt) -> str:
    low, high = min(values), max(values)
    return fmt(low) if low == high else f"{fmt(low)} to {fmt(high)}"


def _clock(value: str) -> str:
    return "midnight" if value == "00:00" else value


def _days(days: list[str]) -> str:
    chosen = [day for day in WEEK if day in days]
    if len(chosen) == 7:
        return ""
    if chosen == list(WEEK[:5]):
        return "on weekdays"
    if chosen == list(WEEK[5:]):
        return "at weekends"
    names = [day.capitalize() for day in chosen]
    return "on " + (names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}")


def _duration(seconds: int) -> str:
    for size, unit in ((3600, "hour"), (60, "minute"), (1, "second")):
        if seconds % size == 0:
            count = seconds // size
            return f"{count} {unit}" if count == 1 else f"{count} {unit}s"
    raise AssertionError("unreachable")


def conditions(restrictions: TariffRestrictions | None) -> str:
    """When a tariff element applies, in plain words, following OCPI 2.2.1 section 11.4.6."""
    if restrictions is None:
        return ""
    r = restrictions
    parts = []
    start, end = r.start_time, r.end_time
    if start and end and not (start == end == "00:00"):
        parts.append(f"from {_clock(start)} to {_clock(end)}")
    elif start and not end:
        parts.append(f"from {_clock(start)}")
    elif end and not start:
        parts.append(f"until {_clock(end)}")
    if r.day_of_week:
        parts.append(_days(r.day_of_week))
    if r.start_date:
        parts.append(f"from {r.start_date.day} {r.start_date:%B %Y}")
    if r.end_date:
        parts.append(f"before {r.end_date.day} {r.end_date:%B %Y}")
    if r.min_duration:
        parts.append(f"after {_duration(r.min_duration)}")
    if r.max_duration:
        parts.append(f"for the first {_duration(r.max_duration)}")
    if r.min_kwh:
        parts.append(f"after {r.min_kwh:g} kWh")
    if r.max_kwh:
        parts.append(f"for the first {r.max_kwh:g} kWh")
    if r.min_power:
        parts.append(f"while charging at {r.min_power:g} kW or more")
    if r.max_power:
        parts.append(f"while charging below {r.max_power:g} kW")
    if r.min_current:
        parts.append(f"while charging at {r.min_current:g} A or more")
    if r.max_current:
        parts.append(f"while charging below {r.max_current:g} A")
    return " ".join(part for part in parts if part)


def _charging_elements(tariff: Tariff) -> list[TariffElement]:
    return [e for e in tariff.elements if not (e.restrictions and e.restrictions.reservation)]


def _reachable(elements: list[TariffElement], kind: str) -> list[tuple[PriceComponent, str]]:
    """Components of one kind that can apply: those before and including the first element
    with no conditions. OCPI uses the first matching element, so later ones never apply."""
    found = []
    for element in elements:
        when = conditions(element.restrictions)
        found += [(c, when) for c in element.price_components if c.type == kind]
        if not when and any(c.type == kind for c in element.price_components):
            break
    return found


def _vat_stated(components: list[PriceComponent]) -> bool:
    # A zero price is zero with or without VAT, so only priced components decide this.
    return all(c.vat is not None for c in components if c.price > 0)


def _amount(component: PriceComponent, vat_stated: bool) -> Decimal:
    price = _decimal(component.price)
    if vat_stated and component.vat is not None:
        return price * (1 + _decimal(component.vat) / 100)
    return price


def _gbp_problem(tariff: Tariff) -> PriceDisplay | None:
    if tariff.currency != DISPLAY_CURRENCY:
        return PriceDisplay(
            "unknown",
            "Price unknown",
            f"The operator published this tariff in {tariff.currency}, not GBP. "
            "Prices are never converted.",
        )
    return None


def energy_range(tariff: Tariff) -> tuple[Decimal, Decimal, bool] | None:
    """Lowest and highest price per kWh that can apply, in pounds, and whether VAT is
    included. None when the tariff is not in GBP or gives no energy price."""
    if tariff.currency != DISPLAY_CURRENCY:
        return None
    elements = _charging_elements(tariff)
    vat_stated = _vat_stated([c for e in elements for c in e.price_components])
    energy = [_amount(c, vat_stated) for c, _ in _reachable(elements, "energy")]
    if not energy:
        return None
    return min(energy), max(energy), vat_stated


def describe_tariff(tariff: Tariff) -> PriceDisplay:
    """The price text the map shows for one tariff."""
    problem = _gbp_problem(tariff)
    if problem:
        return problem
    if tariff.price_state == "free_confirmed":
        return PriceDisplay("free", "Free")
    if tariff.price_state == "unknown":
        return PriceDisplay("unknown", "Price unknown", "The tariff has no price components.")

    elements = _charging_elements(tariff)
    if not elements:
        return PriceDisplay(
            "unknown", "Price unknown", "The tariff only gives prices for reservations."
        )
    vat_stated = _vat_stated([c for e in elements for c in e.price_components])

    parts = []
    for kind, unit, fmt in (
        ("energy", "per kWh", pence),
        *((k, u, pounds) for k, u in NON_ENERGY_UNITS),
    ):
        found = [
            (_amount(c, vat_stated), when)
            for c, when in _reachable(elements, kind)
            if kind == "energy" or c.price > 0
        ]
        pieces = [f"{fmt(amount)} {unit} {when}" for amount, when in found if when]
        plain = [amount for amount, when in found if not when]
        if plain:
            pieces.append(("otherwise " if pieces else "") + f"{_span(plain, fmt)} {unit}")
        if pieces:
            parts.append(", ".join(pieces))
    if not parts:
        return PriceDisplay("unknown", "Price unknown", "No charging price could be shown.")

    vat_note = "including VAT" if vat_stated else "(excluding VAT, VAT not stated)"
    # Semicolons separate kinds of charge when a list of conditional prices uses commas.
    joiner = "; plus " if any(", " in part for part in parts) else ", plus "
    text = f"{joiner.join(parts)} {vat_note}"
    if tariff.min_price:
        text += f"; minimum charge {pounds(tariff.min_price)} excluding VAT"
    return PriceDisplay("priced", text)


class ConnectorPriceLike(Protocol):
    state: str
    energy_low: Decimal | None
    energy_high: Decimal | None
    includes_vat: bool | None


def location_summary(prices: Sequence[ConnectorPriceLike]) -> str:
    """One line about the prices at a location, for the map's list. "Free" only when every
    connector is free_confirmed; a mix says which parts are free, priced or unknown. Only
    energy prices are summarised, so the line starts "Energy"; the details give the rest."""
    if not prices:
        return "Price unknown"
    states = {p.state for p in prices}
    if states == {"free_confirmed"}:
        return "Free (confirmed)"
    energy = [p for p in prices if p.state == "priced" and p.energy_low is not None]
    with_vat = [p for p in energy if p.includes_vat]
    without_vat = [p for p in energy if not p.includes_vat]
    parts = []
    for group, note in (
        (with_vat, "including VAT"),
        (without_vat, "excluding VAT, VAT not stated"),
    ):
        if group:
            low = min(p.energy_low for p in group)
            high = max(p.energy_high for p in group)
            parts.append(f"{_span([low, high], pence)} per kWh {note}")
    if parts:
        parts[0] = f"Energy {parts[0]}"
    elif "priced" in states:
        parts.append("Priced: see details")
    if "free_confirmed" in states:
        parts.append("some connectors free (confirmed)")
    if "unknown" in states:
        parts.append("some prices unknown" if parts else "Price unknown")
    text = "; ".join(parts)
    return text[0].upper() + text[1:]


def tariff_kind(tariff: Tariff) -> str:
    """How a tariff is paid for, from its OCPI type."""
    return TARIFF_KINDS.get(tariff.type or "", UNSTATED_KIND)


def varies_with(tariff: Tariff) -> list[str]:
    """What a tariff's charging price depends on, in plain words, in a fixed order. Empty
    when the same price applies all the time."""
    found: set[str] = set()
    for element in _charging_elements(tariff):
        r = element.restrictions
        if r is None:
            continue
        if (r.start_time or r.end_time) and not (r.start_time == r.end_time == "00:00"):
            found.add("time of day")
        if r.day_of_week and len(set(r.day_of_week)) < 7:
            found.add("day of the week")
        if r.start_date or r.end_date:
            found.add("date")
        if r.min_duration or r.max_duration:
            found.add("how long the session lasts")
        if r.min_kwh or r.max_kwh:
            found.add("how much energy you use")
        if r.min_power or r.max_power or r.min_current or r.max_current:
            found.add("charging speed")
    order = (
        "time of day",
        "day of the week",
        "date",
        "how long the session lasts",
        "how much energy you use",
        "charging speed",
    )
    return [item for item in order if item in found]


def varies_text(items: list[str]) -> str | None:
    """ "Price depends on time of day and day of the week." or None."""
    if not items:
        return None
    joined = items[0] if len(items) == 1 else f"{', '.join(items[:-1])} and {items[-1]}"
    return f"Price depends on {joined}."


class TariffOptionLike(Protocol):
    kind: str
    state: str
    energy_low: Decimal | None
    energy_high: Decimal | None
    includes_vat: bool | None


def comparison(options: Sequence[TariffOptionLike]) -> str | None:
    """A line about which listed tariff has the lowest energy price, or None when that
    cannot be said fairly: fewer than two priced tariffs with an energy price, or prices
    on different VAT bases. Other charges are not compared, and the line says so."""
    priced = [o for o in options if o.state == "priced" and o.energy_low is not None]
    if len(priced) < 2 or len({bool(o.includes_vat) for o in priced}) != 1:
        return None
    vat = "including VAT" if priced[0].includes_vat else "excluding VAT, VAT not stated"
    rest = "Other charges, such as fees per session or per hour, are not compared."
    low = min(o.energy_low for o in priced)
    if all(o.energy_low == o.energy_high == low for o in priced):
        return f"Every priced tariff here charges {pence(low)} per kWh {vat}. {rest}"
    cheapest = [o for o in priced if o.energy_low == low]
    kinds = {o.kind for o in cheapest}
    kind = kinds.pop() if len(kinds) == 1 else UNSTATED_KIND
    which = "" if kind == UNSTATED_KIND else f" ({kind[0].lower()}{kind[1:]})"
    when = " at some times" if all(o.energy_high != low for o in cheapest) else ""
    return f"Lowest energy price listed here: {pence(low)} per kWh {vat}{when}{which}. {rest}"
