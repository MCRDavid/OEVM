# 0009: Scheduled fetch, deploy and keepalive workflows

Date: 2026-10-08. Status: proposed.

Blueprint task 10: a daily fetch (on a schedule and by hand), a deploy to GitHub Pages
from main, and a keepalive. Accept: three green scheduled runs in a row; site live.

## Decisions

- **`pipeline.run --live all`** fetches every operator enabled in the registry, one after
  another, never in parallel. (Changed 9 October 2026 by ADR 0014: operators that share
  no host are fetched at the same time; operators that share a host still one after
  another.) If one fails, its failure log is written, the others are
  still fetched and published, and the exit code is 2. If every operator fails, nothing
  is published and the exit code is 1.
- **Progress** (added 9 October 2026): live runs print a line as each operator starts and
  finishes, as each module finishes, and for the first and every tenth page before a
  module's last, with the page reached, the percentage done and an estimated time left,
  worked out from the feed's X-Total-Count and the pace so far, never faster than the
  operator's gap (`pipeline/progress.py`). Lines carry operator ids, module names and numbers only, never
  a URL, a key or feed text, and are flushed at once so the Actions log shows them live.
  A full run took about 14 minutes on 8 October 2026, almost all of it char.gy at 6
  seconds a page, and printed nothing until the end.
- **`fetch-daily.yml`** runs at 04:17 UTC each day and from the Actions tab. It validates
  the registry, downloads the last `site-data` artifact to carry the feed health history
  forward (`pipeline.status --previous`), fetches, publishes the map files, builds the
  feed health page, keeps them as a `site-data` artifact for 30 days, then calls the
  deploy workflow. A concurrency group stops two fetches running at once, as two would
  use the same operator hosts in parallel.
- **When one operator fails,** the site is still deployed with the others, so the map
  keeps the rest current and the feed health page shows the failure. That operator's
  chargers are missing from the map until its next good run. A last job then fails, so
  the run shows red and GitHub sends its usual failure email.
- **Keys** are passed by secret name to the fetch step only (today just
  `JOLT_API_KEY`). A test checks every enabled operator's `secret_name` is passed there
  and no other secret is used in any workflow.
- **`deploy.yml`** runs after each change to main, by hand, and at the end of the daily
  fetch. It builds the site from main with the newest `site-data` artifact, using the
  OpenFreeMap basemap (not `--offline-style`), checks the key files are present and
  deploys with `actions/upload-pages-artifact@v5` (with `include-hidden-files`, so
  `.well-known/security.txt` is kept) and `actions/deploy-pages`. A change to main
  therefore never fetches feeds itself. Before the first daily fetch, it fails with a
  message saying to run Fetch daily first.
- **Map data is not committed.** Artifacts carry it between runs, so the repository does
  not grow every day and nothing is ever pushed to main by a workflow.
- **`keepalive.yml`** runs monthly and re-enables the two scheduled workflows through the
  GitHub API (`actions: write` only). It makes no commits, as main is protected.
- **Only main publishes.** Every job checks `github.ref`, so a run started by hand on
  another branch cannot replace the site.

## Needs testing

- Whether re-enabling a workflow through the API restarts GitHub's 60 day count of
  inactivity. GitHub documents the 60 day rule but not this. Other public projects use
  the same approach; it can only be confirmed by watching a quiet repository for 60 days.
- How long a full char.gy fetch takes. The fetch job allows 60 minutes.
- Action versions: `actions/upload-artifact@v4`, `actions/download-artifact@v4` and
  `actions/deploy-pages@v4` were pinned from memory, as their release pages could not be
  checked from the build environment. Dependabot proposes newer versions weekly.

## Not done yet

- Keeping yesterday's data for an operator whose fetch failed, instead of leaving it out.
- The status snapshot every 30 to 60 minutes (blueprint section 2).
- A custom domain, so `security.txt` sits at the top of a domain (see
  `docs/GITHUB_SETTINGS.md`).
