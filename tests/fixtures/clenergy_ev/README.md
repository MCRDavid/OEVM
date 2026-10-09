# Clenergy EV fixtures

Responses downloaded from Clenergy EV's open data files on 9 October 2026, one request
each, from the links on Clenergy EV's open data page:

- https://api.clenergy.online/development/pcpr/locations (1,400 locations)
- https://api.clenergy.online/development/pcpr/tariffs (129 tariffs)

Each file is one response holding every record, in the wrapper
`{"name": "OK", "message": "ok", "data": [...], "error": null, "forcelogout": false}`
rather than an OCPI response object. To keep the fixtures short:

- `locations_page1.json` keeps 8 of the 1,400 locations, chosen to cover AC single-phase,
  AC three-phase and DC (CCS and CHAdeMO) connectors, the statuses AVAILABLE, CHARGING,
  OUTOFORDER and UNKNOWN, opening times that are 24/7, regular hours or not given, a
  tariff priced at zero, a location outside the UK with a USD tariff, and a location whose
  latitude and longitude appear to be the other way round.
- `tariffs_page1.json` keeps every tariff those locations refer to.
- Every record is exactly as Clenergy EV sent it. The files send no paging headers.

Only the content-type and access-control-allow-origin headers were kept. `manifest.json`
tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from Clenergy EV published under the Public Charge Point Regulations 2023,
used in line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: https://api.clenergy.online/development/pcpr/locations and
  https://api.clenergy.online/development/pcpr/tariffs, retrieved 9 October 2026.
- This data belongs to Clenergy EV. It is not covered by this project's Apache-2.0 code
  licence. See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
