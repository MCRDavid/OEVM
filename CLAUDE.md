# CLAUDE.md

## What this is
Open map of UK public EV chargers from operator open data (Public Charge Point Regulations 2023,
reg 10, OCPI 2.2.1). Static site on GitHub Pages; Python pipeline on GitHub Actions.
The brief is docs/BLUEPRINT.md; decisions are in docs/adr/.

## Commands
- Lint: uv run ruff check . && uv run ruff format --check .
- Test: uv run pytest -q
- Validate registry: uv run python -m pipeline.registry --validate
- After changing a model: uv run python -m schema.export (CI runs it with --check)
- Secret scan and file checks: uv run pre-commit run --all-files
- Offline pipeline (not built yet, task 4 onwards): uv run python -m pipeline.run --fixtures

## Where things live
- schema/models.py: Location, EVSE, Connector, Tariff, Provenance. schema/operator.py: registry file model.
- pipeline/registry.py: registry loader and validator. operators/*.yaml: one file per operator.

## Hard rules
- Never commit or print secrets. Reference keys by secret_name only, even keys an operator publishes.
- Never call live feeds in tests. Use tests/fixtures.
- Never label a charger "Free" unless price_state == free_confirmed.
- Never overwrite operator data with OSM, Open Charge Map or user reports.
- Status wording: neutral, dated, evidenced. No claims that anyone broke the law.
- British English. No em dashes. Write "unknown" or "needs testing" rather than guessing.
- Only use feed URLs with a known source; record the source in the operator file.
- One issue per change; small PRs; never push to main.

## Adding an operator
Copy operators/_template.yaml to operators/<id>.yaml, pick an adapter, set secret_name, and run the
registry validator. Once adapters exist: record a trimmed fixture, add tests, add attribution to
DATA_LICENCES.md, add an evidence entry. A /add-operator skill is planned but not written yet.
