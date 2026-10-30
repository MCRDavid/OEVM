# bp pulse fixtures

Responses recorded from Eco-Movement's PCPR API (OCPI 2.2.1), which serves bp pulse's data
under the Public Charge Point Regulations 2023, on 30 October 2026. They were recorded once in
GitHub Actions with the token from the `BP_PULSE_TOKEN` secret, sent in an `Authorization: Token`
header, as Eco-Movement's PCPR API user guide says (bp pulse's token email of 30 October 2026
links to it):

- https://open-chargepoints.com/api/ocpi/cpo/2.2.1/locations/?limit=1000 and
  https://open-chargepoints.com/api/ocpi/cpo/2.2.1/locations/?limit=1000&offset=1000
  (1,136 locations, two pages)
- https://open-chargepoints.com/api/ocpi/cpo/2.2.1/tariffs/?limit=1000 (5 tariffs in one page)

To keep the fixtures short:

- `locations_page1.json` keeps 2 of the 1,136 locations, one of each kind the feed holds: a
  location with a numeric id whose connectors give max_electric_power 0, with DC, single-phase
  and three-phase AC connectors (the three-phase one at 400 V), two tariffs and an EVSE
  INOPERATIVE; and a location with a longer id whose connectors give their power and name no
  tariff, with EVSEs INOPERATIVE and UNKNOWN. The second page is left out.
- `tariffs_page1.json` keeps the 2 tariffs that the first location's connectors name, and
  tariff `1`, whose only price is a flat fee of 0, although no kept location names it.
- `X-Total-Count` was changed to match the kept counts, and the `Link` header's offset to
  the kept count. Every response recorded that day linked to a next page past the last
  record, which the adapter does not follow (see `adapters/eco_movement.py`). Every record is
  exactly as Eco-Movement sent it.

Only the content-type, link, x-total-count and x-limit headers were kept; the token is never in
a response. `manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from bp pulse published under the Public Charge Point Regulations 2023, used in line with the
Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: https://open-chargepoints.com/api/ocpi/cpo/2.2.1/locations/ and
  https://open-chargepoints.com/api/ocpi/cpo/2.2.1/tariffs/, retrieved 30 October 2026.
- This data belongs to bp pulse. It is not covered by this project's Apache-2.0 code licence.
  See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
