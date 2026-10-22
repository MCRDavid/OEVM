"""Health figures for one operator's run: what share of the data can be used as received.

Counted automatically from the converted records, for the feed health page. The figures
describe what this project received; they say nothing about whether any operator has met
its legal duties. Connectors priced from a related operator's tariffs (ADR 0020) are
counted on their own, so connectors_with_tariff still measures the operator's own feed.
"""

from statistics import median

from adapters.ocpi_221 import AdapterResult
from pipeline.geography import place_in_uk
from pipeline.tariffs import price_locations
from schema.models import Location, Tariff
from schema.runlog import Health


def in_uk(location: Location) -> bool:
    """True if the location is genuinely in the UK (see pipeline/geography.py)."""
    return place_in_uk(
        location.coordinates.latitude,
        location.coordinates.longitude,
        location.address.postal_code,
    )


def health(result: AdapterResult, related: dict[str, Tariff] | None = None) -> Health:
    """The figures for one run. `related` holds the tariffs found in related operators'
    feeds for this operator's connectors (pipeline.publish related_for)."""
    locations = result.locations
    evses = [evse for location in locations for evse in location.evses]
    prices = price_locations(locations, result.tariffs)
    with_related = price_locations(locations, result.tariffs, related) if related else prices
    ages = [
        (result.fetched_at - location.last_updated).total_seconds() / 86400
        for location in locations
        if location.last_updated is not None
    ]
    return Health(
        locations=len(locations),
        locations_in_uk=sum(in_uk(location) for location in locations),
        evses=len(evses),
        evses_with_status=sum(evse.status != "unknown" for evse in evses),
        connectors=len(prices),
        connectors_with_tariff=sum(bool(price.tariff_ids) for price in prices),
        connectors_with_tariff_from_related=sum(
            not own.tariff_ids and bool(price.tariff_ids)
            for own, price in zip(prices, with_related, strict=True)
        ),
        median_last_updated_days=round(max(median(ages), 0), 1) if ages else None,
    )
