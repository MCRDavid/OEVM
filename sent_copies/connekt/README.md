# Connekt: copy of its data sent on 26 October 2026

Connekt answered the open data request form on
https://www.connektcharging.com/public-charge-point-regulations (sent on 2026-10-24) by email
on 2026-10-26, with its location and tariff data attached as two JSON files and no address
to fetch the data from. The message is saved in `evidence/connekt/2026-10-26-reply.md`.

The two files are kept here exactly as the repository owner received them, gzipped:

| File | What it is | SHA-256 of the file as received (before gzip) |
|---|---|---|
| `2026-10-26-locations.json.gz` | OCPI 2.2.1 locations response: 362 locations, party GB CON | `9791dbac2728701f47bd8af8bf8b390829ecec5d2abfc63d2a4ef22abada2784` |
| `2026-10-26-tariffs.json.gz` | OCPI 2.2.1 tariffs response: 326 tariffs | `eb3c1509bcd9c8ec76c657c89027ec0f3eac28693048b448b466ca1df139cb6d` |

Both responses carry `"status_code": 1000` and a timestamp of 2026-10-26T14:22:52Z
(locations 14:22:52.378, tariffs 14:22:52.593), which `operators/connekt.yaml` records as
`made_at`.

They are on the map by the repository owner's decision of 29 October 2026 (`sent_copy` in
`operators/connekt.yaml`, ADR 0029), with every charge point status shown as unknown.

## Source and licence

Contains data from Connekt provided under the Public Charge Point Regulations 2023, used in
line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). The data is not
covered by this project's Apache-2.0 code licence.
