# char.gy fixtures

Responses recorded from char.gy's open data feed on 7 October 2026 with:

```bash
uv run python -m pipeline.run --live chargy --max-pages 2 --page-size 2 --save-raw raw
uv run python -m pipeline.run --live chargy --max-pages 1 --page-size 2 \
  --date-from 2026-10-07T21:00:00+00:00 --save-raw raw
```

Small pages were requested so the files stay short. The bodies are exactly as char.gy
sent them. Only the paging headers (content-type, link, x-total-count, x-limit) were
kept. `manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

| File | Request |
|---|---|
| `locations_page1.json` | `/open-ocpi/locations?limit=2` |
| `locations_page2.json` | `/open-ocpi/locations?limit=2&offset=2` |
| `tariffs_page1.json` | `/open-ocpi/tariffs?limit=2` |
| `tariffs_page2.json` | `/open-ocpi/tariffs?limit=2&offset=2` (last page) |
| `locations_since_page1.json` | `/open-ocpi/locations?date_from=2026-10-07T21:00:00Z&limit=2` |
| `tariffs_since_page1.json` | `/open-ocpi/tariffs?date_from=2026-10-07T21:00:00Z&limit=2` (no results) |

## Source and licence

Contains data from char.gy published under the Public Charge Point Regulations 2023,
used in line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: https://char.gy/open-ocpi/locations and https://char.gy/open-ocpi/tariffs,
  retrieved 7 October 2026.
- This data belongs to char.gy. It is not covered by this project's Apache-2.0 code
  licence. See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
