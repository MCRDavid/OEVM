# Roam fixtures

Responses recorded from Roam's open data feed on 26 October 2026, one GET to each address
with the project's User-Agent and no key. Roam gave the addresses by email the same day
(`evidence/roam/2026-10-26-reply-email.md`):

- https://data.evc.ninja/public/v1/data (438 locations in one OCPI response)
- https://data.evc.ninja/public/v1/tariffs (728 tariffs in one OCPI response)

The records use OCPI 2.1.1 field names (`adapters/roam.py`). To keep the fixtures short:

- `locations.json` keeps 7 of the 438 locations, chosen to cover AC three-phase Type 2
  sockets, DC CCS cables of 100 kW and 300 kW, the statuses AVAILABLE, CHARGING, OUTOFORDER
  and UNKNOWN, EVSEs whose two connectors report different statuses, the test charger at
  Norwood Hall Hotel on the tariff `free_tariff`, Co op Boley Park with no EVSEs, Marlie
  Holiday Park whose EVSEs have two connectors with the id 1 (read with Roam's own
  connector uuids as ids), and sites in Scotland and Cornwall.
- `tariffs.json` keeps the 8 of 728 tariffs those locations name.
- `X-Total-Count` was changed to match each trimmed count. Every record is exactly as Roam
  sent it.

Only the content-type and x-total-count headers were kept. The locations response also
sent `ratelimit-policy: 5;w=3600`, recorded in `operators/roam.yaml`. `manifest.json` tells
`python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from Roam published under the Public Charge Point Regulations 2023, used in
line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: https://data.evc.ninja/public/v1/data and
  https://data.evc.ninja/public/v1/tariffs, retrieved 26 October 2026.
- This data belongs to Roam. It is not covered by this project's Apache-2.0 code licence.
  See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
