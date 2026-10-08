# Jolt fixtures

Responses recorded from Jolt's open data API on 8 October 2026 with:

```bash
uv run python -m pipeline.run --live jolt --save-raw raw
```

The key was read from the `JOLT_API_KEY` environment variable and is not in these files:
it is only added to requests as they are sent, and anything a response echoes is replaced
with REDACTED. Only the content-type and access-control-allow-origin headers were kept.
`manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

`locations.json` is trimmed to 4 of the 72 locations Jolt returned, chosen to cover the
differences recorded in `operators/jolt.yaml`: lower-case and `preparing` statuses, EVSEs
with no connectors, a location with no time zone, connectors with no tariff, and the
`CCS2` connector standard. Each location is exactly as Jolt sent it. The tariff files are
complete and cover every tariff those locations refer to, including tariff 13, whose
energy price is null.

| File | Request |
|---|---|
| `locations.json` | `/v1/uk/public/locations` (trimmed to 4 locations) |
| `tariff_4.json`, `tariff_5.json`, `tariff_13.json`, `tariff_14.json`, `tariff_25.json` | `/v1/uk/public/tariffs/{tariffId}` |

## Source and licence

Contains data from Jolt published under the Public Charge Point Regulations 2023, used in
line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: https://api.joltcharge.com/v1/uk/public/locations and
  https://api.joltcharge.com/v1/uk/public/tariffs/{tariffId}, retrieved 8 October 2026.
- This data belongs to Jolt. It is not covered by this project's Apache-2.0 code licence.
  See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
