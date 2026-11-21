# Go Zero fixtures

Responses recorded from Go Zero's OCPI feed on 20 November 2026 by
`python -m pipeline.run --live go_zero --max-pages 1 --save-raw raw`, one request each, with
no key:

- https://ocpi.gozerocharge.com/api/v1/ocpi/2.2.1/locations (57 locations in one page), read
  by Go Zero's own "CPO Live Data" dashboard
- https://ocpi.gozerocharge.com/api/v1/ocpi/2.2/tariffs (57 tariffs in one page), the tariffs
  path from Go Zero's earlier open data page on the same host

To keep the fixtures short:

- `locations_page1.json` keeps 11 of the 57 locations, chosen to cover AC single-phase
  7.4 kW, AC three-phase 22 kW and DC 30, 40 and 50 kW connectors, the statuses AVAILABLE,
  CHARGING, OUTOFORDER and INOPERATIVE, a location with four EVSEs of three kinds, a site
  in the Outer Hebrides, and the address quirks in the operator file's findings (a postcode
  starting "S0", a postcode with no space, a city holding the postcode and a name starting
  with a space). Every location gives `"type": "PARKING_LOT"`, the OCPI 2.1.1 field name.
- `tariffs_page1.json` keeps every tariff those locations refer to (11 of 57). Each has two
  ENERGY elements, 06:00 to 22:00 and 22:00 to 06:00 every day, at the same price, excluding
  VAT with a vat rate of 20.
- `X-Total-Count` was changed to match the trimmed counts. Every record is exactly as Go Zero
  sent it.

Only the content-type, x-total-count and x-limit headers were kept. `manifest.json` tells
`python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from Go Zero published under the Public Charge Point Regulations 2023, used in
line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: https://ocpi.gozerocharge.com/api/v1/ocpi/2.2.1/locations and
  https://ocpi.gozerocharge.com/api/v1/ocpi/2.2/tariffs, retrieved 20 November 2026, found
  through https://cpo-data.gozerocharge.network/ (linked as "CPO Live Data" from
  https://www.gozerocharge.com/).
- This data belongs to Go Zero. It is not covered by this project's Apache-2.0 code
  licence. See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
