---
name: add-operator
description: Add a UK charge point operator to the OEVM registry, or switch on one whose key has just arrived. Use when asked to add, onboard, enable or record an operator, or when an operator grants a key or token.
argument-hint: "<operator id or name> [key arrived | new | record only]"
---

# Add an operator

Walks through adding one operator to `operators/`, from a first record of what is known
to a fully switched-on feed with fixtures, tests and attribution. CLAUDE.md's hard rules
apply throughout; this skill only puts them in order.

One operator per run and per PR. Never push to main.

## 0. Work out which case this is

Run `uv run python -m pipeline.registry --validate` and read the table it prints.

| Case | Signs | Go to |
|---|---|---|
| **Record only** | The operator has no file yet and no usable feed: the key is not granted, an agreement is needed, or no feed was found | Steps 1, 2, 3, then 9 and 10 with `enabled: false` |
| **New open feed** | No file yet, and the operator publishes a feed that needs no key or publishes a shared key | Every step |
| **Key arrived** | A file exists with `enabled: false` and status `key_on_request`, `requested_no_reply` or `signed_agreement_required`, and the owner says the key is granted | Step 1 (re-check), then 4 onwards |

If another branch or open PR already touches `operators/<id>.yaml`, stop and say so
rather than writing a second copy.

## 1. Find the source, never guess

Only use feed URLs with a known source: the operator's own open data page, its API
documentation, or its data host's documentation. Never take a URL, price or location
from Open Charge Map, OpenStreetMap or user reports. If a page returns a browser check
to automated requests, ask the owner to read it in a browser and say so in the note.

Write down, with the date read:

- the page that gives the feed URLs, and the exact URLs;
- whether a key is needed, and how it is sent (header or query parameter, and its name);
- any rate limit, quoted exactly, with who publishes it;
- any licence or terms for the data, quoted;
- the OCPI version, if stated.

Anything not found is `unknown` or `needs_testing`. Never fill a gap from memory.

## 2. Create the file

Copy `operators/_template.yaml` to `operators/<id>.yaml`. The id is lower case letters,
digits and underscores, matches the file name, and is not one of `osm`, `ocm`, `reports`
or `unknown`.

Fill in, from step 1 only:

- `display_name`: the name as the operator writes it. This exact text is also the
  `DATA_LICENCES.md` row name and the fixture README attribution, and tests match it.
- `ocpi_country_code`, `ocpi_party_id`: `unknown` until read from the feed's own records.
- `adapter`: see the table below.
- `base_url` and `endpoints`: each endpoint `documented` only if the operator or its host
  lists that URL; otherwise `needs_testing`. Never put a key in a URL.
- `auth`: `method`, `name` and `secret_name`. `secret_name` is the NAME of a GitHub
  Actions secret, upper case, for example `<ID>_TOKEN`, never the key and never starting
  with `GITHUB_`. Keys the operator publishes for everyone are still referenced by name only.
- `rate_limit`: see step 3.
- `supports_single_location`, `cors`: `needs_testing` or `unknown` unless tested.
- `sources`: each page used in step 1, with a note of what it says and the date read.
- `engagement.status` and at least one dated `evidence` entry (url, or a file under
  `evidence/<id>/` with no personal names or email addresses).
- `engagement.log`: a dated `page_checked` step for the pages read in step 1, and a
  `request_sent` step (with its `channel`) when access is requested.
- `access_requested`, `access_granted`: the dates of the first `request_sent` and
  `key_granted` steps in the log, or null. The validator checks they match.
- `enabled: false` for now.

| Adapter | State | Used for |
|---|---|---|
| `ocpi_221` | built | Standard OCPI 2.2.1 feeds: paged, or one file holding every record. If the records are OCPI but the wrapper has no `status_code`, set `response_envelope: data_list` and record a finding |
| `custom` | built | Non-standard feeds, one module per operator id in `pipeline/run.py` `CUSTOM_ADAPTERS` |
| `eco_movement_pcpr` | not built yet | bp pulse, Shell Recharge, ubitricity and others hosted by Eco-Movement |
| `gridserve` | not built yet | Gridserve's API |
| `static_file` | not built yet | Downloads that are not OCPI (CSV and similar) |
| `unknown` | | Not yet known |

If the operator needs an adapter that is not built, stop after step 3 with the operator
disabled, and suggest building the adapter as its own issue and PR. Do not build an
adapter inside an add-operator PR, unless it is a `custom` adapter under 150 lines for
this one operator and the owner agrees.

## 3. Rate limits

- `min_seconds_between_requests` is at least 1, and at least each published limit's
  `per_seconds / requests` plus 1 second. The validator rejects anything less.
- Record every published limit with `publisher`, `requests`, `per_seconds`, `endpoint`,
  an exact `quote`, `source_url` and `checked` date. Set `limits_checked` to the date the
  pages were read; with no limits listed, that date means none were stated.
- If another operator file uses the same host, use the same gap. The client keeps one
  timer per host, and `tests/test_rate_limits.py` counts the Eco-Movement operators, so
  adding one there means updating that count.
- With no stated limit, 2 seconds is the usual choice. Say in `notes` that it is the
  project's own choice.

Then run `uv run python -m pipeline.registry --validate`.

## 4. Licence and attribution (before switching on)

Read the operator's own terms. Then fill in:

- `licence`: `name` (usually `OGL-3.0`), `url`, `basis` quoting what the operator's pages
  say and the PCPR 2023 regulation 10(5) and DfT guidance basis, and `checked` with the
  date. If the operator's terms seem to restrict reuse, stop and ask the owner; record
  their decision in `basis` in neutral words, as `operators/geniepoint.yaml` does.
- `attribution`: "Contains data from <display_name> published under the Public Charge
  Point Regulations 2023, used in line with the Open Government Licence v3.0."

Never apply Apache-2.0, or any licence, to data. Never use operator logos or suggest
endorsement.

## 5. The key (gated feeds only)

The owner stores the key; Claude never asks for it in chat, never prints it and never
writes it to any file.

1. The owner adds a repository secret named exactly `auth.secret_name`
   (Settings, Secrets and variables, Actions).
2. Add it to the env of the `fetch` step in `.github/workflows/fetch-daily.yml`, in the
   same form as `JOLT_API_KEY`: `NAME: ${{ secrets.NAME }}`. Secrets go in that step
   only; `tests/test_workflows.py` checks both directions.
3. Update `engagement.status` (for example `key_on_request`), add a dated `key_granted`
   step to `engagement.log` with evidence and no personal details, and set
   `access_granted` to the same date. Keep any signed
   agreement or correspondence in `private/`, which is never committed.

## 6. Record a trimmed fixture

Live calls are for recording only, and sparingly. Tests never call live feeds.

1. Set `enabled: true` in the working copy so `--live` will run it (the validator then
   checks steps 2 to 4 are complete).
2. Record one page into `raw/` (git-ignored, since responses can echo keys). For a gated
   feed this runs where the key is in the environment, usually on the owner's machine:

   ```bash
   uv run python -m pipeline.run --live <id> --max-pages 1 --save-raw raw
   ```

   Read the report it prints: records kept, issues and prices.
3. Copy into `tests/fixtures/<id>/` and trim each file to a handful of records chosen to
   cover the feed's variety (statuses, AC and DC, tariffs, opening hours, quirks).
   Records stay exactly as sent; only `X-Total-Count` may change to match the trimmed
   count. Keep only the content-type and paging headers. Search the files for the key
   and for anything that looks like a credential before going further.
4. Add every tariff the kept locations refer to.
5. Write `tests/fixtures/<id>/manifest.json`:

   ```json
   {"operator": "<id>", "recorded_at": "<UTC time>", "page_size": null, "max_pages": null, "date_from": null}
   ```

6. Write `tests/fixtures/<id>/README.md` on the pattern of
   `tests/fixtures/geniepoint/README.md`: what was requested and when, how it was
   trimmed, then a `## Source and licence` section with the attribution, the source URLs
   and dates, and the line that the data is not covered by this project's Apache-2.0
   code licence.
7. Fill in `ocpi_country_code` and `ocpi_party_id` from the recorded records, with a
   comment saying so and the date.

## 7. Findings

Record each spec difference, data quirk or access issue seen in the recording as a dated
entry in `findings`: one neutral, factual `summary`, the `handling`, an `evidence_url`
and `status`. Describe what was observed, never whether anyone broke a rule; the
validator rejects accusatory words. A record that cannot be used is shown as unknown,
never corrected from another source.

## 8. Tests

Add `tests/test_<id>.py` on the pattern of `tests/test_geniepoint.py`, replaying the
fixture with `ReplayTransport`:

- the requests made match the recorded URLs, and the fetch is complete;
- locations convert with ids starting `<id>:<country>:<party>:`;
- statuses, power types and opening hours come through as expected;
- prices show only through `pipeline/pricing.py`, in GBP, and "Free" only for
  `free_confirmed`;
- each finding's handling actually happens.

`tests/test_guards.py` already checks that an enabled operator has a built adapter,
fixtures, checked licence terms and a `DATA_LICENCES.md` row.

## 9. Licence row and transparency page

- Add a row to the Sources table in `DATA_LICENCES.md`, starting `| <display_name> |`,
  matching the existing rows: data URLs, licence, attribution, what the terms said and
  when, and what the data is used for.
- Regenerate the transparency page:

  ```bash
  uv run python -m pipeline.transparency
  ```

## 10. Check and open the PR

```bash
uv run python -m pipeline.registry --validate
uv run ruff check . && uv run ruff format --check .
uv run pytest -q
uv run python -m pipeline.run --fixtures --publish build
uv run python -m pipeline.transparency --check
uv run pre-commit run --all-files
```

Leave `enabled: true` only if every step is done and the owner has agreed to switch the
operator on; otherwise commit it as `false`. Commit on a branch, open a draft PR, and
in its description list what is still `unknown` or `needs_testing`. If the operator went
live, say that the next daily run will fetch it and that the feed health page shows the
result.
