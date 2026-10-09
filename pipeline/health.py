"""Health figures for one operator's run: what share of the data can be used as received.

Counted automatically from the converted records, for the feed health page. The figures
describe what this project received; they say nothing about whether any operator has met
its legal duties.
"""

from statistics import median

from adapters.ocpi_221 import AdapterResult
from pipeline.tariffs import price_locations
from schema.models import Location
from schema.runlog import Health

# Latitude and longitude limits that include the Isles of Scilly, Shetland, Northern
# Ireland and the east coast. A point outside them is not plotted.
UK_LATITUDE = (49.8, 60.95)
UK_LONGITUDE = (-8.7, 1.8)


def in_uk(location: Location) -> bool:
    lat, lon = location.coordinates.latitude, location.coordinates.longitude
    return UK_LATITUDE[0] <= lat <= UK_LATITUDE[1] and UK_LONGITUDE[0] <= lon <= UK_LONGITUDE[1]


def health(result: AdapterResult) -> Health:
    locations = result.locations
    evses = [evse for location in locations for evse in location.evses]
    prices = price_locations(locations, result.tariffs)
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
        median_last_updated_days=round(max(median(ages), 0), 1) if ages else None,
    )
