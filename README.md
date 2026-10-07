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

Early days. Blueprint tasks 1 to 4 are done:

1. **Scaffold:** uv, ruff, pytest, pre-commit secret scanning and a CI workflow.
2. **Schema:** Pydantic models for Location, EVSE, Connector, Tariff and Provenance,
   exported as JSON Schema in `schema/json/`.
3. **Operator registry:** one YAML file per operator in `operators/`, with a schema and
   a validator.
4. **OCPI 2.2.1 adapter:** fetches an operator's locations and tariffs politely, page by
   page, and converts them to the schema. char.gy is the first operator switched on.

There is no map yet. The rules the site must follow for privacy and cookies are in
[docs/PRIVACY_AND_COOKIES.md](docs/PRIVACY_AND_COOKIES.md).

## Principles

- Operator feeds come first. OpenStreetMap, Open Charge Map and user reports only fill
  gaps, in separate layers.
- Every record carries its provenance: source, licence, when it was fetched and how far
  to trust it.
- A charger is only ever shown as free when the operator's own tariff says every price
  is zero. A missing tariff means "Price unknown"; missing VAT means "VAT not stated".
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

## Everyday commands

| Task | Command |
|---|---|
| Lint | `uv run ruff check . && uv run ruff format --check .` |
| Fix formatting | `uv run ruff format .` |
| Run the tests | `uv run pytest -q` |
| Validate the operator registry | `uv run python -m pipeline.registry --validate` |
| Run the adapters on recorded data (no network) | `uv run python -m pipeline.run --fixtures` |
| Fetch one page from a real feed | `uv run python -m pipeline.run --live chargy --max-pages 1` |
| Regenerate JSON Schema after changing a model | `uv run python -m schema.export` |
| Run every pre-commit check on every file | `uv run pre-commit run --all-files` |

CI runs all of these on every pull request, except the live fetch: tests never call real
feeds. Use `--live` sparingly. It only works for operators switched on in the registry.

## Repository layout

```
operators/            one YAML file per operator, _template.yaml and schema.json
adapters/             code that reads operator feeds (ocpi_221 so far)
pipeline/registry.py  loads and validates the registry
pipeline/run.py       runs adapters on recorded or live data
schema/models.py      Location, EVSE, Connector, Tariff and Provenance models
schema/operator.py    the model for an operator registry file
schema/export.py      writes the JSON Schema files
schema/json/          exported JSON Schema for published data
tests/                tests; tests/fixtures/ holds sample data, never live calls
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

## Licences

- **Code:** the code written for this project is licensed under the Apache License 2.0
  (see [LICENSE](LICENSE)).
- **Data:** the Apache licence does not cover any data. Data from operators and other
  sources keeps its own licence and belongs to its publishers.
  [DATA_LICENCES.md](DATA_LICENCES.md) lists every source with its licence and
  attribution, and explains how the project keeps to those terms.
