# Source EV fixtures

Responses recorded from Eco-Movement's PCPR API (OCPI 2.2.1), which serves Source EV's data
under the Public Charge Point Regulations 2023, on 29 October 2026. They were recorded once in
GitHub Actions with the token from the `SOURCE_EV_TOKEN` secret, sent in an `Authorization: Token`
header, as Eco-Movement's token email of 26 October 2026 says:

- https://open-chargepoints.com/api/ocpi/cpo/2.2.1/locations/?limit=1000 (37 locations, one page)
- https://open-chargepoints.com/api/ocpi/cpo/2.2.1/tariffs/?limit=1000 (2 tariffs in one page)

To keep the fixtures short:

- `locations_page1.json` keeps 3 of the 37 locations, chosen to cover a site with DC and AC connectors whose tariff gives VAT as 0.2, an OUTOFORDER EVSE and one more of the first records.
- `tariffs_page1.json` keeps the 2 of the 2 tariffs that those locations' connectors name.
- `X-Total-Count` was changed to match the trimmed counts, and the `Link` header's offset to
  the trimmed count. Every response recorded that day linked to a next page past the last
  record, which the adapter does not follow (see `adapters/eco_movement.py`). Every record is
  exactly as Eco-Movement sent it.

Only the content-type, link, x-total-count and x-limit headers were kept; the token is never in
a response. `manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from Source EV Ltd, the data provider published under the Public Charge Point Regulations 2023, used in line with the
Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: https://open-chargepoints.com/api/ocpi/cpo/2.2.1/locations/ and
  https://open-chargepoints.com/api/ocpi/cpo/2.2.1/tariffs/, retrieved 29 October 2026.
- This data belongs to Source EV. It is not covered by this project's Apache-2.0 code licence.
  See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
