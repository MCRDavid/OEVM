# Globe EV fixtures

Responses downloaded from Globe EV's open data files on 23 October 2026, one request each,
from the links on Globe EV's open data page:

- https://api.evdot.clenergy.online/development/pcpr/locations (109 locations)
- https://api.evdot.clenergy.online/development/pcpr/tariffs (10 tariffs)

Each file is one response holding every record, in Clenergy's wrapper
`{"name": "OK", "message": "ok", "data": [...], "error": null, "forcelogout": false}`
rather than an OCPI response object, as for Clenergy EV. To keep the fixtures short:

- `locations_page1.json` keeps 6 of the 109 locations, chosen to cover AC single-phase,
  AC three-phase and DC connectors, the statuses AVAILABLE, CHARGING, OUTOFORDER and
  UNKNOWN, and a tariff with a flat fee. Every location in the feed is open 24/7.
- `tariffs_page1.json` keeps every tariff those locations refer to (3 of 10). None gives a
  VAT rate.
- Every record is exactly as Globe EV sent it. The files send no paging headers.

Only the content-type and access-control-allow-origin headers were kept. `manifest.json`
tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from Globe EV published under the Public Charge Point Regulations 2023, used
in line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: https://api.evdot.clenergy.online/development/pcpr/locations and
  https://api.evdot.clenergy.online/development/pcpr/tariffs, retrieved 23 October 2026,
  linked from https://globeev.co.uk/open-data/.
- This data belongs to Globe EV. It is not covered by this project's Apache-2.0 code
  licence. See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
