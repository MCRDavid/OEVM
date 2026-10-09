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
  full fetch still runs daily and replaces the snapshot.
- **Never in parallel with the daily run.** One scheduled workflow does both kinds of run
  in one concurrency group and picks the kind from the state it finds.
- **Prices stay daily**, shown only through `pipeline/pricing.py`. The Worker shows none.
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

## Needs testing

- Whether char.gy, GeniePoint and Jolt answer a request for one location by id.
- Snapshot sizes and the CPU time of the first click after a new snapshot.
- Whether Durable Objects are on the free plan (only matters for fetching on click later).

## Not done

- Deploying the Worker, the refresh workflow, the notice changes and the map's status
  line. Each is a later step in the plan, after the repository owner approves.
