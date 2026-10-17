# ParkRecharge fixtures

Responses downloaded from the two "Access Reference Data" links on ParkRecharge's "Public
Charging and Open Data" page on 17 October 2026, one full run with
`python -m pipeline.run --live parkrecharge --save-raw raw` (six requests):

- https://ocpi.hubeleon.net/ocpi/public/2.2.1/locations (288 locations, three pages)
- https://ocpi.hubeleon.net/ocpi/public/2.2.1/tariffs (292 tariffs, three pages)

The feed is paged, 100 records a page, with X-Total-Count and Link headers. To keep the
fixtures short:

- `locations_page1.json` (the first page) keeps 5 of its 100 locations and
  `locations_page2.json` (`?offset=100`) keeps 5 of its 100. Together they cover the
  statuses AVAILABLE, CHARGING, INOPERATIVE, OUTOFORDER and REMOVED, AC single-phase, AC
  three-phase and DC connectors (CCS and CHAdeMO), opening times, names beginning
  "(REMOVED)" and "(Archived)", and the two locations named as test units.
- `tariffs_page1.json` keeps every tariff those locations refer to (10).
- Every record is exactly as sent. Page 1 keeps its content-type, Link and
  X-RateLimit-* headers; the other pages keep only content-type, so the replay stops after
  page 2. X-Total-Count was dropped from every page, as the trimmed pages hold fewer
  records than it gives.

Until 13 October 2026 the page linked https://ocpi-pcpr.hubeleon.net/2.2.1/reference and
https://ocpi-pcpr.hubeleon.net/2.2.1/referencetariffs, which no longer resolve. The
earlier fixtures, from those files, are in this folder's git history.

`manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from ParkRecharge published under the Public Charge Point Regulations 2023,
used in line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: the two URLs above, linked from https://parkrecharge.com/public-charging,
  retrieved 17 October 2026.
- This data belongs to ParkRecharge. It is not covered by this project's Apache-2.0 code
  licence. See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
