# Feed adapters plan

Date: 2026-10-09. Status: proposed, waiting for the owner's agreement.

The blueprint (section 1) names five adapters. Two are built: `ocpi_221` and `custom`
(Jolt). This plan splits the three that are not built, and any new ones that operator
research turns up, into one task each. Each task is built in its own issue, branch and
small PR, following the add-operator skill for the operators it unlocks. Nothing here
switches an operator on: that still needs the operator's own terms read and its licence
section filled in.

## Summary

| Task | Adapter | Unlocks | Blocked on | Suggested order |
|---|---|---|---|---|
| A1 | `eco_movement_pcpr` | bp pulse, Shell Recharge, ubitricity, Community by Shell Recharge | A token from at least one operator | 1 |
| A2 | `gridserve` | Gridserve | Gridserve's data terms clarified, then a key | 2 |
| A3 | `static_file` | No current operator; later council CSVs and FOI spreadsheets | A source that needs it | Deferred |
| A4 | To be decided | MFG, Clenergy, Be.EV and others from operator research | Findings from the "More operators from source feeds" thread | After that thread reports |

Operators that need no new adapter, so are not tasks here: Pod (`ocpi_221` once a token
is granted; how tokens are sent is unknown), GeniePoint (already on `ocpi_221`). InstaVolt
and Go Zero have no known feed, so their adapter is unknown until access is arranged.

## What every adapter task includes

- Code under `adapters/`, registered in `pipeline/run.py` `ADAPTERS`.
- Records reshaped into OCPI 2.2.1 and passed to `adapters.ocpi_221.convert_records`, as
  Jolt does (ADR 0004), so the publish flag rule, logging and model rules are shared.
- A trimmed fixture recorded from a real response with `--save-raw`, with its source and
  licence in the fixture manifest. Never examples copied from documentation.
- Tests that use only fixtures, including the rate limit tests in `tests/test_rate_limits.py`.
- Spec differences and quirks recorded as dated findings in each operator file, then the
  transparency page regenerated.
- An ADR for any decision the owner makes along the way.
- The operator stays switched off until its licence section is filled in.

## A1: `eco_movement_pcpr`

**Unlocks:** bp pulse, Shell Recharge, ubitricity and Community by Shell Recharge. All four
operator files already exist, switched off.

**Feed format:** documented as OCPI 2.2.1 on one shared host:

- `GET https://open-chargepoints.com/api/ocpi/cpo/2.2.1/locations` (also `/locations/{id}`)
- `GET https://open-chargepoints.com/api/ocpi/cpo/2.2.1/tariffs`
- `GET https://open-chargepoints.com/api/statuses`: not OCPI; live status, Phase 3 only.

Because the format is documented as OCPI 2.2.1, the adapter is expected to be a thin
layer over `ocpi_221`: it adds the token, always sends an explicit page size (the
documentation gives two different defaults) and does not rely on `date_from` for tariffs
until tested. Whether the responses really are standard OCPI needs testing with a real
token; if they are, the operators may use `ocpi_221` directly and this task shrinks to
configuration and tests.

**Access:** an `Authorization: Token <token>` header. bp pulse uses a request form; how the
other three grant tokens is unknown. Whether one token covers several operators is
unverified, so each operator has its own secret (`BP_PULSE_TOKEN`, `SHELL_RECHARGE_TOKEN`,
`UBITRICITY_TOKEN`, `COMMUNITY_BY_SHELL_RECHARGE_TOKEN`). The Shell UK open data request
page has not been read yet.

**Rate limits:** Eco-Movement publishes 30 requests per hour for locations and for tariffs,
and 1 per 30 seconds for statuses. The operator files take the strictest reading: one
allowance shared by every endpoint and every operator on the host, so 125 seconds between
any two requests to it. Requests are never sent in parallel.

**Main risk:** at 125 seconds a request, the daily job's 60 minute limit fits about 28
requests to this host across all four operators. The page size and record counts are
unknown, so whether a full daily fetch fits needs testing. Options if it does not, for the
owner to choose then: fetch one or two operators a day in turn, use `date_from` for
locations, or ask Eco-Movement whether the limit is per key.

**Licence:** unknown for all four. Each operator's terms must be read when its token is
granted.

**Depends on:** at least one token (the "Operator engagement log" thread handles access
requests). The "Faster fetching within rate limits" thread is changing how
`pipeline/run.py` schedules hosts; build after that lands so the shared host gap is
enforced in one place.

**Before a token arrives:** nothing useful can be built, because fixtures must come from
real responses. The access request is the first step.

## A2: `gridserve`

**Unlocks:** Gridserve. Its operator file exists, switched off.

**Feed format:** `https://api.gridserve.com/ocpi/v1/` with `GET /locations`,
`/locations/{location-id}` and `/tariffs`. The developer documentation (version 1.0,
November 2024) shows results under `locations`, `location` or `tariffs` keys rather than
the OCPI `data` field, and lists `location-id` as a header. The adapter reshapes whatever
the real responses hold into OCPI 2.2.1 records; no paging is documented, so whether the
API pages needs testing.

**Access:** an `ec-subscription-key` header (`GRIDSERVE_SUBSCRIPTION_KEY`), requested
through a form that asks the requester to agree to Gridserve's API Fair Use Policy.

**Rate limits:** Gridserve's policy sets 1 request per 30 seconds per key; the operator file
waits 31 seconds.

**Licence:** unknown. The policy says intellectual property in the API Data stays with
Gridserve and calls it confidential and proprietary, while DfT's guidance says the data
must be open in line with the Open Government Licence. The operator file says to clarify
this with Gridserve before requesting a key.

**Depends on:** the owner deciding to write to Gridserve about the terms, a reply that
allows republishing, then a key. Only after that can a real fixture be recorded.

## A3: `static_file`

**Unlocks:** no current operator. The blueprint planned it for GeniePoint, but GeniePoint's
files turned out to be OCPI 2.2.1 and `ocpi_221` reads them (ADR 0004). Later uses are
council CSVs and FOI spreadsheets, which belong to Phase 4 and Phase 5 in separate layers,
never overwriting operator data.

**Feed format:** CSV or spreadsheet downloads, with a column mapping set in the operator
file. That needs a new section in `schema/operator.py` and a schema export.

**Access, rate limits and licence:** per source. Each source needs its own licence row in
`DATA_LICENCES.md`.

**Suggestion:** defer until a real source needs it, as ADR 0004 already decided. Building
it against no real file would mean guessing the format.

## A4: adapters for newly found operators

The "More operators from source feeds" thread is researching new operators, including
MFG, Clenergy and Be.EV. Its early status notes say MFG and Clenergy have open feeds and
no Be.EV feed was found; the details are not in yet. Operators whose feeds are standard
OCPI 2.2.1 go on `ocpi_221` in that thread with no task here. Each operator that needs
something else gets its own task in this file with the same headings as A1 and A2.

## Suggested order

1. Request access for the Eco-Movement operators and write to Gridserve about its terms
   (engagement log work, not adapter work). Nothing else can start without this.
2. A4 tasks for any open feed found by operator research, since they need no key and can
   be built straight away.
3. A1 `eco_movement_pcpr`, when the first token arrives and after the faster fetching work
   lands.
4. A2 `gridserve`, when the terms are clarified and a key is granted.
5. A3 `static_file`, only when a real source needs it.
