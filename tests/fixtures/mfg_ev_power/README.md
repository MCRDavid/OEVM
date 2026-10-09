# MFG EV Power fixtures

Responses downloaded from MFG EV Power's open data files on 9 October 2026, one request
each, with `python -m pipeline.run --live mfg_ev_power --save-raw`, from the links on
MFG's EV Power page:

- https://opendata.motorfuelgroup.net/locations (597 locations)
- https://opendata.motorfuelgroup.net/tariffs (8 tariffs)

Each file is one OCPI 2.2.1 response holding every record, sent with no paging headers.
To keep the fixtures short:

- `locations_page1.json` keeps 4 of the 597 locations, chosen to cover the statuses
  AVAILABLE, CHARGING, INOPERATIVE, OUTOFORDER and UNKNOWN, opening times that are 24/7
  or regular hours, and both tariffs the network refers to. Every connector in the feed
  is DC (CCS or CHAdeMO).
- `tariffs_page1.json` keeps the 2 tariffs those locations refer to.
- Every record is exactly as MFG EV Power sent it. Only the content-type header was
  kept, because the files send no X-Total-Count, X-Limit or Link header.

`manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from MFG EV Power published under the Public Charge Point Regulations 2023,
used in line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: https://opendata.motorfuelgroup.net/locations and
  https://opendata.motorfuelgroup.net/tariffs, retrieved 9 October 2026.
- This data belongs to MFG EV Power. It is not covered by this project's Apache-2.0 code
  licence. See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
