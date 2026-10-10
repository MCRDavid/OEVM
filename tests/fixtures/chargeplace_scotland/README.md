# ChargePlace Scotland fixtures

Responses downloaded from the "Locations" and "Tariffs" links on ChargePlace Scotland's
Network Performance page on 10 October 2026, one request each, with
`python -m pipeline.run --live chargeplace_scotland --save-raw`:

- https://info.smartcharging.uk/public_feed/locations/2463 (1,479 locations)
- https://info.smartcharging.uk/public_feed/locations/2463/tariffs (323 tariffs)

Each file is one OCPI 2.2.1 response holding every record, with X-Total-Count and X-Limit
headers equal to the number of records and a `meta` object giving the same total. Location
and connector ids are JSON numbers rather than strings. To keep the fixtures short:

- `locations_page1.json` keeps 6 of the 1,479 locations, chosen to cover:
  - the statuses AVAILABLE, CHARGING, INOPERATIVE and UNKNOWN, AC single phase, AC three
    phase and DC;
  - tariffs with a price per hour after a time and a minimum price, and a tariff whose
    only price is a flat fee of 0;
  - one location whose connectors name no tariff, and one whose connectors name a tariff
    that is not in ChargePlace Scotland's tariff response (it is in Evolt Network's);
  - a connector that gives 0 for max_amperage and max_electric_power.
  X-Total-Count, X-Limit and `meta.total` were changed to 6 to match.
- `tariffs_page1.json` keeps the 5 tariffs those locations name that are in the response.
  Its X-Total-Count, X-Limit and `meta.total` were changed to 5 to match.
- Every record is exactly as sent, in the order sent. The content-type, X-Total-Count and
  X-Limit headers were kept.

`manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from ChargePlace Scotland published under the Public Charge Point
Regulations 2023, used in line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: the two URLs above, linked from
  https://chargeplacescotland.org/network-performance-2/, retrieved 10 October 2026.
- This data belongs to ChargePlace Scotland. It is not covered by this project's
  Apache-2.0 code licence. See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
