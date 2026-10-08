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
"""

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

from schema.models import PriceComponent, Tariff

DISPLAY_CURRENCY = "GBP"
NON_ENERGY_UNITS = (
    ("flat", "per session"),
    ("time", "per hour charging"),
    ("parking_time", "per hour parked"),
)


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


def describe_tariff(tariff: Tariff) -> PriceDisplay:
    """The price text the map shows for one tariff."""
    if tariff.currency != DISPLAY_CURRENCY:
        return PriceDisplay(
            "unknown",
            "Price unknown",
            f"The operator published this tariff in {tariff.currency}, not GBP. "
            "Prices are never converted.",
        )
    if tariff.price_state == "free_confirmed":
        return PriceDisplay("free", "Free")
    if tariff.price_state == "unknown":
        return PriceDisplay("unknown", "Price unknown", "The tariff has no price components.")

    components: list[PriceComponent] = [
        component
        for element in tariff.elements
        if not (element.restrictions and element.restrictions.reservation)
        for component in element.price_components
    ]
    if not components:
        return PriceDisplay(
            "unknown", "Price unknown", "The tariff only gives prices for reservations."
        )

    # A zero price is zero with or without VAT, so only priced components decide this.
    vat_stated = all(c.vat is not None for c in components if c.price > 0)

    def amount(component: PriceComponent) -> Decimal:
        price = _decimal(component.price)
        if vat_stated and component.vat is not None:
            return price * (1 + _decimal(component.vat) / 100)
        return price

    parts = []
    energy = [amount(c) for c in components if c.type == "energy"]
    if energy:
        parts.append(f"{_span(energy, pence)} per kWh")
    for kind, unit in NON_ENERGY_UNITS:
        values = [amount(c) for c in components if c.type == kind and c.price > 0]
        if values:
            parts.append(f"{_span(values, pounds)} {unit}")
    if not parts:
        return PriceDisplay("unknown", "Price unknown", "No charging price could be shown.")

    vat_note = "including VAT" if vat_stated else "(excluding VAT, VAT not stated)"
    text = f"{', plus '.join(parts)} {vat_note}"
    if tariff.min_price:
        text += f"; minimum charge {pounds(tariff.min_price)} excluding VAT"
    return PriceDisplay("priced", text)
