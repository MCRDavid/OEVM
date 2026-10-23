# BrightGreen fixtures

Responses downloaded from BrightGreen's open data files on 23 October 2026, one request
each, from the links on BrightGreen's open data page:

- https://connect.bright.green/ocpp/locations (15 locations)
- https://connect.bright.green/ocpp/tariffs (12 tariffs)

Each file is one OCPI response object holding every record. The feed is small, so nothing
was trimmed: both files keep every record, which covers what the feed does differently
from OCPI 2.2.1 (EVSE status "idle", power types "fast" and "ultrarapid", no connector
standard, two-letter country codes, prices written as text, no party_id), 5 locations
marked publish false, 2 in Slovakia with a EUR tariff, one with no coordinates, one with
coordinates 90, 90, three sharing the same rounded coordinates, and one whose longitude
appears to be missing its minus sign.

- Every record is exactly as BrightGreen sent it. The files send no paging headers.
- Only the content-type header was kept. `manifest.json` tells
  `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from BrightGreen published under the Public Charge Point Regulations 2023,
used in line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: https://connect.bright.green/ocpp/locations and
  https://connect.bright.green/ocpp/tariffs, retrieved 23 October 2026, linked from
  https://bright.green/open-data/.
- This data belongs to BrightGreen. It is not covered by this project's Apache-2.0 code
  licence. See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
