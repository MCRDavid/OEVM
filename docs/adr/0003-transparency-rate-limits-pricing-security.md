# 0003: Transparency page, rate limits, GBP pricing, security and privacy of the owner

Date: 2026-10-07. Status: accepted.

## Transparency page

- `pipeline/transparency.py` builds `site/transparency/index.html` and
  `site/data/transparency.json` from the registry only, so the committed page is
  reproducible and CI checks it is up to date. Its "last reviewed" date is the latest date
  in the registry, not today's date.
- Run logs (`pipeline.run --log-dir`) can be added with `--runs`. They hold counts and
  logged problems, never records or keys. The committed page never includes them; the
  daily fetch (blueprint task 10) will add them when it publishes the site.
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
- Project floor: at least 1 second between any two requests to an operator.
- Each operator's published limits are recorded as numbers, with the exact quote, source
  and date checked. The registry rejects a gap shorter than any limit needs. One gap
  covers every endpoint of an operator, so the strictest limit decides it.
- Tests simulate the client with a clock that only moves when it waits, so responses take
  no time (the worst case). For every operator in the registry they check the gap between
  requests, retries included, and the count in every window of each published limit.
  A deliberately broken client (no waiting) fails 13 of these tests.
- When a server asks for a wait longer than this project will make (Retry-After over 600
  seconds), the client gives up and sends nothing more to that server until the wait has
  passed, rather than retrying early.
- Re-checked on 2026-10-07: Eco-Movement publishes 30 requests an hour for locations,
  single locations and tariffs, and 1 per 30 seconds for statuses, so its operators use a
  120 second gap. Gridserve's developer documentation states no limit; the 30 second gap
  from earlier research is kept and the difference is shown on the transparency page.

## Prices

- `pipeline/pricing.py` is the only way prices are shown: pounds and pence, GBP tariffs
  only. Other currencies show as "Price unknown" with the reason, and are never
  converted. Regulation 10(6)(d)(iv) describes the price in reference data as "the price
  in pence per kilowatt hour".
- VAT is added only when every component states it; otherwise "VAT not stated".
  Reservation fees are not shown as charging prices.

## Security

- `SECURITY.md` asks for private reports through GitHub's private vulnerability
  reporting. `site/.well-known/security.txt` follows RFC 9116 and lists the report form
  first and `SECURITY.md` second, because the report form's address could not be checked
  from the cloud session. A test fails 30 days before its Expires date.
- security.txt only works at the top of a domain, so a GitHub Pages project site needs a
  custom domain or a `<user>.github.io` repository. Publishing with
  `actions/upload-pages-artifact@v4` drops dot folders; use v5 with
  `include-hidden-files: true`.
- `.github/dependabot.yml` sets weekly grouped updates for uv and GitHub Actions. Settings
  that must be switched on by hand are listed in `docs/GITHUB_SETTINGS.md`.
- Privacy questions and data corrections use issue forms that warn issues are public.

## Owner's privacy

- The owner's name, location and places they use were removed from every file. Synthetic
  test data now uses an obviously made-up place (Exampletown, 52.0, -1.0).
- Jolt's published key was replaced in the blueprint's example command by
  `$JOLT_API_KEY`, so no key value is in the repository.
- The repository URL lives in one place (`pipeline/project.py`), plus security.txt and
  the issue forms, so it is easy to change if the repository moves.
- Removing text from the current files does not remove it from git history or from the
  GitHub account name. That decision is the owner's.
