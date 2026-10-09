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
| A1 | `eco_movement_pcpr` | bp pulse, Shell Recharge, ubitricity, Community by Shell Recharge | A token from at least one operator | 2 |
| A2 | `gridserve` | Gridserve | A key | 3 |
| A3 | `static_file` | No current operator; later council CSVs and FOI spreadsheets | A source that needs it | Deferred |
| A4 | None yet | MFG and Clenergy on `ocpi_221`; Fastned, Believ and others once their format is known | Nothing for MFG and Clenergy; access for the rest | 1 |
| A5 | Basic auth for `ocpi_221` | Osprey | Osprey confirming the method and granting credentials | When credentials arrive |

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
unknown, so whether a full daily fetch fits needs testing. The owner expects the limit
applies per operator key rather than to the whole platform. If Eco-Movement confirms
that in writing, the gap can apply per key: requests still go one at a time from one
address, but turns between the four operators' keys, so a full fetch takes about a
quarter of the time. Until then the strictest reading stays. Sending requests from
several addresses to get round a limit is not an option: the project's rules forbid
rotating addresses (CLAUDE.md, ADR 0010). Other options if the fetch does not fit: fetch
one or two operators a day in turn, or use `date_from` for locations.

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

**Licence:** OGL v3.0. The policy says intellectual property in the API Data stays with
Gridserve and calls it confidential and proprietary. On 2026-10-09 the repository owner
decided that regulation 10(5), which requires the data to be available without terms on
its use, takes priority, and that the project goes ahead without first writing to
Gridserve. This is recorded in its operator file, `DATA_LICENCES.md` and the transparency
page. The published rate limit is still followed.

**Depends on:** a key, requested through Gridserve's form. Only after that can a real
fixture be recorded. Its documentation suggests `ocpi_221` with a header key may be
enough; untested.

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

## A4: newly found operators

The "More operators from source feeds" thread checked each operator's own pages on
2026-10-09. Its results, as reported to this plan:

**No new adapter needed:**

- MFG EV Power: `ocpi_221` (added in its own PR from that thread).
- Clenergy EV: full-file OCPI on `https://api.clenergy.online/development/pcpr/`, no key.
  The response wrapper uses `name` and `message` rather than `status_code` and
  `status_message`, and responses carry `X-RateLimit-Limit: 6` with no window stated. Both
  are recorded as findings when it is added; if `ocpi_221` rejects the wrapper, that is a
  small change to `ocpi_221`, not a new adapter.

**Format unknown until access is granted:** Fastned (API keys; its Fair Use Policy claims
all rights in the data and says it "may throttle"), Believ (free self-serve registration;
documentation only visible after login), Giga Power, EV Smart (says OCPI, no terms),
Blink and Ionity (all by request). Each gets an A-numbered task in this file once a real
response shows it is not standard OCPI.

**No feed found:** Be.EV, Go Zero (the documented address now returns 404), Tesla,
Connected Kerb and Sainsbury's Smart Charge.

No operator found publishes a CSV or other non-OCPI file, which supports deferring A3.

## A5: HTTP Basic authentication

**Unlocks:** Osprey, which reportedly sends credentials by email for HTTP Basic
authentication. That comes from the OSM wiki only and is not verified on Osprey's own site.

**Change:** not a new adapter. Add a `basic` auth method to `schema/operator.py` and
`adapters/http.py`, with the user name and password read from secrets named in the operator
file and never logged, then run the schema export. `ocpi_221` then reads the feed as normal.

**Depends on:** Osprey confirming the method and granting credentials. Building it before
then would be guessing.

## Suggested order

Decided by the owner on 2026-10-09: sources that need no key come first.

1. MFG and Clenergy on `ocpi_221`, owned by the "More operators from source feeds" thread
   (MFG is in its own PR). Believ's free registration is the quickest way to learn another
   feed's format.
2. Request keys for the Eco-Movement operators and Gridserve, and ask Eco-Movement whether
   its limits apply per key (engagement log work, not adapter work).
3. A1 `eco_movement_pcpr`, when the first token arrives and after the faster fetching work
   lands.
4. A2 `gridserve`, when a key is granted.
5. A5 Basic auth, when Osprey grants credentials.
6. A3 `static_file`, only when a real source needs it.
