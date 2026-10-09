"""Work out the price shown for each connector from the tariffs it refers to.

Blueprint task 6. For each connector:

- No tariff listed: "Price unknown". OCPI 2.2.1 says a free connector should still point
  to a free tariff, so a missing tariff is never read as free.
- Tariff ids that cannot be found among the operator's tariffs are "unresolvable" and
  logged. If none can be found, the price is unknown.
- When several tariffs apply, ones of type ad_hoc_payment are preferred, because that is
  the price someone pays at the charger without an account. Otherwise all are used.
- "Free" (price_state free_confirmed) only when every listed tariff was found and every
  one is confirmed free. One tariff that could not be read is enough to withhold "Free".
- The indicative price per kWh is the lowest and highest energy price that can apply,
  including VAT when the operator states it. It is a guide for filters and map labels;
  the text from pipeline.pricing is what explains the price.

For a site's details, site_tariffs lists every tariff its connectors refer to, not only
the preferred ones, so people can compare them: each with how it is paid for, its price,
what the price depends on (time of day, day of the week and so on) and how many of the
site's connectors list it. Tariffs that could not be found are listed as unknown.

Prices are only ever worded by pipeline.pricing.
"""

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Literal

from pipeline.pricing import (
    UNSTATED_KIND,
    comparison,
    describe_tariff,
    energy_range,
    pence,
    tariff_kind,
    varies_text,
    varies_with,
)
from schema.models import Connector, Location, PriceState, Tariff


@dataclass(frozen=True)
class ConnectorPrice:
    location_id: str
    evse_uid: str
    connector_id: str
    state: PriceState
    text: str
    reason: str | None = None
    tariff_ids: list[str] = field(default_factory=list)
    unresolved_ids: list[str] = field(default_factory=list)
    energy_low: Decimal | None = None
    energy_high: Decimal | None = None
    includes_vat: bool | None = None

    @property
    def indicative(self) -> str | None:
        """A short label such as "49.2p/kWh" or "32.5p to 49.2p/kWh (excl. VAT)"."""
        if self.energy_low is None or self.energy_high is None:
            return None
        low, high = pence(self.energy_low), pence(self.energy_high)
        span = low if low == high else f"{low} to {high}"
        return f"{span}/kWh" + ("" if self.includes_vat else " (excl. VAT)")


UNKNOWN: Literal["unknown"] = "unknown"


def _candidates(tariffs: list[Tariff]) -> list[Tariff]:
    ad_hoc = [t for t in tariffs if t.type == "ad_hoc_payment"]
    return ad_hoc or tariffs


def price_connector(
    connector: Connector, tariffs: dict[str, Tariff], *, location_id: str, evse_uid: str
) -> ConnectorPrice:
    """The price for one connector, using a dictionary of the operator's tariffs by id."""
    where = {"location_id": location_id, "evse_uid": evse_uid, "connector_id": connector.id}
    if not connector.tariff_ids:
        return ConnectorPrice(
            **where, state=UNKNOWN, text="Price unknown", reason="No tariff is listed."
        )
    found = [tariffs[i] for i in connector.tariff_ids if i in tariffs]
    unresolved = [i for i in connector.tariff_ids if i not in tariffs]
    if not found:
        return ConnectorPrice(
            **where,
            state=UNKNOWN,
            text="Price unknown",
            reason="None of the listed tariffs was found in the operator's tariff data.",
            unresolved_ids=unresolved,
        )

    chosen = _candidates(found)
    shown = [describe_tariff(t) for t in chosen]
    ids = [t.id for t in chosen]
    ranges = [r for r in (energy_range(t) for t in chosen) if r is not None]
    energy = {}
    if ranges:
        energy = {
            "energy_low": min(r[0] for r in ranges),
            "energy_high": max(r[1] for r in ranges),
            "includes_vat": all(r[2] for r in ranges),
        }

    if all(d.state == "free" for d in shown):
        if unresolved:
            return ConnectorPrice(
                **where,
                state=UNKNOWN,
                text="Price unknown",
                reason="Some listed tariffs could not be read, so free cannot be confirmed.",
                tariff_ids=ids,
                unresolved_ids=unresolved,
            )
        return ConnectorPrice(
            **where, state="free_confirmed", text="Free", tariff_ids=ids, **energy
        )

    priced = [d for d in shown if d.state == "priced"]
    if not priced:
        return ConnectorPrice(
            **where,
            state=UNKNOWN,
            text="Price unknown",
            reason=shown[0].reason,
            tariff_ids=ids,
            unresolved_ids=unresolved,
        )
    texts = list(dict.fromkeys(d.text for d in priced))
    text = texts[0] if len(texts) == 1 else f"{len(texts)} tariffs: " + " | ".join(texts)
    reason = "Some listed tariffs could not be read." if unresolved else None
    return ConnectorPrice(
        **where,
        state="priced",
        text=text,
        reason=reason,
        tariff_ids=ids,
        unresolved_ids=unresolved,
        **energy,
    )


@dataclass(frozen=True)
class TariffOption:
    """One tariff listed at a site, for its details."""

    tariff_id: str
    name: str | None
    kind: str
    state: Literal["priced", "free", "unknown"]
    text: str
    reason: str | None = None
    varies: str | None = None
    connectors: int = 0
    energy_low: Decimal | None = None
    energy_high: Decimal | None = None
    includes_vat: bool | None = None


@dataclass(frozen=True)
class SiteTariffs:
    options: list[TariffOption]
    comparison: str | None
    connectors: int


def _option(tariff: Tariff, count: int) -> TariffOption:
    shown = describe_tariff(tariff)
    energy = energy_range(tariff)
    return TariffOption(
        tariff_id=tariff.id,
        name=tariff.alt_text,
        kind=tariff_kind(tariff),
        state=shown.state,
        text=shown.text,
        reason=shown.reason,
        varies=varies_text(varies_with(tariff)) if shown.state == "priced" else None,
        connectors=count,
        energy_low=energy[0] if energy else None,
        energy_high=energy[1] if energy else None,
        includes_vat=energy[2] if energy else None,
    )


def site_tariffs(location: Location, tariffs: dict[str, Tariff]) -> SiteTariffs:
    """Every tariff the location's connectors list, in the order they are first listed."""
    connectors = [c for evse in location.evses for c in evse.connectors]
    counts: dict[str, int] = {}
    for connector in connectors:
        for tariff_id in dict.fromkeys(connector.tariff_ids):
            counts[tariff_id] = counts.get(tariff_id, 0) + 1
    options = [
        _option(tariffs[i], n)
        if i in tariffs
        else TariffOption(
            tariff_id=i,
            name=None,
            kind=UNSTATED_KIND,
            state=UNKNOWN,
            text="Price unknown",
            reason="This tariff is listed but could not be read from the operator's tariff data.",
            connectors=n,
        )
        for i, n in counts.items()
    ]
    return SiteTariffs(options, comparison(options), len(connectors))


def price_locations(locations: list[Location], tariffs: list[Tariff]) -> list[ConnectorPrice]:
    """The price for every connector at every location, in order."""
    index = {tariff.id: tariff for tariff in tariffs}
    return [
        price_connector(connector, index, location_id=location.id, evse_uid=evse.uid)
        for location in locations
        for evse in location.evses
        for connector in evse.connectors
    ]


def summary(prices: list[ConnectorPrice]) -> str:
    """One line for run reports, including the share of connectors with a resolvable tariff."""
    if not prices:
        return "prices: no connectors"
    states = {
        state: sum(p.state == state for p in prices) for state in ("priced", "free_confirmed")
    }
    resolvable = sum(bool(p.tariff_ids) for p in prices)
    share = round(100 * resolvable / len(prices))
    unknown = len(prices) - states["priced"] - states["free_confirmed"]
    return (
        f"prices: {states['priced']} priced, {states['free_confirmed']} free, {unknown} unknown "
        f"({share}% of {len(prices)} connectors have a tariff that was found)"
    )
