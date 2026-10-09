# CLAUDE.md

## What this is
Open map of UK public EV chargers from operator open data (Public Charge Point Regulations 2023,
reg 10, OCPI 2.2.1). Static site on GitHub Pages; Python pipeline on GitHub Actions. A personal,
experimental, AI-assisted learning project (see DISCLAIMER.md). The brief is docs/BLUEPRINT.md;
decisions are in docs/adr/.

## Commands
- Lint: uv run ruff check . && uv run ruff format --check .
- Test: uv run pytest -q
- Validate registry: uv run python -m pipeline.registry --validate
- Validate plan providers: uv run python -m pipeline.plans --validate
- Offline pipeline: uv run python -m pipeline.run --fixtures
- Map files from fixtures: uv run python -m pipeline.run --fixtures --publish build (never site/)
- Feed health page: uv run python -m pipeline.run --fixtures --log-dir logs, then
  uv run python -m pipeline.status --runs logs --out build
- One live page (sparingly, enabled operators only): uv run python -m pipeline.run --live chargy --max-pages 1
- Daily run (workflows only, not locally): uv run python -m pipeline.run --live all --log-dir logs --publish build
- After changing a model: uv run python -m schema.export (CI runs it with --check)
- After changing operators/*.yaml: uv run python -m pipeline.transparency (CI runs it with --check)
- After changing the notice in docs/PRIVACY_AND_COOKIES.md: uv run python -m pipeline.privacy (CI runs it with --check)
- Secret scan and file checks: uv run pre-commit run --all-files
- Dependency audit: see the pip-audit and npm audit steps in .github/workflows/ci.yml
- Map page: npm ci, then uv run python -m pipeline.run --fixtures --publish build and
  uv run python -m pipeline.build_site --out build (add --offline-style for tests)
- Front-end tests: npm test; browser tests and Lighthouse: CHROME_PATH=<chrome> uv run pytest -q -m e2e

## Where things live
- schema/models.py: Location, EVSE, Connector, Tariff, Provenance. schema/operator.py: registry file model.
- adapters/http.py: polite client. adapters/ocpi_221/: paging and OCPI conversion. adapters/replay.py: fixtures.
- pipeline/registry.py, pipeline/run.py. operators/*.yaml: one file per operator.
- pipeline/pricing.py: the only way prices are shown. pipeline/tariffs.py: price per connector.
- providers/*.yaml: charging plans from providers' own pages (schema/provider.py, pipeline/plans.py,
  ADR 0016, providers/README.md). Plans only where the provider's terms allow reuse; never
  estimate a price. Permission requests to the others are tracked in providers/README.md.
- pipeline/transparency.py: site/transparency/. pipeline/publish.py: map files; schema/published.py.
- pipeline/geography.py and pipeline/data/: whether a point is in the UK (Natural Earth outlines).
- pipeline/status.py: feed health page. schema/runlog.py: run log format. pipeline/health.py: figures.
- pipeline/project.py: repository URL (also in site/index.html, site/.well-known/security.txt and .github/ISSUE_TEMPLATE).
- site/index.html, site/assets/: the map page. pipeline/build_site.py: build folder with MapLibre.
- proxy/: Phase 3 live status Worker, not deployed (docs/PHASE3_PLAN.md). pipeline/live_snapshot.py, schema/live.py: its snapshots.
- .github/workflows/: ci, fetch-daily (cron, calls deploy), deploy (Pages from main), keepalive.

## Hard rules
- Never commit or print secrets. Reference keys by secret_name only, even keys an operator publishes.
- Never call live feeds in tests. Use tests/fixtures.
- Never label a charger "Free" unless price_state == free_confirmed.
- Never overwrite operator data with OSM, Open Charge Map or user reports. Record bad values as unknown.
- Status wording: neutral, dated, evidenced. No claims that anyone broke the law.
- British English. No em dashes. Write "unknown" or "needs testing" rather than guessing.
- Only use feed URLs with a known source; record the source in the operator file.
- One issue per change; small PRs; never push to main.
- No personal details of the owner anywhere: no name, location or places they use.

## Prices and rate limits
- Show prices only through pipeline/pricing.py: pounds and pence, GBP tariffs only. Never convert
  currencies; other currencies show as "Price unknown".
- Never go below 1 second between requests to a host, or below any limit in an operator's
  rate_limit.limits plus a 1 second margin. Record each published limit with its publisher, an
  exact quote, source URL and date; tests enforce these rules. Never run two fetches that use the same host in parallel.
- Record spec differences, data quirks and access issues as dated findings in the operator file,
  in neutral words, then regenerate the transparency page.
- Record every access request, follow-up, reply and check as a dated step in engagement.log
  (see operators/_template.yaml); saved replies go in evidence/<id>/ with names and addresses removed.

## Data licences (DATA_LICENCES.md)
- Apache-2.0 covers our code only. Never apply it, or any other licence, to data. Data keeps its source's licence.
- Every record keeps its provenance. Every source gets attribution and a row in DATA_LICENCES.md.
- Never use operator logos or suggest any operator or public body endorses the project.
- Show an EVSE status that is not an OCPI 2.2.1 value as anything but unknown only when the
  operator file records the owner's decision in nonstandard_statuses; never add one yourself.
- Never keep locations whose OCPI publish flag is false. Keep ones with no flag only when the
  operator file records the owner's decision in missing_publish_flag; never add one yourself.
- Map only locations whose coordinates are genuinely in the UK (pipeline/geography.py, ADR 0016).
- Correct coordinates only where the operator file records the owner's decision in
  swapped_coordinates, and only obvious latitude/longitude swaps (ADR 0013); show and record each one.
- Switch an operator on only after reading its own terms and filling in its licence section.
- Fetch through the relay (relay/worker.js) only when the operator file records the owner's
  decision in relay; only feeds that need no key; same User-Agent and rate limits; never
  rotate addresses or disguise the project. Cloudflare deploys relay/ from main (relay/wrangler.toml).

## The site (docs/PRIVACY_AND_COOKIES.md)
- No analytics, ads, tracking or third-party files that set cookies or use storage.
- Text from feeds goes into the page as text only (textContent), never as HTML.
- Tests never contact the basemap (OpenFreeMap): use --offline-style.
- Nothing is stored on a visitor's device until they opt in; "Forget my settings" deletes it all.
- Every page shows the short disclaimer and links to DISCLAIMER.md, data sources, the privacy notice
  and SECURITY.md.

## Security (SECURITY.md)
- Vulnerabilities, leaked keys and personal data are reported privately, never in public issues.
- Renew Expires in site/.well-known/security.txt before it lapses; a test fails 30 days ahead.

## Adding an operator
Copy operators/_template.yaml to operators/<id>.yaml, pick an adapter, set secret_name, read the
operator's terms and fill in licence, then run the registry validator. Record a trimmed fixture with
--save-raw, add tests, add a row to DATA_LICENCES.md and an evidence entry. The /add-operator skill
(.claude/skills/add-operator/SKILL.md) walks through each step, including when a key arrives.
