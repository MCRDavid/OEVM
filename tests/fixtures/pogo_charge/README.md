# PoGo Charge fixtures

Responses downloaded from the "Locations" and "Tariffs" links in PoGo Charge's FAQ answer
"Does PoGo offer open data API access?" on 10 October 2026, one request each, with
`python -m pipeline.run --live pogo_charge --save-raw`:

- https://info.smartcharging.uk/public_feed/locations/4009 (161 locations)
- https://info.smartcharging.uk/public_feed/locations/4009/tariffs (13 tariffs)

Each file is one OCPI 2.2.1 response holding every record, with X-Total-Count and X-Limit
headers equal to the number of records and a `meta` object giving the same total. Location
and connector ids are JSON numbers rather than strings. To keep the fixtures short:

- `locations_page1.json` keeps 5 of the 161 locations, chosen to cover the statuses
  AVAILABLE, CHARGING, INOPERATIVE and UNKNOWN, AC single phase, AC three phase and DC (CCS
  and CHAdeMO), EVSEs with parking restrictions, and one location whose connectors name no
  tariff. The connectors of the other four name tariffs that are not in PoGo's tariff
  response (on 10 October 2026 every tariff PoGo's connectors named was one published in
  Evolt Network's tariff response instead). X-Total-Count, X-Limit and `meta.total` were
  changed to 5 to match.
- `tariffs_page1.json` is the whole tariff response (13 tariffs, none of them named by a
  connector).
- Every record is exactly as sent, in the order sent. The content-type, X-Total-Count and
  X-Limit headers were kept.

`manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from PoGo Charge published under the Public Charge Point Regulations 2023,
used in line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: the two URLs above, linked from https://pogocharge.com/faqs/, retrieved
  10 October 2026.
- This data belongs to PoGo Charge. It is not covered by this project's Apache-2.0 code
  licence. See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
