# Enfield Council fixtures

Responses downloaded from the location data and tariff data links on Enfield Council's
electric vehicle charging page on 23 October 2026, one request each, 31 seconds apart, with
`python -m pipeline.run --live enfield_council --save-raw`:

- https://api.fuuse.io/opendata/d73a73f9-d063-456c-9f25-b51765e5747f/location (7 locations)
- https://api.fuuse.io/opendata/d73a73f9-d063-456c-9f25-b51765e5747f/tariff (1 tariff)

Each file is one OCPI 2.2.1 response holding every record, with X-Total-Count and X-Limit
headers. The feed is small, so nothing was trimmed:

- `locations_page1.json` is the whole location response: 7 council car parks, 32 Type 2
  sockets at 7 or 7.36 kW, statuses AVAILABLE, CHARGING and INOPERATIVE, and only the 2
  connectors at Palace Gardens naming a tariff.
- `tariffs_page1.json` is the whole tariff response (1 tariff, prices sent as strings).
- Every record is exactly as sent. The content-type, X-Total-Count and X-Limit headers were
  kept.

`manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from Enfield Council published under the Public Charge Point Regulations 2023,
used in line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: the two URLs above, linked from
  https://www.enfield.gov.uk/services/roads-and-transport/electric-vehicle-charging,
  retrieved 23 October 2026.
- This data belongs to Enfield Council. It is not covered by this project's Apache-2.0 code
  licence. See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
