# 0003: Transparency page, rate limits, GBP pricing, security and privacy of the owner

Date: 2026-10-07. Status: accepted.

## Transparency page

- `pipeline/transparency.py` builds `site/transparency/index.html` and
  `site/data/transparency.json` from the registry only, so the committed page is
  reproducible and CI checks it is up to date. Its "last reviewed" date is the latest date
  in the registry, not today's date.
- Run logs (`pipeline.run --log-dir`) can be added with `--runs`. They hold counts and
  logged problems, never records or keys. A failed run writes a log too, so failures show
  on the page. The committed page never includes run logs: building with `--runs` needs
  `--out`, and the daily fetch (blueprint task 10) will publish that build.
- Findings are recorded by hand in each operator file (`findings:`), dated, with a kind
  (spec conformance, data quality, access, documentation), how the project handles each
  one, and evidence.
- Published wording passes a coarse check for accusatory words (`neutral_text`). It is a
  safety net, not a replacement for careful wording.
- The page has no scripts, no cookies and no third-party files, and shows the short
  disclaimer and the required links.

## Rate limits

- The regulations set no limit on how often data users may request data. Regulation
  10(4)'s 30-second rule is a duty on operators to update status data. DfT guidance allows
  "terms and conditions covering the means of access", which is where operators' limits
  come from.
- Project floor: at least 1 second between any two requests to a host.
- Each operator's published limits are recorded as numbers, with the exact quote, source
  and date checked. The registry rejects a gap shorter than any limit needs plus a 1
  second safety margin. One gap covers every endpoint, so the strictest limit decides it.
  The client also works the gap out again itself, so a gap that skipped validation
  cannot make it faster.
- The gap is measured from when the previous response finished, so uneven network delays
  can never bring two requests closer together at the server than the gap.
- Timers are kept per host and shared by every client in the process, so operators served
  from the same host (the four Eco-Movement operators) share one gap and one Retry-After.
  Timers live in memory: runs that use the same host must never be started in parallel,
  and a future scheduled workflow needs a concurrency group for that.
- Every Retry-After is honoured, in seconds or as an HTTP date, on any attempt including
  the last. One that cannot be read counts as a one hour wait. A wait longer than 600
  seconds makes the client stop and send nothing more to that host until it has passed.
- Tests simulate the client with a fake clock, check arrival times at the server with
  uneven network delays, and count windows inclusively. Eleven deliberately broken
  versions of the client and registry were each caught by the tests (2026-10-08).
- Re-checked on 2026-10-07: Eco-Movement publishes 30 requests an hour for locations,
  single locations and tariffs, and 1 per 30 seconds for statuses, so its operators use a
  125 second gap.
- Checked on 2026-10-08: Gridserve's API Fair Use Policy sets a default of 1 request per
  30 seconds per API key, although its developer documentation states no limit. The
  policy's limit is recorded with an exact quote, Gridserve uses a 31 second gap, and the
  difference is a finding on the transparency page. Each published limit now names its
  publisher (the operator, or the company hosting its data), and the page shows it.

## Prices

- `pipeline/pricing.py` is the only way prices are shown: pounds and pence, GBP tariffs
  only. Other currencies show as "Price unknown" with the reason, and are never
  converted. Regulation 10(6)(d)(iv) describes the price in reference data as "the price
  in pence per kilowatt hour".
- VAT is added only when every component that costs something states it; otherwise
  prices are shown as published, which OCPI defines as excluding VAT, and marked
  "excluding VAT, VAT not stated". Sums use exact decimal arithmetic, so half pennies
  round up. Reservation fees are not shown as charging prices.

## Security

- `SECURITY.md` asks for private reports through GitHub's private vulnerability
  reporting. `site/.well-known/security.txt` follows RFC 9116 and lists the report form
  first and `SECURITY.md` second, because private reporting must be switched on by hand
  (GitHub's public API showed it off on 2026-10-08), and `SECURITY.md` gives a fallback
  route. A test fails 30 days before its Expires date.
- security.txt only works at the top of a domain, so a GitHub Pages project site needs a
  custom domain or a `<user>.github.io` repository. Publishing with
  `actions/upload-pages-artifact@v4` drops dot folders; use v5 with
  `include-hidden-files: true`.
- `.github/dependabot.yml` sets weekly grouped updates for uv and GitHub Actions. Settings
  that must be switched on by hand are listed in `docs/GITHUB_SETTINGS.md`.
- Privacy questions and data corrections use issue forms that warn issues are public.
- Keys are only sent over https; the registry rejects plain http feed URLs for operators
  that need a key, and the client refuses to send one. Anything a server sends back
  (headers, links, bodies, error text and logged issues) has the key removed before it
  is saved or shown, in case a server echoes it.
- Run logs are checked against a fixed list of fields before the transparency page uses
  them, and each log must be named after its operator.
- CI checks the locked dependencies against known vulnerabilities with pip-audit, because
  Dependabot alerts may not read `uv.lock`.

## Owner's privacy

- The owner's name, location and places they use were removed from every file. Synthetic
  test data now uses an obviously made-up place (Exampletown, 52.0, -1.0).
- Jolt's published key was replaced in the blueprint's example command by
  `$JOLT_API_KEY`, so no key value is in the current files. It remains in git history,
  and a test checks that no tracked file contains a key-shaped value again.
- The repository URL lives in one place (`pipeline/project.py`), plus security.txt and
  the issue forms, so it is easy to change if the repository moves.
- Removing text from the current files does not remove it from git history or from the
  GitHub account name. That decision is the owner's.
