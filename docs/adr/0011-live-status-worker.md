# 0011: Live status through snapshots served by a Worker

Date: 2026-10-09. Status: proposed. The full plan is `docs/PHASE3_PLAN.md`.

## Decisions (proposed)

- **The pipeline fetches; the Worker only serves.** Statuses are fetched by the Python
  pipeline in GitHub Actions, with the same polite client, rate limits, relay and
  normalisers as the daily run, and turned into one snapshot per operator
  (`pipeline/live_snapshot.py`, `schema/live.py`). A second Cloudflare Worker,
  `oevm-live` in `proxy/`, stores the latest snapshot in Workers KV and answers
  `GET /live/<operator>/<location key>` for the map. It never contacts an operator.
- **Separate from the relay.** The relay (ADR 0010) stays as it is, with its own token.
  The live Worker has its own token (`LIVE_TOKEN`), its own folder and its own Git
  integration, so neither can change the other.
- **Changes only, where offered.** Where an operator supports OCPI `date_from` (char.gy),
  a refresh fetches only changed locations and lays them over the previous snapshot. A
  changed location that is no longer to be published, cannot be read or is outside the
  UK is removed at once, and a fetch that did not finish never replaces a snapshot. A
  full fetch still runs daily and replaces the snapshot.
- **Attribution travels with the data.** Every snapshot and every `/live/` answer
  carries the operator's attribution and licence, as the map's detail files do.
- **Staggered and never in parallel.** One hourly workflow in one concurrency group gives
  each operator its full daily fetch in its own slot (owner's decision, 9 October 2026)
  and a status refresh in the other hours, one operator at a time. The run's state, not
  the clock, decides when a full fetch is due, so a missed slot is caught up.
- **Prices once a day** (owner's decision, 9 October 2026), in each operator's full
  fetch, shown only through `pipeline/pricing.py`. The Worker shows none.
- **Counts and colours on the details screen** (owner's request, 9 October 2026): how
  many charge points are available, with green, orange, red and grey groups, each with a
  symbol and words (`site/assets/js/live.js`). The red group uses the same statuses as
  the "Hide out of service" filter (ADR 0012).
- **Open to the map only.** Browsers get a CORS header only for the map's own address.
  Answers are cached for 60 seconds. Nothing about a request is stored or logged.
- **Notices first.** The privacy notice and page footer say that clicking a charger
  contacts Cloudflare before the map makes that request.

## Why

- A Worker fetching operators on each click cannot keep to the project's rate limit rules
  across its instances without extra machinery not checked for the free plan, needs more
  than the 50 subrequests allowed for a full char.gy fetch, and would parse OCPI within a
  10 ms CPU limit. Cloudflare's limits pages, read 9 October 2026.
- KV's free plan allows 1,000 writes a day: one per operator per refresh fits easily.
- Keeping OCPI handling in Python means one set of tested rules.

## Needs the owner's decision

- How char.gy's `WORKING` and `FAULTED`, which are not OCPI statuses, are shown.

## Needs testing

- Whether hourly refreshes from GitHub's servers are refused, as char.gy and GeniePoint
  refused the first daily run on 8 October 2026. char.gy starts at a slower refresh.

- Whether char.gy, GeniePoint and Jolt answer a request for one location by id.
- Snapshot sizes and the CPU time of the first click after a new snapshot.
- Whether Durable Objects are on the free plan (only matters for fetching on click later).

## Not done

- Deploying the Worker, the refresh workflow, the notice changes and the map's status
  line. Each is a later step in the plan, after the repository owner approves.
