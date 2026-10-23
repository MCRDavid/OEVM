# 3ti fixtures

Responses downloaded on 23 October 2026 from the Fuuse open data addresses that 3ti's
public charge points page (https://3ti.co.uk/3ti-public-charge-points/) reads for each
site, one request each, 31 seconds apart, with this project's client:

| Site | Location file | Tariff file |
|---|---|---|
| Raigmore Hospital, Inverness | `locations_page1.json` (1 location) | `tariffs_page1.json` (1 tariff) |
| Riverbridge House, Surrey | `locations_page2.json` (1 location) | `tariffs_page2.json` (1 tariff) |
| University of Surrey, Surrey | `locations_page3.json` (1 location) | `tariffs_page3.json` (1 tariff) |
| East Staffordshire Borough Council | `locations_page4.json` (1 location) | `tariffs_page4.json` (1 tariff) |
| Salford Royal Hospital | `locations_page5.json` (2 locations) | `tariffs_page5.json` (1 tariff) |

Each address is `https://api.fuuse.io/opendata/<site id>/location` or `.../tariff`; the
site ids are in `operators/three_ti.yaml`. Each file is one OCPI 2.2.1 response with
X-Total-Count and X-Limit headers. The files are small, so none was trimmed: every record
is exactly as sent, and only the content-type, X-Total-Count and X-Limit headers were kept.
The sixth site on the page, Segen, Medway, answered HTTP 204 with no content for both of
its addresses that day, so it has no fixture.

`manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from 3ti published under the Public Charge Point Regulations 2023, used in
line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: the ten addresses above, read by https://3ti.co.uk/3ti-public-charge-points/,
  retrieved 23 October 2026.
- This data belongs to 3ti. It is not covered by this project's Apache-2.0 code licence.
  See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
