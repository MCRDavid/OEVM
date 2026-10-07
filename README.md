# OEVM: Open UK EV Charger Map

A free, open map of UK public electric vehicle chargers, built from the open data that
charge point operators must publish under the Public Charge Point Regulations 2023
(regulation 10, OCPI 2.2.1). The aim is prices and availability from operators' own
data, with a data health page and a dated log of how each operator provides access.

The full plan is in [docs/BLUEPRINT.md](docs/BLUEPRINT.md).

## Status

Early days. Blueprint tasks 1 to 3 are done:

1. **Scaffold:** uv, ruff, pytest, pre-commit secret scanning and a CI workflow.
2. **Schema:** Pydantic models for Location, EVSE, Connector, Tariff and Provenance,
   exported as JSON Schema in `schema/json/`.
3. **Operator registry:** one YAML file per operator in `operators/`, with a schema and
   a validator.

Nothing is fetched from operators yet and there is no map yet.

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
| Regenerate JSON Schema after changing a model | `uv run python -m schema.export` |
| Run every pre-commit check on every file | `uv run pre-commit run --all-files` |

CI runs all of these on every pull request.

## Repository layout

```
operators/            one YAML file per operator, _template.yaml and schema.json
pipeline/registry.py  loads and validates the registry
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

## Licence

Code is licensed under the Apache License 2.0 (see [LICENSE](LICENSE)). Licences for
published data will be set out in `DATA_LICENCES.md` when data is first published, as
described in section 6 of the blueprint.
