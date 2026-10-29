# Blink Charging fixtures

Responses recorded from Eco-Movement's PCPR API (OCPI 2.2.1), which serves Blink Charging's data
under the Public Charge Point Regulations 2023, on 29 October 2026. They were recorded once in
GitHub Actions with the token from the `BLINK_CHARGING_UK_TOKEN` secret, sent in an `Authorization: Token`
header, as Eco-Movement's token email of 26 October 2026 says:

- https://open-chargepoints.com/api/ocpi/cpo/2.2.1/locations/?limit=1000 (875 locations, one page)
- https://open-chargepoints.com/api/ocpi/cpo/2.2.1/tariffs/?limit=1000 (56 tariffs in one page)

To keep the fixtures short:

- `locations_page1.json` keeps 4 of the 875 locations, chosen to cover DC, AC single-phase and three-phase connectors, the statuses AVAILABLE, CHARGING and OUTOFORDER, and a location whose time zone is UTC.
- `tariffs_page1.json` keeps the 3 of the 56 tariffs that those locations' connectors name.
- `X-Total-Count` was changed to match the trimmed counts, and the `Link` header's offset to
  the trimmed count. Every response recorded that day linked to a next page past the last
  record, which the adapter does not follow (see `adapters/eco_movement.py`). Every record is
  exactly as Eco-Movement sent it.

Only the content-type, link, x-total-count and x-limit headers were kept; the token is never in
a response. `manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from Blink Charging published under the Public Charge Point Regulations 2023, used in line with the
Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: https://open-chargepoints.com/api/ocpi/cpo/2.2.1/locations/ and
  https://open-chargepoints.com/api/ocpi/cpo/2.2.1/tariffs/, retrieved 29 October 2026.
- This data belongs to Blink Charging. It is not covered by this project's Apache-2.0 code licence.
  See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
