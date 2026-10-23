# PLUG Charging fixtures

Responses recorded from PLUG Charging's OCPI 2.2.1 feed on 23 October 2026 by
`python -m pipeline.run --live plug_charging --save-raw raw`, run once in GitHub Actions with
the key from the `PLUG_CHARGING_TOKEN` secret. The addresses come from the feed's version
details (https://plugcharging.co.uk/ocpi/2.2.1):

- https://plugcharging.co.uk/ocpi/2.2.1/locations (177 locations in one page)
- https://plugcharging.co.uk/ocpi/2.2.1/tariffs (86 tariffs in one page)

To keep the fixtures short:

- `locations_page1.json` keeps 8 of the 177 locations, chosen to cover AC single-phase, AC
  three-phase and DC connectors, the statuses AVAILABLE, CHARGING, INOPERATIVE, OUTOFORDER,
  REMOVED and UNKNOWN, opening times that are 24/7 or not, on-street and car park parking,
  single-phase connectors with `max_amperage` 0, connectors that name a tariff id the
  tariffs module does not have, and locations whose every EVSE is REMOVED.
- `tariffs_page1.json` keeps every tariff those locations refer to that the feed has (6).
- `X-Total-Count` was changed to match the trimmed record counts. Every record is exactly as
  PLUG Charging sent it.

Only the content-type, x-total-count and x-limit headers were kept; the key is never in a
response. `manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from PLUG Charging published under the Public Charge Point Regulations 2023,
used in line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: https://plugcharging.co.uk/ocpi/2.2.1/locations and
  https://plugcharging.co.uk/ocpi/2.2.1/tariffs, retrieved 23 October 2026. PLUG Charging's
  open data page, https://plugcharging.co.uk/open-data, states the Open Government Licence
  v3.0 for the data.
- This data belongs to PLUG Charging. It is not covered by this project's Apache-2.0 code
  licence. See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
