# 0032: Statuses refreshed every hour and served from the site

Date: 2026-11-12. Status: accepted. The full plan is `docs/PHASE3_PLAN.md`.

ADR 0015 proposed, on 9 October 2026, that a Cloudflare Worker would store and serve
status snapshots. The plan was checked against the map on 9 November 2026 (see the
update in `docs/PHASE3_PLAN.md`), and four questions were put to the repository owner.
This records the answers, given on 12 November 2026. It replaces the serving half of
ADR 0015; the fetching half stands: the pipeline fetches statuses in GitHub Actions with
the same polite client, rate limits and normalisers as the daily run.

## What the check showed

- The map had 46 operators on 9 November 2026, 44 of them fetched from a feed. One
  snapshot per operator every hour is 1,056 Workers KV writes a day; the free plan
  allows 1,000.
- A Worker would mean each visitor's browser contacting Cloudflare, so the privacy
  notice, the footer and the Content Security Policy would have to change first, and the
  owner would have to create the Worker, its store and its secrets.
- The site's own deploy is quick: the deploy job took 27 seconds on 9 November 2026,
  and a whole "Deploy site" run 43 seconds on 12 November. GitHub's limits page (read 9 November 2026) says its soft limit of 10 builds
  an hour "does not apply if you build and publish your site with a custom GitHub
  Actions workflow", which is how this site is deployed.
- GitHub's own schedule started two backup runs more than 8 hours late on 9 November
  2026, so a refresh cannot rely on it (ADR 0024).

## Decisions (the owner, 12 November 2026)

- **The map gets statuses from the site itself.** Each refresh writes status files
  beside the map files and the site is deployed again. No Worker serves statuses, no new
  party sees what a visitor opens, and the privacy notice, footer and Content Security
  Policy stay as they are.
- **Statuses refresh every hour.**
- **Availability shows on the details screen only**, as decided on 9 October 2026:
  counts and colours when a charger is opened, with the time the feed was read. Map
  points, their colours (ADR 0031) and the "Hide out of service" filter (ADR 0012) do
  not change; the filter still says it is from the last daily fetch.
- **The daily fetch stays one run** at 04:17 UTC. The staggered daily fetches in the
  plan of 9 October 2026 are dropped. The hourly refreshes are the small runs spread
  through the day.

## What follows

- **Status files** (`pipeline/live_site.py`, `schema/live.py`). `data/live/<shard>.json`
  holds the statuses of the locations whose key starts with those two characters, the
  same split as the detail files, so opening a charger reads one small file. All 256
  are always written, empty or not. `data/live/index.json` says which operators'
  statuses are in them, when each was read, and each one's attribution and licence.
- **Nothing looks newer than it is.** A status is served only when it was read after
  that operator's data on the map, so after each daily fetch the detail files' own
  statuses stand until the next refresh. Each location carries the time its statuses
  were read, and the details screen shows it.
- **A status never adds or changes a location.** It is laid over a location the daily
  fetch published, with all its checks, and only its EVSEs' status and status time are
  read. Prices, the publish flag, coordinates and everything else come once a day.
- **The same reading of statuses.** A value that is not an OCPI 2.2.1 status is unknown
  unless the operator file records the owner's `nonstandard_statuses` decision, as in
  the daily fetch. A copy an operator sent (ADR 0029) is never refreshed and keeps
  "status unknown".
- **The same rate limits, kept across runs** (`pipeline/refresh.py`). One fetch per host
  at a time; operators with `limits_per_key` take turns; and a host is not asked until
  the longest gap any operator on it keeps has passed since the last run that asked
  feeds ended. The refresh shares the daily fetch's concurrency group, so the two never
  run together. Eco-Movement's networks are asked at their statuses endpoint, one
  request each, within its published limit of "1 request per 30 seconds".
- **A failed or waiting operator keeps its last statuses**, with their own time, until
  a newer refresh or the next daily fetch replaces them.
- **The details screen** (`site/assets/js/live.js`) reads the one status file for the
  charger that was opened, from this site only. Where a refresh read the feed after the
  detail file was made, it shows those statuses, the time the refresh read them under
  the counts, and under "Where this comes from" that the statuses were read again. A
  charge point the refresh did not list shows as unknown, never an older status under a
  newer time. A status file that is missing or cannot be read changes nothing.
- **The workflow** (`.github/workflows/refresh-statuses.yml`, Refresh statuses). Its
  first job stops the run, without asking any feed, when a daily fetch or another
  refresh is waiting or running, or when GitHub cannot say. So a refresh never waits
  in the concurrency group, where GitHub would let it take the place of a daily fetch
  waiting there. Its feed job is in the daily fetch's concurrency group. Once it holds
  the group it reads from the run history when the last feed job of either workflow
  ended, whatever its result (`pipeline/refresh_runs.py`), and the refresh keeps every
  host's gap from then. What it read is kept as the `live-data` artifact, for the
  deploy and for the next refresh.
- **The daily fetch keeps the gap too.** Before it fetches, it waits until the longest
  gap any operator keeps (Roam's, 721 seconds) has passed since the last feed job
  ended. That is seldom any wait.
- **Every deploy packs the newest statuses**: the deploy at the end of a refresh, of
  the daily fetch, and after each change to main. If they cannot be downloaded or
  packed the site is deployed without them, with a warning in the run.
- **The timer is the relay Worker's**, as for the daily fetch (ADR 0024). At half past
  each hour (`30 * * * *` in `relay/wrangler.toml`) it asks GitHub to start Refresh
  statuses, with the token it already has; it reads no feed for this. Half past is
  away from every minute a daily fetch can start at. The run at 04:30 UTC finds the
  daily fetch still going on most days and stops at once, so that hour has the daily
  fetch's statuses. Any timer the Worker does not know as the hourly one starts Fetch
  daily, as before, so the daily fetch cannot be lost to a change in a timer's wording.

## Not done yet

Each is its own pull request:

- Showing the last refresh on the feed health page.
- `proxy/` (the Worker of ADR 0015) is no longer needed for this and was never
  deployed. Whether to remove it is the owner's decision.

## Needs testing

- How long a whole refresh takes from GitHub's servers, and whether any operator
  refuses hourly requests, as char.gy and GeniePoint refused the first daily run on 8
  October 2026.
- How many pages a refresh of char.gy's changes only (`date_from`) takes; until then
  its whole feed is read, about 122 pages at 6 seconds.
- Whether ChargePlace Scotland, Evolt, PoGo, ChargePoint, RAW and BrightGreen statuses
  change during the day. None had changed in the hour before the 9 November 2026 fetch.
- How long a visitor's browser keeps a status file before asking again.
