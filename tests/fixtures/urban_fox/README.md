# Urban Fox fixtures

Responses downloaded from Urban Fox's OCPI Open Data API on 23 October 2026, one request
each, from the addresses in the API description linked from Urban Fox's data access page:

- https://api.urbanfox.network/api/opendata/locations (138 locations, in three pages of
  up to 50, each with `X-Total-Count` 138 and a `Link` header to the next page)
- https://api.urbanfox.network/api/opendata/tariffs (22 tariffs, one page)

Each file is one OCPI 2.2.1 response. To keep the fixtures short:

- `locations_page1.json` (the first page) keeps 3 of its 50 locations, and its `Link`
  header to the second page is kept as sent.
- `locations_page2.json` (the second page's address) keeps 3 locations from the second
  and third pages, and its `Link` header to the third page was removed, so the adapter
  follows one link and stops.
- Together they cover Dundee, Newport, Plymouth, Brighton and Dartford, AC single-phase
  and three-phase connectors, the statuses AVAILABLE, CHARGING and OUTOFORDER, tariffs
  with a price per kWh, and tariffs whose only price is 0.0 (see
  `operators/urban_fox.yaml`). Every tariff states VAT 0.
- `tariffs_page1.json` keeps every tariff those locations refer to (5 of 22).
- `X-Total-Count` was changed to match the trimmed record counts. Every record is exactly
  as Urban Fox sent it.

Only the content-type, link, x-total-count and x-limit headers were kept. `manifest.json`
tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from Urban Fox published under the Public Charge Point Regulations 2023,
used in line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: https://api.urbanfox.network/api/opendata/locations and
  https://api.urbanfox.network/api/opendata/tariffs, retrieved 23 October 2026, described
  at https://urbanfox.network/public-charge-point-regulations-data-access/.
- This data belongs to Urban Fox. It is not covered by this project's Apache-2.0 code
  licence. See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
