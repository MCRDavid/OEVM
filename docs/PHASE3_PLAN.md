# Phase 3 plan: live status and prices

Status: proposed, 9 October 2026. Nothing in this plan is switched on. The map, the daily
run and the relay are unchanged. ADR 0011 records the main decision.

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
| char.gy | 6 s, our choice (no published limit) | Works: recorded 7 October 2026 (`tests/fixtures/chargy/locations_since_page1.json`) | Needs testing | About 120 pages of 50 |
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
   (`schema/live.py`): every EVSE's status and its time, keyed like the map's detail files.
   For char.gy, a run fetches only the locations that changed since the last one and lays
   them over the previous snapshot, so a refresh needs a few requests, not 120.
3. The run sends each snapshot to the live Worker (`proxy/worker.js`) with a shared token.
   The Worker keeps the latest one per operator in Workers KV.
4. When a visitor opens a charger, the map asks the Worker
   `GET /live/<operator>/<location key>` and shows "Status as of HH:MM" from the
   snapshot's time. If the Worker does not answer, the map keeps today's behaviour.

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

### Never in parallel with the daily run

Both runs use the same operator hosts, so they must never overlap. GitHub's concurrency
groups are not enough on their own: a group keeps one waiting run, and a newer one
**cancels** the waiting one, so an hourly snapshot could cancel a waiting daily run.

Recommendation: one scheduled workflow replaces both. Every run fetches in the same
concurrency group, and each run decides what to do from the state it finds: a full fetch
and site deploy if none has finished today, otherwise a status refresh. A daily run that
is cancelled or fails is then done by the next run.

### Stage B: fetching one location on click (later, only if worth it)

For an operator that confirms single-location fetching and allows enough requests, the
Worker could fetch that location on click, cached for 60 seconds. It needs a gate per host
so requests keep their gap across instances, and keyed feeds would read their keys from
Worker secrets (blueprint, section 1). Consider it only after Stage A has run within the
free plan, and only after the single-location tests below.

### Prices

DfT's guidance says the price "must be opened on the same basis as other reference data",
which the daily run already fetches. Recommendation: prices stay in the pipeline, shown
only through `pipeline/pricing.py`. A status refresh can also fetch char.gy's tariffs that
changed (`date_from` worked on tariffs on 7 October 2026, with no results); a changed price
then reaches the map at the next deploy. The Worker shows no prices.

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
- **Wording on the map:** neutral and dated: "Status as of 14:05, from the operator's
  feed". Never imply an operator is late or at fault.

## What the repository owner sets up by hand (when Stage A is approved)

1. In Cloudflare, create a second Worker named `oevm-live` from this repository with the
   Git integration, as for the relay (`docs/GITHUB_SETTINGS.md`, section 10), but with
   root directory `proxy`, builds only for changes under `proxy/`, and previews off.
2. Create a KV namespace (for example `oevm-live-snapshots`) and send its id. The id goes
   in `proxy/wrangler.toml` as the `SNAPSHOTS` binding; it is not a secret.
3. Add a Worker secret `LIVE_TOKEN` (a new random value, not the relay's token).
4. Add two GitHub Actions secrets, named `OEVM_LIVE_URL` (the Worker's address) and
   `OEVM_LIVE_TOKEN` (the same random value as the Worker secret).
5. Decide the refresh interval. Recommendation: hourly to start.
6. Confirm visitors' browsers may contact Cloudflare's `workers.dev` address on click,
   with the notice changes above.

Nothing in GitHub Pages or the relay changes.

## Steps, one issue and pull request each

1. **This pull request:** this plan, ADR 0011 (proposed), the snapshot format and builder,
   and the Worker, with tests. Nothing deploys and the site is unchanged.
2. **Single-location tests:** one request per switched-on operator, sparingly, to see
   whether `{locations}/{id}` works. Record the results as dated findings in each operator
   file and regenerate the transparency page.
3. **Status refresh run:** a locations-only option for the adapters, the merged workflow
   described above, and sending snapshots to the Worker. Measure snapshot sizes.
4. **Measure the Worker:** real snapshots, CPU time in Cloudflare's dashboard, and the
   headers on its answers. Split snapshots if CPU is too high.
5. **Notices, then the map:** the notice changes above, then the "Status as of" line in
   the detail panel (text only, nothing stored on the device).
6. **Thirty days** within the free plan, measured from Cloudflare's dashboard, completes
   Phase 3. Then decide whether Stage B is worth building.

## Unknowns

- Single-location fetching for char.gy, GeniePoint and Jolt: **needs testing**.
- Durable Objects on the free plan, and Cloudflare headers on `workers.dev`: **need checking**.
- Snapshot sizes and CPU per click: **estimates; need measuring**.
- How often char.gy, GeniePoint and Jolt update statuses in their public feeds: **unknown**.
  Report the age we measure; never claim an operator breaks the 30-second rule in
  regulation 10(4), which applies to the data they hold, not the public copy.
