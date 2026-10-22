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
- A tariff the owner names in zero_price_tariffs (ADR 0022) shows "Price unknown" while
  its prices are all zero, and gives no indicative price. withheld_free_tariffs finds them
  among the operator's own tariffs by exact OCPI id.
- A tariff from an operator whose file records vat_not_stated (ADR 0003, amended 22
  October 2026) has that rate of VAT added to each price with no VAT figure. `added_vat`
  maps each such operator's id to its rate, and a tariff is matched by the operator whose
  feed published it, so a related operator's tariff follows its own operator's file.
- The indicative price per kWh is the lowest and highest energy price that can apply,
  including VAT when the operator states it. It is a guide for filters and map labels;
  the text from pipeline.pricing is what explains the price.
- The label above a point on the map (ADR 0026) uses the lowest price per kWh among every
  tariff the connector lists, not only the preferred ones, because people can pay with
  the operator's app or account as well as at the charger (see lowest_energy).

For a site's details, site_tariffs lists every tariff its connectors refer to, not only
the preferred ones, so people can compare them: each with how it is paid for, its price,
what the price depends on (time of day, day of the week and so on) and how many of the
site's connectors list it. Tariffs that could not be found are listed as unknown.

Only where the owner has recorded tariffs_from in the operator file (ADR 0020),
related_tariffs finds tariffs a connector names that only a related operator's feed
holds: the exact same OCPI id, which must be a UUID, with the same country code, in
exactly one related operator's tariffs, and never in the operator's own. Names and
descriptions are never compared.

Prices are only ever worded by pipeline.pricing.
"""

import re
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from decimal import ROUND_HALF_UP, Decimal
from types import MappingProxyType
from typing import Literal

from pipeline.pricing import (
    UNSTATED_KIND,
    comparison,
    describe_tariff,
    energy_always,
    energy_range,
    map_label,
    pence,
    readable_name,
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
    # From lowest_energy over every tariff the connector lists, for the map's label.
    lowest: Decimal | None = None
    lowest_vat: bool | None = None
    lowest_varies: bool = False

    @property
    def label(self) -> str | None:
        """The short price drawn above the location's point on the map (ADR 0026)."""
        return map_label(self.state, self.lowest, self.lowest_vat, self.lowest_varies)

    @property
    def indicative(self) -> str | None:
        """A short label such as "49.2p/kWh" or "32.5p to 49.2p/kWh (excl. VAT)"."""
        if self.energy_low is None or self.energy_high is None:
            return None
        low, high = pence(self.energy_low), pence(self.energy_high)
        span = low if low == high else f"{low} to {high}"
        return f"{span}/kWh" + ("" if self.includes_vat else " (excl. VAT)")


UNKNOWN: Literal["unknown"] = "unknown"
NO_VAT_ADDED: Mapping[str, float] = MappingProxyType({})


def _added(tariff: Tariff, added_vat: Mapping[str, float]) -> float | None:
    # The VAT rate the owner decided to add to the publishing operator's prices, if any.
    return added_vat.get(tariff.provenance.source_id)


def _in_force(tariff: Tariff) -> bool:
    # Within its own validity dates when it was fetched (OCPI 2.2.1 lets a connector list
    # an old and a new tariff side by side).
    when = tariff.provenance.fetched_at
    started = tariff.start_date_time is None or tariff.start_date_time <= when
    return started and (tariff.end_date_time is None or tariff.end_date_time > when)


def _as_shown(amount: Decimal) -> Decimal:
    # To the tenth of a penny a label shows, so ties are judged on what people see.
    return amount.quantize(Decimal("0.001"), rounding=ROUND_HALF_UP)


def lowest_energy(
    tariffs: list[Tariff], added_vat: Mapping[str, float] = NO_VAT_ADDED
) -> tuple[Decimal, bool, bool] | None:
    """The lowest price per kWh that any of these tariffs gives, to the tenth of a penny,
    whether it includes VAT, and whether it applies only in some cases (every tariff giving
    it charges more per kWh, or not per kWh, at other times, speeds or amounts), for the
    label above a point on the map (ADR 0026). Only priced GBP tariffs within their
    validity dates count. A tariff that charges nothing per kWh at all (only by time or
    per session) is left out. When a tariff is free, or free per kWh only at some times,
    there is no label, because "0p" reads as free and only free_confirmed is ever called
    free. The lowest figure wins whether or not its VAT is stated: VAT is added only by the
    owner's vat_not_stated decision (`added_vat`), and a higher price including VAT could
    be the dearer one. On a tie, the price including VAT is used."""
    ranges = []
    for tariff in tariffs:
        if not _in_force(tariff):
            continue
        if tariff.price_state == "free_confirmed":
            return None
        priced = tariff.price_state == "priced"
        found = energy_range(tariff, _added(tariff, added_vat)) if priced else None
        if found is None:
            continue
        low, high, vat = _as_shown(found[0]), _as_shown(found[1]), found[2]
        if low == 0 and high > 0:
            return None
        if low > 0:
            ranges.append((low, vat, high != low or not energy_always(tariff)))
    if not ranges:
        return None
    low = min(r[0] for r in ranges)
    at_low = [r for r in ranges if r[0] == low]
    with_vat = any(r[1] for r in at_low)
    varies = all(r[2] for r in at_low if r[1] == with_vat)
    return low, with_vat, varies


def _candidates(tariffs: list[Tariff]) -> list[Tariff]:
    ad_hoc = [t for t in tariffs if t.type == "ad_hoc_payment"]
    return ad_hoc or tariffs


def withheld_free_tariffs(tariffs: list[Tariff], ocpi_ids: list[str]) -> frozenset[str]:
    """Record ids of the operator's own tariffs (`tariffs`) that a zero_price_tariffs
    decision names (`ocpi_ids`, exact OCPI ids) and that are confirmed free as published
    (ADR 0022). Names are never compared."""
    wanted = set(ocpi_ids)
    return frozenset(
        tariff.id
        for tariff in tariffs
        if tariff.price_state == "free_confirmed"
        and (parts := _parts(tariff.id)) is not None
        and parts[2] in wanted
    )


def price_connector(
    connector: Connector,
    tariffs: dict[str, Tariff],
    *,
    location_id: str,
    evse_uid: str,
    withheld: frozenset[str] = frozenset(),
    added_vat: Mapping[str, float] = NO_VAT_ADDED,
) -> ConnectorPrice:
    """The price for one connector, using a dictionary of the operator's tariffs by id.
    `withheld` holds the ids from withheld_free_tariffs; `added_vat` the VAT rates from
    vat_not_stated decisions, by operator id."""
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

    cheapest = lowest_energy([t for t in found if t.id not in withheld], added_vat)
    lowest = {}
    if cheapest:
        lowest = dict(zip(("lowest", "lowest_vat", "lowest_varies"), cheapest, strict=True))
    chosen = _candidates(found)
    shown = [
        describe_tariff(t, zero_price_withheld=t.id in withheld, added_vat=_added(t, added_vat))
        for t in chosen
    ]
    ids = [t.id for t in chosen]
    priceable = [t for t in chosen if t.id not in withheld]
    ranges = [r for r in (energy_range(t, _added(t, added_vat)) for t in priceable) if r]
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
            **where, state="free_confirmed", text="Free", tariff_ids=ids, **energy, **lowest
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
        **lowest,
    )


@dataclass(frozen=True)
class TariffOption:
    """One tariff listed at a site, for its details."""

    tariff_id: str
    name: str | None
    kind: str
    state: Literal["priced", "free", "unknown"]
    text: str
    original_name: str | None = None
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


def _option(
    tariff: Tariff, count: int, withheld: frozenset[str], added_vat: Mapping[str, float]
) -> TariffOption:
    vat = _added(tariff, added_vat)
    shown = describe_tariff(tariff, zero_price_withheld=tariff.id in withheld, added_vat=vat)
    energy = None if tariff.id in withheld else energy_range(tariff, vat)
    return TariffOption(
        tariff_id=tariff.id,
        name=readable_name(tariff.alt_text),
        original_name=(
            tariff.alt_text if readable_name(tariff.alt_text) != tariff.alt_text else None
        ),
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


def _cheapest_first(option: TariffOption) -> tuple:
    """Sort key: confirmed free first, then energy prices including VAT from lowest to
    highest, then energy prices excluding VAT or with VAT not stated (not comparable with
    the first group), then priced tariffs with no energy price, then unknown prices."""
    if option.state == "free":
        return (0, Decimal(0), Decimal(0))
    if option.state == "priced" and option.energy_low is not None:
        high = option.energy_high if option.energy_high is not None else option.energy_low
        return (1 if option.includes_vat else 2, option.energy_low, high)
    return (3 if option.state == "priced" else 4, Decimal(0), Decimal(0))


def site_tariffs(
    location: Location,
    tariffs: dict[str, Tariff],
    withheld: frozenset[str] = frozenset(),
    added_vat: Mapping[str, float] = NO_VAT_ADDED,
) -> SiteTariffs:
    """Every tariff the location's connectors list, cheapest first (see _cheapest_first);
    tariffs that sort the same keep the order they are first listed in. `withheld` holds
    the ids from withheld_free_tariffs; `added_vat` the VAT rates from vat_not_stated
    decisions, by operator id."""
    connectors = [c for evse in location.evses for c in evse.connectors]
    counts: dict[str, int] = {}
    for connector in connectors:
        for tariff_id in dict.fromkeys(connector.tariff_ids):
            counts[tariff_id] = counts.get(tariff_id, 0) + 1
    options = [
        _option(tariffs[i], n, withheld, added_vat)
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
    options.sort(key=_cheapest_first)
    return SiteTariffs(options, comparison(options), len(connectors))


# An OCPI id in the form of a UUID names one record, so a match cannot be a coincidence.
UUID = re.compile(r"^[0-9a-fA-F]{8}(-[0-9a-fA-F]{4}){3}-[0-9a-fA-F]{12}$")


def _parts(record_id: str) -> tuple[str, str, str] | None:
    """(country code, party id, OCPI id) of an id made by the OCPI adapter, else None."""
    parts = record_id.split(":", 3)
    return (parts[1], parts[2], parts[3]) if len(parts) == 4 else None


def related_tariffs(
    locations: list[Location], own: list[Tariff], related: dict[str, list[Tariff]]
) -> dict[str, Tariff]:
    """Tariffs from related operators' feeds (`related`, by operator id) for the tariff ids
    connectors name that the operator's own tariffs (`own`) do not have, keyed by the id
    the connector names (ADR 0020). Use only where the owner has recorded tariffs_from.

    A connector's tariff id is matched only when its OCPI id is a UUID, no tariff in the
    operator's own response has that OCPI id under any country or party code, and exactly
    one tariff among all the related operators' responses has it, with the same country
    code. Anything else stays unresolved. Names and descriptions are never compared.
    """
    own_ids = {parts[2] for parts in map(_parts, (t.id for t in own)) if parts}
    by_id: dict[str, list[Tariff]] = defaultdict(list)
    for tariffs in related.values():
        for tariff in tariffs:
            parts = _parts(tariff.id)
            if parts:
                by_id[parts[2]].append(tariff)
    found: dict[str, Tariff] = {}
    for location in locations:
        for evse in location.evses:
            for connector in evse.connectors:
                for tariff_id in connector.tariff_ids:
                    parts = _parts(tariff_id)
                    if parts is None or parts[2] in own_ids or not UUID.match(parts[2]):
                        continue
                    matches = by_id.get(parts[2], [])
                    if len(matches) == 1 and _parts(matches[0].id)[0] == parts[0]:
                        found[tariff_id] = matches[0]
    return found


def price_locations(
    locations: list[Location],
    tariffs: list[Tariff],
    related: dict[str, Tariff] | None = None,
    withheld: frozenset[str] = frozenset(),
    added_vat: Mapping[str, float] = NO_VAT_ADDED,
) -> list[ConnectorPrice]:
    """The price for every connector at every location, in order. `related` adds tariffs
    from related_tariffs, keyed by the id the connector names; `withheld` holds the ids
    from withheld_free_tariffs; `added_vat` the VAT rates from vat_not_stated decisions,
    by operator id."""
    index = {tariff.id: tariff for tariff in tariffs} | (related or {})
    return [
        price_connector(
            connector,
            index,
            location_id=location.id,
            evse_uid=evse.uid,
            withheld=withheld,
            added_vat=added_vat,
        )
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
