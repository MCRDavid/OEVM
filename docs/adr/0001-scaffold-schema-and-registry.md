# 0001: Scaffold, schema and operator registry choices

Date: 2026-10-07. Status: accepted.

Decisions made while building blueprint tasks 1 to 3, where the blueprint left a choice
open or where this project departs from it.

## Secret scanning

- **detect-secrets** runs as a pre-commit hook. It is pure Python, so it needs no extra
  toolchain. `detect-private-key` from pre-commit-hooks adds a second check.
- `.secrets.baseline` holds no findings. Its only special rule skips lines of the exact
  form `secret_name: SOME_NAME` (capitals, digits and at least one underscore), because
  those hold secret names, not secrets.
- detect-secrets ignores UUID-shaped strings by design. The registry tests therefore
  reject any UUID-shaped value in `operators/*.yaml`.
- CI runs every hook on every file, then proves the scanner still blocks a fake key.

## Jolt's published key is kept as a secret

The blueprint says Jolt's shared `apiKey` may go in the registry because Jolt publishes it.
This project keeps it in the GitHub Actions secret `JOLT_API_KEY` instead, so that the rule
"no key values in the repository" has no exceptions and the scanner and tests stay simple.

## Schema

- These are the project's own normalised models, not raw OCPI objects.
- `Tariff.price_state` is stored in the output but always derived from the price
  components. Supplying a value that does not match is a validation error, so "free"
  cannot be set by hand.
- `PriceComponent.vat` is null when VAT is not stated, never 0.
- `Connector.standard` keeps the OCPI 2.2.1 ConnectorType value as published. A friendlier
  grouping (for example "CCS") can be derived later without losing the original.
- Location and Tariff ids are `{source}:{country}:{party}:{id}` and must start with the
  provenance `source_id`. Connector `tariff_ids` use the same form.
- Timestamps must carry a time zone.

## Operator registry

- Unknown facts are written as `unknown` or `needs_testing`. Support fields use
  `supported` and `not_supported` rather than `yes` and `no`, because YAML reads unquoted
  `yes` and `no` as true and false.
- Every URL in the seed files appears in the blueprint. Endpoints the blueprint marks as
  unverified have `status: needs_testing`.
- Hosts such as Eco-Movement are not operators and have no registry file. Eco-Movement's
  shared endpoints are repeated in each operator file that uses them. Fuuse, Monta,
  Clenergy, Virta, ChargePoint, Paua, Hubject, Gireve and Zapmap are named in the blueprint
  only as hosts or platforms, so they have no files either.
- Secret names are pre-assigned (for example `BP_PULSE_TOKEN`) so that granting a key only
  needs the secret to be created. One secret per operator, because it is unverified
  whether one Eco-Movement token covers several operators.

## Layout

`schema` and `pipeline` are top-level packages run from the repository root
(`uv run python -m ...`). uv does not build or install the project (`package = false`).
