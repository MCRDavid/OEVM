# 0004: Jolt adapter and locations with no publish flag

Date: 2026-10-08. Status: accepted.

## Context

Blueprint task 5 asks for a custom adapter for Jolt. Jolt's API was read on 2026-10-08
(one request for locations, one per tariff). It is close to OCPI 2.2.1 but differs in
ways recorded as dated findings in `operators/jolt.yaml`:

- no OCPI response wrapper and no paging: all 72 locations came in one response;
- locations have no `id` and no `publish` flag, EVSEs have no `uid` or `last_updated`,
  statuses are lower case and some are `preparing`, and some ids are numbers;
- connectors use `CCS2`, and tariffs use plain strings and numbers where OCPI uses
  objects.

The project's rule was that locations with a missing publish flag are never kept, so no
Jolt location would have been shown.

## Decisions

- **Missing publish flags.** On 2026-10-08 the repository owner decided that Jolt's
  locations may be shown, because Jolt publishes the feed itself as open data under the
  regulations. This is recorded in the operator file as `missing_publish_flag` (date,
  basis and evidence) and shown on the transparency page. Without that field, locations
  with no flag are still never kept, and a flag set to false is always respected. Only
  the owner adds this field.
- **Reshape, then reuse.** `adapters/jolt.py` reshapes each Jolt record into an OCPI
  2.2.1 object and passes it to `adapters.ocpi_221.convert_records`, so the publish rule,
  the logging and every model rule are shared with the OCPI adapter. Only differences
  with one clear meaning are reshaped: lower-case statuses that match an OCPI status,
  `CCS2` as `IEC_62196_T2_COMBO`, numbers as strings, the name as the missing location
  id, and `evse_id` as the missing EVSE uid. `preparing` stays unknown.
- **Status time.** Jolt gives no time for EVSE statuses, so each is dated with the time
  it was fetched, which is when Jolt reported it.
- **Plain-number prices.** A `min_price` or `max_price` of 0 means no minimum or
  maximum. Any other plain number does not say whether it includes VAT, so that tariff is
  skipped and shows as price unknown.
- **Safety limits.** The adapter stops with an error if a next page link ever appears,
  fetches at most 100 tariffs per run, and never requests a tariff id containing
  anything other than letters, digits, hyphens and underscores.
- **Fixtures.** `pipeline.run --fixtures` replays recorded responses with a made-up key,
  so CI needs no secret. The real key is only needed for live runs, from the
  `JOLT_API_KEY` environment variable or GitHub Actions secret.

## Other

- Jolt is switched on in the registry. Its terms were checked on 2026-10-07 and
  re-read on 2026-10-08.
- The repository owner chose on 2026-10-08 to keep the current GitHub account name and
  git history for now (see ADR 0003, "Owner's privacy").
