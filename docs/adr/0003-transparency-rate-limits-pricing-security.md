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

### Amendment, 22 October 2026: VAT added where a feed gives none

- The owner asked for every price on the map to include VAT, so prices can be compared.
  OCPI 2.2.1 reads a price with no VAT rate as having no VAT, but VAT on public charging
  in the UK is at the standard rate of 20%. In the daily run of 22 October 2026, 10 of the
  12 operators fetched gave a rate on their prices; char.gy and Clenergy EV gave none.
- char.gy's own pricing page gives each price 20% above its feed (39p against 32.5p).
  Clenergy EV's website gives no charging prices, but 120 of the 126 prices per kWh in
  its feed come to a whole penny, to within 0.02p, once 20% is added (0.4167 becomes 50p);
  only 23 are whole pence as published. That reading is inferred and needs confirming.
- So the owner's decision is recorded per operator in `vat_not_stated` (decided, basis,
  evidence and `add_percent`). Where it is recorded, `pipeline/pricing.py` adds that rate
  to every price component that gives no VAT rate; a component with its own rate keeps
  it. The price says "including VAT, with VAT at 20% added by this project where the
  operator's feed does not state it", and a minimum charge has the rate added too. A
  tariff follows the decision of the operator whose feed published it, so a related
  operator's tariff (ADR 0020) follows its own file. The tariffs are published unchanged.
- Without a decision nothing changes: such prices are shown as published and marked
  "excluding VAT, VAT not stated". Only the owner adds a decision.
- The transparency page shows each decision in the operator's row, dated findings in
  both operator files, and a "VAT in prices" section on what was seen across operators.
- A last good copy kept from before the decision (ADR 0018) keeps its prices until the
  operator's next good fetch.

### Amendment, 23 October 2026: stated VAT read as already in the price

- BrightGreen's feed gives every price with VAT 20 and also a `price_display` field, not
  in OCPI 2.2.1, equal to the price as written: price "0.59", VAT 20 and price_display
  "£0.59" (12 of 12 tariffs on 23 October 2026). Read as OCPI says, that is 70.8p per kWh
  including VAT, while the display price shows 59p. Which one drivers pay is not stated.
- The owner decided the prices are read as the display price shows them. The decision is
  recorded per operator in `vat_in_price` (decided, basis, evidence). Where it is
  recorded, `pipeline/pricing.py` adds nothing to a price component that states its VAT,
  and the price says "including VAT, read as the operator's display price shows it". A
  component that gives no rate is still marked "VAT not stated"; this decision never
  supplies a rate. A minimum charge is read the same way.
- An operator cannot record both `vat_in_price` and `vat_not_stated`. The tariffs are
  published unchanged, the transparency page shows the decision in the operator's row and
  in its "VAT in prices" section, and only the owner adds one.

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
