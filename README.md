# OEVM: Open UK EV Charger Map

> OEVM is a personal, experimental project for learning about AI tools. Much of its code
> and text was written with an AI assistant, and it will contain mistakes. Charger data
> comes from the operators and other sources credited on every record, and remains their
> work. Everything is provided "as is", with no warranty or guarantee of any kind. Always
> check prices and availability at the charger. Full text: [DISCLAIMER.md](DISCLAIMER.md).

A free, open map of UK public electric vehicle chargers, built from the open data that
charge point operators must publish under the Public Charge Point Regulations 2023
(regulation 10, OCPI 2.2.1). The aim is prices and availability from operators' own
data, with a data health page and a dated log of how each operator provides access.

The full plan is in [docs/BLUEPRINT.md](docs/BLUEPRINT.md).

## Status

Early days. The map is live at https://mcrdavid.github.io/OEVM/ (since 8 October 2026,
with char.gy's and Jolt's data so far; see the feed health page). Blueprint tasks 1 to 10 are in place:

1. **Scaffold:** uv, ruff, pytest, pre-commit secret scanning and a CI workflow.
2. **Schema:** Pydantic models for Location, EVSE, Connector, Tariff and Provenance,
   exported as JSON Schema in `schema/json/`.
3. **Operator registry:** one YAML file per operator in `operators/`, with a schema and
   a validator.
4. **OCPI 2.2.1 adapter:** fetches an operator's locations and tariffs politely, page by
   page, and converts them to the schema. char.gy is the first operator switched on.
5. **Jolt adapter:** reads Jolt's own API format, which differs from OCPI 2.2.1 in ways
   recorded on the transparency page, and converts it the same way. GeniePoint's files
   turned out to be standard OCPI 2.2.1, so the OCPI adapter reads them.
6. **Tariffs:** each connector's price comes from the tariffs it lists. "Free" only when
   every listed tariff is confirmed free; a missing or unreadable tariff means "Price
   unknown". Prices that apply only at some times, or after a while, say so.
7. **Map files:** `--publish DIR` merges the operators into one slim GeoJSON layer, one
   detail file per location and a manifest with attribution and file sizes. Every file
   is validated before it is written.
8. **Feed health page:** each run logs health figures (locations with UK coordinates,
   EVSEs with a status, connectors with a tariff that was found). `pipeline.status` turns
   the logs into a page with a 30-day history, in neutral, dated wording.
9. **Map page** (`site/index.html`): a clustered map with filters (power, connector,
   price, network), a details panel showing where each record came from and when, filters
   kept in the page address, opt-in saved settings and a list view that works without
   the map. The background map comes from OpenFreeMap; MapLibre GL JS is served from the
   site itself.
10. **Workflows:** a daily fetch of every enabled operator, a deploy to GitHub Pages from
    `main` and a monthly keepalive. See `docs/adr/0009-scheduled-workflows.md` and section
    9 of `docs/GITHUB_SETTINGS.md` for the settings to switch on first.

Also in place:

- **Transparency page** (`site/transparency/index.html`): every source, how it publishes
  its data, its licence, the rate limits that apply, and dated findings such as
  differences from the OCPI standard. Built from the registry.
- **Rate limits:** at least 1 second between requests to any operator, and never more
  than an operator's published limit. Tests check both.
- **Prices in pounds and pence only.** Tariffs in other currencies show as "Price unknown"
  and are never converted.

The rules the site follows for privacy and cookies are in
[docs/PRIVACY_AND_COOKIES.md](docs/PRIVACY_AND_COOKIES.md), and the notice is published
on the site at `privacy/` from the same file.

## Principles

- Operator feeds come first. OpenStreetMap, Open Charge Map and user reports only fill
  gaps, in separate layers.
- Every record carries its provenance: source, licence, when it was fetched and how far
  to trust it.
- A charger is only ever shown as free when the operator's own tariff says every price
  is zero. A missing tariff means "Price unknown"; missing VAT means "excluding VAT,
  VAT not stated".
- No secrets in the repository and no personal data.
- Status pages use neutral, dated, evidenced wording.
- Unknown facts are written as "unknown" or "needs_testing", never guessed.

## Getting started

1. Install uv by following the
   [uv installation guide](https://docs.astral.sh/uv/getting-started/installation/).
2. In the repository folder, install everything the project needs:

   ```bash
   uv sync
   ```

3. Turn on the secret scanner for your own commits (once per copy of the repository):

   ```bash
   uv run pre-commit install
   ```

4. For the map page only: install [Node.js](https://nodejs.org/) 22 or later, then
   install MapLibre and Lighthouse from the lock file:

   ```bash
   npm ci
   ```

## Everyday commands

| Task | Command |
|---|---|
| Lint | `uv run ruff check . && uv run ruff format --check .` |
| Fix formatting | `uv run ruff format .` |
| Run the tests | `uv run pytest -q` |
| Validate the operator registry | `uv run python -m pipeline.registry --validate` |
| Run the adapters on recorded data (no network) | `uv run python -m pipeline.run --fixtures` |
| Fetch one page from a real feed | `uv run python -m pipeline.run --live chargy --max-pages 1` |
| Rebuild the transparency page after editing `operators/` | `uv run python -m pipeline.transparency` |
| Regenerate JSON Schema after changing a model | `uv run python -m schema.export` |
| Run every pre-commit check on every file | `uv run pre-commit run --all-files` |
| Build the map page from recorded data into `build/` | `uv run python -m pipeline.run --fixtures --publish build && uv run python -m pipeline.build_site --out build` |
| Look at the built page | `python -m http.server -d build 8000`, then open http://localhost:8000 |
| JavaScript unit tests | `npm test` |
| Browser tests and Lighthouse (needs `npm ci` and Chrome or Chromium) | `CHROME_PATH=/path/to/chrome uv run pytest -q -m e2e` |

CI runs all of these on every pull request, except the live fetch: tests never call real
feeds. Use `--live` sparingly. It only works for operators switched on in the registry.

## Repository layout

```
operators/            one YAML file per operator, _template.yaml and schema.json
adapters/             code that reads operator feeds (ocpi_221, jolt)
pipeline/registry.py  loads and validates the registry
pipeline/run.py       runs adapters on recorded or live data
pipeline/pricing.py   how prices are shown (pounds and pence only)
pipeline/tariffs.py   the price for each connector, from its tariffs
pipeline/publish.py   writes the map files (GeoJSON layer, detail files, manifest)
pipeline/status.py    builds the feed health page from run logs
pipeline/transparency.py  builds the transparency page
pipeline/build_site.py  assembles the website in a build folder, with MapLibre
site/                 files for the website (map, transparency and privacy pages, security.txt)
site/assets/js/       the map page's scripts (filters, settings, details, map)
package.json          front-end packages (MapLibre, and Lighthouse for tests)
schema/models.py      Location, EVSE, Connector, Tariff and Provenance models
schema/operator.py    the model for an operator registry file
schema/export.py      writes the JSON Schema files
schema/json/          exported JSON Schema for published data
tests/                tests; tests/fixtures/ holds sample data, never live calls
tests/js/             unit tests for the map page's scripts (npm test)
docs/BLUEPRINT.md     the project brief
docs/adr/             records of decisions
```

## The operator registry

Each file in `operators/` describes one operator: which adapter reads its feed, where
the feed is, how access works, and what this project knows about getting access, with
links to evidence. Anything not yet known says "unknown" or "needs_testing".

To add an operator, copy `operators/_template.yaml` to `operators/<id>.yaml`, fill it
in, then run `uv run python -m pipeline.registry --validate`. The template explains
every field.

## Secrets

- Never put a key, token or password in the repository. Operator files give only the
  **name** of a secret in `auth.secret_name`.
- Store the key itself as a GitHub Actions secret: on GitHub, open the repository, then
  **Settings > Secrets and variables > Actions > New repository secret**, and use exactly
  the name from the operator file.
- The pre-commit scanner ([detect-secrets](https://github.com/Yelp/detect-secrets)) checks
  each commit, and CI checks every file. The scanner ignores UUID-shaped strings by
  design, so the registry tests separately reject UUID-shaped values in operator files.
- If the scanner flags something that is not a secret, add the comment
  `pragma: allowlist secret` to that line and explain why in the pull request.
- To report a security problem, see [SECURITY.md](SECURITY.md). GitHub settings that
  protect the repository are listed in [docs/GITHUB_SETTINGS.md](docs/GITHUB_SETTINGS.md).
- Privacy questions and data corrections go through GitHub issue forms. Issues are public,
  so never include personal information.

## Licences

- **Code:** the code written for this project is licensed under the Apache License 2.0
  (see [LICENSE](LICENSE)).
- **Data:** the Apache licence does not cover any data. Data from operators and other
  sources keeps its own licence and belongs to its publishers.
  [DATA_LICENCES.md](DATA_LICENCES.md) lists every source with its licence and
  attribution, and explains how the project keeps to those terms.
