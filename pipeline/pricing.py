"""How prices are shown to people using the map.

The site is for a UK audience, so prices are only ever shown in pounds and pence. The
regulations describe the price in reference data as "the price in pence per kilowatt hour"
(Public Charge Point Regulations 2023, regulation 10(6)(d)(iv)).

- A tariff published in any currency other than GBP is shown as "Price unknown", with the
  reason. Prices are never converted: a converted figure is not what the operator charges.
- "Free" is shown only for a GBP tariff whose price_state is free_confirmed, and never for
  one the owner has named in zero_price_tariffs in the operator file (ADR 0022), which
  shows "Price unknown" while its prices are all zero.
- Energy prices are shown in pence per kWh, as the blueprint asks. VAT is added only when
  every component that costs something states it. Otherwise prices are shown as
  published (OCPI prices exclude VAT) and marked "excluding VAT, VAT not stated".
- Where the owner has recorded vat_not_stated in the operator file (ADR 0003, amended 22
  October 2026), its rate is added to each component that gives no VAT figure
  (`added_vat`), and the price says this project added it.
- Where the owner has recorded vat_in_price in the operator file (ADR 0003, amended 23
  October 2026), `added_vat` is VAT_IN_PRICE: a component's stated VAT is read as already
  in its price, so nothing is added, and the price says it was read that way.
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
- The label above a point on the map (ADR 0026) is the lowest price per kWh a connector's
  tariffs give, marked "from" when it applies only in some cases and "excl. VAT" when VAT
  is not stated (and not added by the owner's decision), or "Free" when the connector is
  confirmed free. A price that would show as "0p" is never a label.
"""

import html
import re
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
# `added_vat` when the operator file records vat_in_price: stated VAT is already in prices.
VAT_IN_PRICE: Literal["in_price"] = "in_price"
VatReading = float | Literal["in_price"] | None
IN_PRICE_NOTE = "including VAT, reading the VAT rate the feed states as already in the price"
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


def _rate(component: PriceComponent, added_vat: VatReading) -> float | None:
    # The component's own VAT figure, or the rate the owner decided to add when it has none.
    if component.vat is not None or added_vat == VAT_IN_PRICE:
        return component.vat
    return added_vat


def _vat_stated(components: list[PriceComponent], added_vat: VatReading = None) -> bool:
    # A zero price is zero with or without VAT, so only priced components decide this.
    return all(_rate(c, added_vat) is not None for c in components if c.price > 0)


def _vat_added(components: list[PriceComponent], added_vat: VatReading) -> bool:
    if added_vat is None or added_vat == VAT_IN_PRICE:
        return False
    return any(c.vat is None for c in components if c.price > 0)


def _amount(component: PriceComponent, vat_stated: bool, added_vat: VatReading = None) -> Decimal:
    price = _decimal(component.price)
    rate = _rate(component, added_vat)
    if vat_stated and rate is not None and added_vat != VAT_IN_PRICE:
        return price * (1 + _decimal(rate) / 100)
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


def energy_range(
    tariff: Tariff, added_vat: VatReading = None
) -> tuple[Decimal, Decimal, bool] | None:
    """Lowest and highest price per kWh that can apply, in pounds, and whether VAT is
    included. added_vat is the rate from the operator's vat_not_stated decision, or
    VAT_IN_PRICE from its vat_in_price decision, if any. None when the tariff is not in GBP
    or gives no energy price."""
    if tariff.currency != DISPLAY_CURRENCY:
        return None
    elements = _charging_elements(tariff)
    vat_stated = _vat_stated([c for e in elements for c in e.price_components], added_vat)
    energy = [_amount(c, vat_stated, added_vat) for c, _ in _reachable(elements, "energy")]
    if not energy:
        return None
    return min(energy), max(energy), vat_stated


def energy_always(tariff: Tariff) -> bool:
    """Whether the tariff gives a price per kWh whatever the time, speed or amount: an
    element with no conditions has one."""
    return any(not when for _, when in _reachable(_charging_elements(tariff), "energy"))


ZERO_PRICE_WITHHELD = (
    "Every price in this tariff is zero, but the repository owner decided not to show it as "
    "free (zero_price_tariffs in the operator file)."
)


def describe_tariff(
    tariff: Tariff, *, zero_price_withheld: bool = False, added_vat: VatReading = None
) -> PriceDisplay:
    """The price text the map shows for one tariff. zero_price_withheld is True only for a
    tariff the owner names in zero_price_tariffs (ADR 0022). added_vat is the rate from
    the operator's vat_not_stated decision, or VAT_IN_PRICE from its vat_in_price
    decision, if any."""
    problem = _gbp_problem(tariff)
    if problem:
        return problem
    if tariff.price_state == "free_confirmed":
        if zero_price_withheld:
            return PriceDisplay("unknown", "Price unknown", ZERO_PRICE_WITHHELD)
        return PriceDisplay("free", "Free")
    if tariff.price_state == "unknown":
        return PriceDisplay("unknown", "Price unknown", "The tariff has no price components.")

    elements = _charging_elements(tariff)
    if not elements:
        return PriceDisplay(
            "unknown", "Price unknown", "The tariff only gives prices for reservations."
        )
    components = [c for e in elements for c in e.price_components]
    vat_stated = _vat_stated(components, added_vat)
    vat_added = _vat_added(components, added_vat)

    parts = []
    for kind, unit, fmt in (
        ("energy", "per kWh", pence),
        *((k, u, pounds) for k, u in NON_ENERGY_UNITS),
    ):
        found = [
            (_amount(c, vat_stated, added_vat), when)
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
    if vat_added:
        vat_note = (
            f"including VAT, with VAT at {added_vat:g}% added by this project where the "
            "operator's feed does not state it"
        )
    elif vat_stated and added_vat == VAT_IN_PRICE:
        vat_note = IN_PRICE_NOTE
    # Semicolons separate kinds of charge when a list of conditional prices uses commas.
    joiner = "; plus " if any(", " in part for part in parts) else ", plus "
    text = f"{joiner.join(parts)} {vat_note}"
    if tariff.min_price and added_vat == VAT_IN_PRICE:
        text += f"; minimum charge {pounds(tariff.min_price)} {IN_PRICE_NOTE}"
    elif tariff.min_price and added_vat is not None:
        minimum = _decimal(tariff.min_price) * (1 + _decimal(added_vat) / 100)
        text += f"; minimum charge {pounds(minimum)} including VAT added by this project"
    elif tariff.min_price:
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


_UUID = re.compile(r"[_\s-]*[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)
_CAMEL = re.compile(r"(?<=[a-z])(?=[A-Z][a-z])")
# HTML tags, which OCPI 2.2.1 display text should not carry ("No markup, html etc. allowed").
_MARKUP = re.compile(r"</?[a-z][a-z0-9]*(?:\s[^<>]*)?/?>", re.I)


def readable_name(text: str | None) -> str | None:
    """A tariff description that is easier to read, when the operator's own text looks like
    a system name such as "Tariff_Contactless_Rapid7ab83c27-57b5-...": the trailing id and
    a leading "Tariff" are dropped and the words are split, giving "Contactless rapid".
    HTML tags such as <div> and <br> are taken out, leaving the words between them.
    Text that already reads as words is kept exactly. None when nothing readable is left.
    The original is always published next to it, so nothing the operator said is lost."""
    if text and _MARKUP.search(text):
        text = " ".join(html.unescape(_MARKUP.sub(" ", text)).split())
    if not text:
        return None
    stripped = _UUID.sub("", text.strip())
    if stripped == text.strip() and "_" not in stripped:
        return text.strip()
    stripped = re.sub(r"^tariff(?=[_\s]|$)", "", stripped, flags=re.I)
    parts = [p for p in re.split(r"[_\s]+", stripped) if p]
    words = [
        " ".join(
            w if w.isupper() or any(c.isdigit() for c in w) else w.lower()
            for w in _CAMEL.split(part)
        )
        for part in parts
    ]
    if not words:
        return None
    label = " ".join(words)
    return label[0].upper() + label[1:]


def map_label(
    state: str, lowest: Decimal | None, includes_vat: bool | None, varies: bool
) -> str | None:
    """The short price drawn above a point on the map for one connector (ADR 0026): "Free"
    only for a connector whose price state is free_confirmed, otherwise the lowest price per
    kWh any of its tariffs gives, such as "56p", "from 32.5p" when that price applies only
    in some cases, and "excl. VAT" when VAT is not stated. None when there is no such
    price. Other charges are left out: the details show them."""
    if state == "free_confirmed":
        return "Free"
    if lowest is None:
        return None
    text = f"from {pence(lowest)}" if varies else pence(lowest)
    return text if includes_vat else f"{text} excl. VAT"


def shows_as_zero(amount: float | Decimal) -> bool:
    """Whether a price per kWh would be shown as "0p". Such a price is never put in a label,
    because "0p" reads as free and only free_confirmed is ever called free."""
    return pence(amount) == pence(0)


def plan_label(
    price_per_kwh: Decimal | None, includes_vat: bool | None, only_at_some_times: bool = False
) -> str | None:
    """The short price drawn on the map for a plan the visitor ticked: its fixed price per
    kWh, only when the provider says it includes VAT, marked "from" when the plan applies
    only at some times. None otherwise, and for a price that would show as "0p"."""
    if price_per_kwh is None or includes_vat is not True or shows_as_zero(price_per_kwh):
        return None
    text = pence(price_per_kwh)
    return f"from {text}" if only_at_some_times else text


def plan_fee_text(monthly_fee: Decimal | None) -> str:
    """ "£9.99 a month", "No monthly fee" or "Monthly fee not published"."""
    if monthly_fee is None:
        return "Monthly fee not published"
    if monthly_fee == 0:
        return "No monthly fee"
    return f"{pounds(monthly_fee)} a month"


def plan_price_text(
    price_per_kwh: Decimal | None,
    discount_percent: Decimal | None,
    discount_of: str | None,
    includes_vat: bool | None,
) -> str:
    """The price a charging plan gives, as its provider publishes it: a fixed price per kWh
    or a discount off another price. Discounts are never turned into a price here, because
    the price they are taken off is often only shown in the provider's app."""
    if price_per_kwh is not None:
        vat = {True: "including VAT", False: "excluding VAT"}.get(includes_vat, "(VAT not stated)")
        return f"{pence(price_per_kwh)} per kWh {vat}"
    if discount_percent is not None:
        return f"{discount_percent:g}% off {discount_of}"
    return "Price per kWh not published"
