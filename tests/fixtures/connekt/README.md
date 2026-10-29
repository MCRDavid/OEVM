# Connekt fixtures

Connekt publishes no address to fetch its data from. It sent its data by email on
26 October 2026 as two OCPI 2.2.1 responses, which are kept as sent, gzipped, in
`sent_copies/connekt/` and shown on the map by the repository owner's decision of
29 October 2026 (`sent_copy` in `operators/connekt.yaml`, ADR 0029). Nothing was fetched
to make these fixtures.

To keep the fixtures short:

- `locations.json` keeps 6 of the 362 locations, chosen to cover AC single-phase 7.4 kW and
  three-phase 22 kW Type 2 cables, DC CCS at 40, 50, 60 and 120 kW, the statuses AVAILABLE,
  CHARGING and OUTOFORDER (all shown as unknown), connectors that name no tariff, and
  locations whose city is sent as "undefined".
- `tariffs.json` keeps the 8 tariffs those locations name, each a flat fee and an energy
  price with VAT stated as 20.
- Every record, and each response's `status_code`, `status_message` and `timestamp`, is
  exactly as Connekt sent it; only the other records were removed, and the JSON re-indented.

`manifest.json` tells `python -m pipeline.run --fixtures` to read these two files in place of
the ones named in `operators/connekt.yaml`.

## Source and licence

Contains data from Connekt provided under the Public Charge Point Regulations 2023, used in
line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). The data is not
covered by this project's Apache-2.0 code licence.
