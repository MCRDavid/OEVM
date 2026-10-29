# Zest: copy of its data sent on 28 October 2026

Zest answered the open data request form on https://www.zest.uk.com/charge-point-open-data
(sent on 2026-10-23) by email on 2026-10-28, with its location and tariff data attached as
two JSON files and no address to fetch the data from. It asked for the form to be completed
monthly for an updated snapshot. The message is saved in `evidence/zest/2026-10-28-reply.md`.

The two files are kept here exactly as the repository owner received them, gzipped:

| File | What it is | SHA-256 of the file as received (before gzip) |
|---|---|---|
| `2026-10-28-locations.json.gz` | OCPI 2.2.1 locations response: 2,005 records for 1,963 locations, party GB ZST | `d310aaa6f24e9e8e511505a59d724fb384afd0f3b4aabc6270a43efc1dc62ad3` |
| `2026-10-28-tariffs.json.gz` | OCPI 2.2.1 tariffs response: 67 tariffs | `dd3759be46037f332a7ba5e4c51f15b8e61688e2f3cc134fda9db90a398d7c2d` |

They arrived as `zest_prod_locations_20261026_1030_combined.json` and
`zest_prod_tariffs_20261026_1030.json`. Both responses carry `"status_code": 1000`. The
locations response's timestamp is 2026-10-26T10:29:56.054Z, which `operators/zest.yaml`
records as `made_at`; the tariffs response's is 2026-10-26T10:28:03.225Z.

They are on the map by the repository owner's decision of 29 October 2026 (`sent_copy` in
`operators/zest.yaml`, ADR 0029), with every charge point status shown as unknown. By the
same decision, each newer copy Zest sends replaces this one: add its files here named by the
day they arrived, update this table and `sent_copy`, log the reply, and delete these files.

## Source and licence

Contains data from Zest, licensed under CC BY 4.0
(https://creativecommons.org/licenses/by/4.0/). Adapted from Zest's data. The data is not
covered by this project's Apache-2.0 code licence.
