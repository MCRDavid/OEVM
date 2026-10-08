# GeniePoint fixtures

Responses downloaded from GeniePoint's open data files on 8 October 2026, one request
each, from the links on GeniePoint's open data page:

- https://opendata.geniepoint.co.uk/locations (306 locations)
- https://opendata.geniepoint.co.uk/tariffs (530 tariff records, 376 distinct ids)

Each file is one OCPI 2.2.1 response holding every record. To keep the fixtures short:

- `locations_page1.json` keeps 5 of the 306 locations, chosen to cover AC single-phase,
  AC three-phase and DC connectors, the statuses AVAILABLE, CHARGING, BLOCKED,
  INOPERATIVE, OUTOFORDER and UNKNOWN, and opening times that are 24/7, regular hours or
  not given.
- `tariffs_page1.json` keeps every tariff those locations refer to, plus 2 of the 8
  identical copies of one repeated tariff, so the de-duplication is tested.
- `X-Total-Count` was changed to match the trimmed record counts, so the adapter reads
  one page as it does with the full files. Every record is exactly as GeniePoint sent it.

Only the content-type, x-total-count and x-limit headers were kept. `manifest.json` tells
`python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from GeniePoint published under the Public Charge Point Regulations 2023,
used in line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: https://opendata.geniepoint.co.uk/locations and
  https://opendata.geniepoint.co.uk/tariffs, retrieved 8 October 2026.
- This data belongs to GeniePoint. It is not covered by this project's Apache-2.0 code
  licence. See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
