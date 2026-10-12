# 0024: A timer on the relay Worker starts the daily fetch

Date: 2026-10-12. Status: proposed.

Fetch daily was scheduled on GitHub for 04:17 UTC (ADR 0009). GitHub started it at 11:18
UTC on 9 October 2026, 10:35 UTC on 10 October and 10:48 UTC on 11 October, six to seven
hours late, and had not started it by 11:29 UTC on 12 October. GitHub documents this as
possible: "The `schedule` event can be delayed during periods of high loads of GitHub
Actions workflow runs" and "If the load is sufficiently high enough, some queued jobs may
be dropped" (https://docs.github.com/en/actions/reference/workflows-and-actions/events-that-trigger-workflows,
read 12 October 2026). Why the delay is so long for this repository is not documented and
is unknown. No setting makes GitHub's schedule reliable.

The repository owner asked for a reliable start using what the project already has, and
suggested trying more often and publishing how often the scheduled run works.

## Decisions

- **The relay Worker gets a timer.** Cloudflare Cron Triggers on `oevm-relay`
  (`relay/wrangler.toml`) call the Worker's `scheduled` handler at 04:17 and 06:17 UTC. It
  asks GitHub to start Fetch daily on `main` through the API (`POST
  /repos/{owner}/{repo}/actions/workflows/fetch-daily.yml/dispatches`), with the input
  `started_by: timer`. It tries up to three times, a minute apart, when GitHub is busy or
  unreachable, and throws when it could not, so the failure shows in the Worker's Cron
  Events. It never contacts an operator: the fetch itself still runs on GitHub with the
  same client, rate limits and relay rules as before.
- **Why this Worker.** It already exists, Cloudflare already deploys it from `main`, and
  the owner already manages its secrets. A third-party scheduler (IFTTT, Google Cloud
  Scheduler, Cronhub and similar) would need a new account holding a GitHub token outside
  the project. A second Worker would need its own Cloudflare setup. Cloudflare's free plan
  allows 5 Cron Triggers per account and 10 ms of CPU per trigger; this uses 2, and
  waiting for GitHub uses no CPU (https://developers.cloudflare.com/workers/platform/limits/,
  read 12 October 2026). Cloudflare does not document a delivery guarantee for Cron
  Triggers either, so GitHub's schedule stays as a backup.
- **One token, as small as possible.** The timer uses a Worker secret,
  `GITHUB_DISPATCH_TOKEN`: a fine-grained personal access token for this repository only,
  with **Actions: read and write** and no other permission. GitHub lists the dispatch
  endpoint as needing Actions write
  (https://docs.github.com/en/rest/authentication/permissions-required-for-fine-grained-personal-access-tokens,
  read 12 October 2026). The token can start, cancel and re-run workflows; it cannot change
  code, settings or secrets. It is set in the Cloudflare dashboard, never in the
  repository, and has an expiry date the owner chooses. It is separate from `RELAY_TOKEN`
  and does not open the relay.
- **GitHub's schedule is the backup, three times a day.** `fetch-daily.yml` keeps a
  schedule at 04:47, 10:47 and 16:47 UTC, after the timer's tries and away from the top of
  the hour, so a day the timer misses still gets up to three more chances.
- **Still one fetch a day.** A new first job, "Check whether today's fetch has run"
  (`pipeline/daily_runs.py`), lets a run started by the timer or the schedule fetch only
  if no other run of Fetch daily on `main` has fetched and published that day (UTC). A run
  whose fetch failed, or whose deploy failed, does not count, so the next try fetches and
  deploys again. If GitHub cannot be asked, the run fetches: a second fetch in a day keeps
  every rate limit, while a missed day leaves the map a day older. A run started by hand
  always fetches. The workflow's concurrency group already stops two runs fetching at once,
  so a run that waits behind another checks only after the other has finished. The check
  uses only Python's standard library, so it runs before anything is installed.
- **Each run says how it started.** The workflow's `run-name` reads "Fetch daily
  (Cloudflare timer)", "Fetch daily (GitHub schedule 47 4 * * *)" or "Fetch daily (by
  hand)". Runs before 12 October 2026 are titled "Fetch daily"; a scheduled one among them
  came from the only schedule then, 04:17 UTC.
- **The feed health page shows the record.** Each fetch reads the last 30 days of runs from
  GitHub's API (`pipeline.daily_runs record`, with the workflow's own token and `actions:
  read`) and the page gains "How the daily fetch started": days the map was updated, on
  how many days GitHub's schedule started a run, how many of its runs started within an
  hour of the time set and the median delay, how many days the Cloudflare timer started
  one, and a run-by-run table linking each run on GitHub. If GitHub cannot be asked, the
  fetch carries on and the page says the record could not be read. Wording is dated and
  factual: it reports what GitHub's list of runs shows.

## Not done

- A third-party scheduler. Not needed while the Worker's timer works; the feed health page
  will show if it stops.
- Moving the fetch itself to Cloudflare. ADR 0015 explains why the Worker does not fetch
  operators (rate limits, subrequests, CPU).
- Alerting when the token is about to expire. Whether GitHub emails before a
  fine-grained token expires was not confirmed from its documentation (needs checking), so
  the setup steps ask the owner to note the date. Once it expires, the feed health page
  shows the timer starting no runs, the Worker's Cron Events show the refusal, and the
  schedule takes over.

## Owner setup

`docs/GITHUB_SETTINGS.md`, section 10, steps 12 to 16: make the token, add it as a Worker
secret, check the triggers after the merge deploys, and renew the token before it expires.
