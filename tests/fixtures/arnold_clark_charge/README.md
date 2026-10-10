# Arnold Clark Charge fixtures

Responses downloaded from the "Open Access Location Data" and "Open Access Tariff Data"
links on Arnold Clark Charge's page on 10 October 2026, one request each, with
`python -m pipeline.run --live arnold_clark_charge --save-raw`:

- https://api.fuuse.io/opendata/e6397b95-1624-49cd-824d-ab2f9dfe7294/location (126 locations)
- https://api.fuuse.io/opendata/e6397b95-1624-49cd-824d-ab2f9dfe7294/tariff (2 tariffs)

Each file is one OCPI 2.2.1 response holding every record, with X-Total-Count and X-Limit
headers. To keep the fixtures short:

- `locations_page1.json` keeps 5 of the 126 locations, chosen to cover the statuses
  AVAILABLE, CHARGING and OUTOFORDER, CCS and CHAdeMO, opening times that are 24/7 or
  regular hours, a location with a state, one "(App Bookings)" location, and the only two
  locations whose connectors name a tariff. Its X-Total-Count was changed to 5 to match.
- `tariffs_page1.json` is the whole tariff response (2 tariffs).
- Every record is exactly as sent. The content-type, X-Total-Count and X-Limit headers were
  kept.

`manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from Arnold Clark Charge published under the Public Charge Point Regulations
2023, used in line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: the two URLs above, linked from https://www.arnoldclark.com/charge, retrieved
  10 October 2026.
- This data belongs to Arnold Clark Charge. It is not covered by this project's Apache-2.0
  code licence. See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
