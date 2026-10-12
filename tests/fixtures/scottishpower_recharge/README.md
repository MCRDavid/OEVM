# ScottishPower Recharge fixtures

Responses downloaded from the location and tariff data links in the "Open data access" section
of ScottishPower's public EV charging blog page on 11 October 2026, one request each, 31 seconds
apart, with `python -m pipeline.run --live scottishpower_recharge --save-raw`:

- https://api.fuuse.io/opendata/e11a667d-c56a-468f-b8d3-a50b41628292/location (65 locations)
- https://api.fuuse.io/opendata/e11a667d-c56a-468f-b8d3-a50b41628292/tariff (8 tariffs)

Each file is one OCPI 2.2.1 response holding every record, with X-Total-Count and X-Limit
headers. To keep the fixtures short:

- `locations_page1.json` keeps 7 of the 65 locations, chosen to cover the statuses AVAILABLE,
  CHARGING and INOPERATIVE, AC Type 2, CCS and CHAdeMO, the one Type 2 cable sent as DC,
  opening times that are 24/7 or regular hours, a location with a state, connectors that name
  no tariff, the location whose connectors name the tariff with every price at zero, and the
  postcode written with a letter O. Its X-Total-Count was changed to 7 to match.
- `tariffs_page1.json` is the whole tariff response (8 tariffs).
- Every record is exactly as sent. The content-type, X-Total-Count and X-Limit headers were
  kept.

`manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from ScottishPower Recharge published under the Public Charge Point Regulations
2023, used in line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: the two URLs above, linked from https://www.scottishpower.co.uk/blog/public-ev-charging,
  retrieved 11 October 2026.
- This data belongs to ScottishPower Recharge. It is not covered by this project's Apache-2.0
  code licence. See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
