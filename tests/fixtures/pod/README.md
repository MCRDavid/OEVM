# Pod Point fixtures

Responses recorded from Eco-Movement's PCPR API (OCPI 2.2.1), which serves Pod Point's data
under the Public Charge Point Regulations 2023, on 29 October 2026. They were recorded once in
GitHub Actions with the token from the `POD_TOKEN` secret, sent in an `Authorization: Token`
header, as Eco-Movement's token email of 26 October 2026 says:

- https://open-chargepoints.com/api/ocpi/cpo/2.2.1/locations/?limit=1000 (1809 locations, 2 pages; only the first was recorded)
- https://open-chargepoints.com/api/ocpi/cpo/2.2.1/tariffs/?limit=1000 (774 tariffs in one page)

To keep the fixtures short:

- `locations_page1.json` keeps 4 of the 1809 locations, chosen to cover a DC site, an AC site with an OUTOFORDER EVSE, a site on the Isle of Man (outside the UK, so left off the map) and a site whose tariff prices are all zero.
- `tariffs_page1.json` keeps the 6 of the 774 tariffs that those locations' connectors name.
- `X-Total-Count` was changed to match the trimmed counts, and the `Link` header's offset to
  the trimmed count. Every response recorded that day linked to a next page past the last
  record, which the adapter does not follow (see `adapters/eco_movement.py`). Every record is
  exactly as Eco-Movement sent it.

Only the content-type, link, x-total-count and x-limit headers were kept; the token is never in
a response. `manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from Pod Point published under the Public Charge Point Regulations 2023, used in line with the
Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: https://open-chargepoints.com/api/ocpi/cpo/2.2.1/locations/ and
  https://open-chargepoints.com/api/ocpi/cpo/2.2.1/tariffs/, retrieved 29 October 2026.
- This data belongs to Pod Point. It is not covered by this project's Apache-2.0 code licence.
  See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
