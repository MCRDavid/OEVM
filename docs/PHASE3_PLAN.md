# Phase 3 plan: live status and prices

Status: proposed, 9 October 2026, and updated the same day with the repository owner's
answers below. Nothing in this plan is switched on, and the daily run and the relay are
unchanged. The one change visible on the map is the owner's reading of char.gy's
statuses (see "char.gy's statuses"). ADR 0015 records the main decision.

## Decided by the repository owner (9 October 2026)

- **Prices once a day.** Prices change rarely; one fetch a day is enough.
- **Live availability is the point.** The details screen shows how many charge points at
  the location are available, colour coded: green for available, orange for in use, red
  for out of service, and another colour for other statuses (see "The details screen").
- **Stagger the operators.** Each operator's daily fetch runs at its own time of day, so
  no single run is large and no GitHub or Cloudflare limit is approached.

The blueprint's Phase 3 is done when "clicking shows live status with a timestamp" and
the service stays "within the free tier for 30 days" (docs/BLUEPRINT.md, section 10). Its
main risks are the Worker's CPU limit and operators' rate limits.

## What we know

### Cloudflare's free plan (read 9 October 2026)

From https://developers.cloudflare.com/workers/platform/limits/:

- "CPU time per HTTP request | 10 ms"
- "Subrequests per invocation | 50"
- "Number of Cron Triggers per account | 5"
- "Scheduled Workers have a maximum wall time of 15 minutes per invocation."

From https://developers.cloudflare.com/kv/platform/limits/:

- "100,000 reads per day"; "1,000 writes per day" to different keys; writes to the same
  key "1 per second"; values up to "25 MiB".

Not checked: whether Durable Objects are on the free plan, and whether Cloudflare adds
Network Error Logging headers to `workers.dev` responses. Both **need checking** before
the steps that depend on them.

### The operators switched on today

| Operator | Gap between requests | Changes only (`date_from`) | One location by id | Whole network in |
|---|---|---|---|---|
| char.gy | 6 s, our choice (no published limit); 4 s in PR #21 | Works: recorded 7 October 2026 (`tests/fixtures/chargy/locations_since_page1.json`) | Needs testing | About 120 pages of 50 |
| GeniePoint | 2 s, through the relay | Not offered: one file | Needs testing | One file |
| Jolt | 2 s | Not offered (`adapters/jolt.py`) | Needs testing (only `tariffs/{id}` is documented) | One request for locations |

The gated operators waiting for keys (Gridserve, 31 s; Eco-Movement operators, 125 s)
document fetching one location, but their published limits allow too few requests for a
fetch on every click.

## Design: snapshots first

### Stage A: snapshots built by the pipeline, served by the Worker

1. A scheduled GitHub Actions run fetches each switched-on operator's statuses with the
   same polite client, rate limits, relay and normalisers as the daily run.
2. `pipeline/live_snapshot.py` turns them into one small snapshot per operator
   (`schema/live.py`): every EVSE's status and its time, keyed like the map's detail
   files, with the operator's attribution and licence. For char.gy, a run fetches only the
   locations that changed since the last one and lays them over the previous snapshot. A
   location that comes back with its publish flag false, unreadable or outside the UK is
   removed at once. A fetch that does not finish never replaces the snapshot.
   How many requests a refresh takes **needs measuring**: the 7 October fixture
   (`locations_since_page1.json`) reports 551 locations changed in about 90 minutes, so an
   hourly refresh may be about 7 to 12 pages of 50, or under a minute at 4 seconds a page,
   against about 120 pages for a full fetch.
3. The run sends each snapshot to the live Worker (`proxy/worker.js`) with a shared token.
   The Worker keeps the latest one per operator in Workers KV.
4. When a visitor opens a charger, the map asks the Worker
   `GET /live/<operator>/<location key>` and shows the counts and coloured groups below,
   with the time the feed was read. If the Worker does not answer, the map keeps today's
   behaviour.

The Worker never contacts an operator. Visitors' requests never reach one either.

### Why the Worker does not fetch operators itself

- **Rate limits.** The project never goes below an operator's gap and never runs two
  fetches to one host in parallel. Many Worker instances answering many visitors cannot
  keep to that without extra machinery (a Durable Object per host), which is not checked
  for the free plan.
- **Subrequests.** A full char.gy fetch takes about 120 requests; the free plan allows 50
  per invocation.
- **CPU.** Parsing a whole network's OCPI data in 10 ms is the blueprint's flagged risk.
  The snapshot is parsed once per Worker instance, and stored as sent, without parsing
  each location.
- **One set of rules.** OCPI quirks, status mapping, publish flags and findings stay in
  the Python pipeline, which the tests already guard. Nothing is written twice.
- **Keys.** No key needs to reach Cloudflare in Stage A.

### Budgets (estimates; measure them)

- **KV writes:** one per operator per refresh. Three operators hourly is 72 a day; every
  30 minutes is 144. The limit is 1,000.
- **KV reads and Worker requests:** at most one each per click. The blueprint's
  illustration of 500 visitors making 10 clicks is 5,000 a day; the limit is 100,000.
- **Snapshot size:** the fixtures give about 100 bytes per EVSE, so char.gy's 5,948
  locations would be roughly 0.6 to 1 MB. This is an **estimate**; a live run will show.
- **CPU per click:** a cached parse costs almost nothing; the first click after a new
  snapshot parses it. Whether that fits in 10 ms **needs measuring** (Cloudflare's
  dashboard shows CPU time). The fallback is to split each snapshot into 16 parts by the
  first character of the key, at 16 writes per operator per refresh, with fewer refreshes.

### Staggered daily fetches, never in parallel

Following the owner's decision, each operator gets its own daily slot for its full fetch
(locations and tariffs, so prices once a day), and status refreshes fill the hours between.

- **One scheduled workflow** replaces `fetch-daily`. It runs once an hour. In each run,
  operators whose slot it is get a full fetch; every other switched-on operator that is
  due gets a status refresh (locations only, no tariffs).
- **Builds on PR #21 (fetching hosts at the same time).** Each hourly run uses that
  pull request's host groups: operators that share no host run at the same time, and
  operators that share a host (or the relay) run one after another in one group, so two
  requests never go to the same host at once. Gaps come from each operator file, so
  char.gy's 4 second gap from PR #21, the owner's choice, applies here too.
- **Slots belong to host groups, not single operators.** Operators that share a host
  share one daily slot and one request budget, worked out from `rate_limit.limits` plus
  the 1 second margin. A refresh for a host is skipped when it would not fit that budget.
- **Refresh interval per operator.** Feeds that are one whole file (GeniePoint, Jolt, and
  MFG EV Power and Clenergy EV in PRs #25 and #28) re-download the whole locations file on
  every refresh; MFG's two files are about 3.6 MB. They start at every 2 or 3 hours, as
  does char.gy (see "Unknowns and risks"), and the interval goes in each operator file
  when the workflow is built.
- **Example slots (UTC):** char.gy 02:17, GeniePoint 03:17, Jolt 04:17, MFG EV Power
  05:17, Clenergy EV 06:17: quiet times, away from the top of the hour. New host groups
  get the next free slot. These are a starting point, not a requirement.
- **State, not the clock, decides.** A run gives an operator a full fetch when its slot
  has passed and no full fetch of it has finished today, so a slot missed through a
  delayed or failed run is caught up by the next run. The state is each snapshot's
  `full_fetch_at`, read back from the Worker (`GET /snapshot/<operator>`), which a
  refresh needs anyway; if the Worker cannot be read, the run does a full fetch.
- **Only full fetches publish.** A status refresh uploads no `site-data` artifact and
  writes no feed health run log. Otherwise the next run would pick up a partial artifact
  as the newest (`.github/scripts/download-site-data.sh` takes the newest), and a
  locations-only log would replace the day's full figures on the feed health page
  (`pipeline/status.py` keeps the latest run each day). That script, its wording, which
  names "Fetch daily", and ADR 0009 change with the workflow.
- **One concurrency group.** GitHub keeps one waiting run per group, and a newer one
  **cancels** the waiting one. With a single hourly workflow that is harmless: the newer
  run does the same work, and the state rule above catches up any missed full fetch.
- **Publishing carries the others forward.** A full fetch of one operator rebuilds the
  map files from that operator's new data and the other operators' files from the last
  deploy (the daily run already downloads them for the feed health history). This needs
  a change to `pipeline/publish.py` and is part of step 3 below.
- **Limits.** Each run is small: a char.gy refresh is probably 7 to 12 pages (see Stage A,
  needs measuring); GeniePoint, Jolt, MFG EV Power and Clenergy EV are one request each
  for locations. At a refresh every 2 or 3 hours, char.gy gets roughly 60 to 140 extra
  requests a day, at its usual gap. GitHub-hosted runners are free on public
  repositories (blueprint, section 9). The site deploys up to three times a day instead
  of once. Cloudflare sees one KV write per operator per hour (72 a day for three) and
  one or two relay requests an hour for GeniePoint.

### Stage B: fetching one location on click (later, only if worth it)

For an operator that confirms single-location fetching and allows enough requests, the
Worker could fetch that location on click, cached for 60 seconds. It needs a gate per host
so requests keep their gap across instances, and keyed feeds would read their keys from
Worker secrets (blueprint, section 1). Consider it only after Stage A has run within the
free plan, and only after the single-location tests below.

### Prices

Decided: once a day, in each operator's full fetch, shown only through
`pipeline/pricing.py`. DfT's guidance says the price "must be opened on the same basis as
other reference data", which this keeps to. Status refreshes do not fetch tariffs, and the
Worker shows no prices.

## The details screen

At the top of the details screen, above the connectors, the map will show:

- **A summary line:** "2 of 4 charge points available". A charge point is an OCPI EVSE,
  which charges one vehicle at a time. Only when every status is unknown: "Status
  unknown for 4 charge points". Blocked charge points count as not available.
- **Coloured chips** for each group that has any charge points, each with a symbol and a
  written count, such as "● 2 available", "◐ 1 in use", "✕ 1 reported out of service".
  The symbol is hidden from screen readers (`aria-hidden`), like the dots in the map's
  key, so they read only the words.
- **The operator's attribution and licence**, which every live answer carries, as the
  map's detail files do.
- **When the feed was read:** "Status from the operator's feed, read 9 Oct 2026, 14:05
  BST". Never "live" or "now", because the feed itself may lag.
- **Each connector** keeps its own status line, coloured to match its group.

| Group | Colour (light / dark mode) | OCPI 2.2.1 statuses |
|---|---|---|
| Available | Green `#17733a` / `#6fd08f` | available |
| In use | Orange `#8a5300` / `#ffc46b` | charging, reserved |
| Reported out of service | Red `#8a2a12` / `#ffab91` | out_of_order, inoperative, planned, removed |
| Blocked, working or status unknown | Grey `#4d5559` / `#b4bcc2` | blocked, unknown, and "working" (not an OCPI status; see below) |

- "Reported out of service" uses exactly the statuses of the map's "Hide out of service"
  filter (ADR 0012, `OUT_OF_SERVICE` in `pipeline/publish.py`); a test keeps them the same.
  "Blocked" usually means a parked vehicle, so it is not counted as out of service.
- Every colour has at least 4.5:1 contrast on the page and panel backgrounds in both
  modes (checked 9 October 2026 with the WCAG formula). Colour is never the only cue:
  every chip has a symbol and words, as ADR 0008 requires.
- The wording, groups and colours are in `site/assets/js/live.js` and `site/assets/app.css`,
  tested, but not used by the map until the Worker runs.

### char.gy's statuses (decided 9 October 2026)

char.gy publishes `WORKING` and `FAULTED`, which are not OCPI 2.2.1 statuses (finding of
7 October 2026 in `operators/chargy.yaml`). Regulation 10(6)(a) uses "working" to mean an
OCPI status of available, charging or reserved, so `WORKING` cannot say whether a charge
point is free or in use. The repository owner chose to show `WORKING` as "Working (free or
in use, not stated)", in grey, never counted as available, and `FAULTED` as reported out
of service. The decision is recorded in `nonstandard_statuses` in the operator file and on
the transparency page, and the pipeline applies it from the next run. A summary line for
such a location reads "4 of 4 charge points working (free or in use, not stated)".

Because `FAULTED` is now out of order, the map's "Hide out of service" filter (ADR 0012)
also hides char.gy charge points the feed reports as faulted, and the details panel shows
the new wording, once this pull request is merged. The feed health page still counts
`WORKING` as no OCPI status, so its figures do not change.

## Notices to change before the map calls the Worker

The map would make a new request on each click, to the Worker's `workers.dev` address,
which Cloudflare runs. Before that ships:

- **Privacy notice** (`docs/PRIVACY_AND_COOKIES.md`, then `pipeline/privacy.py`):
  Cloudflare receives the visitor's IP address and the location key asked for; the Worker
  stores and logs nothing about requests (observability is off in `proxy/wrangler.toml`);
  and, if found, any Cloudflare headers on the answer, as for OpenFreeMap. Following the
  owner's earlier decision, a Cloudflare header is acceptable only if the notice says so.
- **Page footer** (`site/index.html`): the same short statement.
- **Transparency page:** say which operators have live status and how old it can be.
- **Wording on the map:** neutral and dated: "Status from the operator's feed, read
  9 Oct 2026, 14:05 BST". Never imply an operator is late or at fault.
- **Content Security Policy** (`site/index.html`): add the Worker's address to
  `connect-src`, or the browser will refuse the request.
- **Data licences:** the Worker passes on operator data, so `DATA_LICENCES.md` says so,
  and every answer carries the operator's attribution and licence.

## What the repository owner sets up by hand (when Stage A is approved)

1. In Cloudflare, create a second Worker named `oevm-live` from this repository with the
   Git integration, as for the relay (`docs/GITHUB_SETTINGS.md`, section 10), but with
   root directory `proxy`, builds only for changes under `proxy/`, and previews off.
2. Create a KV namespace (for example `oevm-live-snapshots`) and send its id. The id goes
   in `proxy/wrangler.toml` as the `SNAPSHOTS` binding; it is not a secret.
3. Add a Worker secret `LIVE_TOKEN` (a new random value, not the relay's token).
4. Add two GitHub Actions secrets, named `OEVM_LIVE_URL` (the Worker's address) and
   `OEVM_LIVE_TOKEN` (the same random value as the Worker secret).
5. Decide how often statuses refresh. Recommendation: hourly to start, which the
   staggered workflow above assumes.
6. Confirm visitors' browsers may contact Cloudflare's `workers.dev` address on click,
   with the notice changes above.

Nothing in GitHub Pages or the relay changes.

## Steps, one issue and pull request each

1. **This pull request:** this plan, ADR 0015 (proposed), the snapshot format and builder,
   the Worker, the details screen's groups, wording and colours, and the owner's reading
   of char.gy's statuses, with tests. Nothing deploys. Only the char.gy wording and the
   "Hide out of service" filter's handling of its faulted charge points change on the map.
2. **Single-location tests:** one request per switched-on operator, sparingly, to see
   whether `{locations}/{id}` works. Record the results as dated findings in each operator
   file and regenerate the transparency page.
3. **Staggered workflow, after PR #21 merges:** a locations-only option for the adapters,
   publishing that carries other operators forward, the hourly workflow with daily slots
   per host group described above, a refresh interval in each operator file, and sending
   snapshots to the Worker. Measure snapshot sizes.
4. **Measure the Worker:** real snapshots, CPU time in Cloudflare's dashboard, and the
   headers on its answers. Split snapshots if CPU is too high.
5. **Notices, then the map:** the notice changes above, then the summary line, chips and
   coloured statuses on the details screen (text only, nothing stored on the device).
6. **Thirty days** within the free plan, measured from Cloudflare's dashboard, completes
   Phase 3. Then decide whether Stage B is worth building.

## Unknowns and risks

- **Refusals from GitHub's servers.** char.gy and GeniePoint both refused requests from
  GitHub Actions runners in the first daily run (findings of 8 October 2026 in their
  operator files). Hourly refreshes mean many more runs from the same address ranges.
  Start char.gy at a slower refresh (every 2 or 3 hours) and raise it only if the feed
  health page shows no refusals. If a feed refuses, refresh less often; never shorten the
  gap or disguise the requests.

- Single-location fetching for char.gy, GeniePoint and Jolt: **needs testing**.
- Durable Objects on the free plan, and Cloudflare headers on `workers.dev`: **need checking**.
- Snapshot sizes and CPU per click: **estimates; need measuring**.
- How often char.gy, GeniePoint and Jolt update statuses in their public feeds: **unknown**.
  Report the age we measure; never claim an operator breaks the 30-second rule in
  regulation 10(4), which applies to the data they hold, not the public copy.
