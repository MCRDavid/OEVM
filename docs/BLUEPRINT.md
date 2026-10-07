# Open UK EV Charger Map: Project Blueprint and Claude Code Kickoff Brief

**Bottom line: yes, one person can build this at close to zero cost. Use a plug-in registry of operator feeds, a static map on GitHub Pages, and later a small Cloudflare Worker for live prices and status. The legal position is better than you feared: the open data duty in regulation 10 of the Public Charge Point Regulations 2023 covers every public charge point run by a non-micro-business operator, whatever its power. The 8kW threshold only applies to contactless payment.**

## TL;DR

- **Build it as a data pipeline plus a static site.** Each operator gets one YAML file in a registry and uses one of five reusable adapters. GitHub Actions fetches reference data and tariffs daily and publishes slim GeoJSON to GitHub Pages. In Phase 3, a free-tier Cloudflare Worker holds API keys and serves cached live status when a visitor clicks a charger. Visitors' browsers do not call operator feeds directly.
- **No login in Phase 1.** Visitor preferences live in the browser and in shareable URL parameters. All admin happens through GitHub: registry files, secrets, workflow runs, issues and pull requests. User reports come in through GitHub issue forms. The project holds no personal data.
- **Sub-8kW public chargers are covered by the open data duty if the operator is not a micro-business.** The real gaps are micro-business operators, chargers outside the "public" definition (workplace, residential, manufacturer-only, occupation-only) and operators that gate their feeds. Fill these from Open Charge Map, OpenStreetMap, FOI requests and user reports, each with a clear provenance badge.

## Key decisions

| Question | Decision | Confidence |
|---|---|---|
| Login? | **No.** No accounts in Phase 1 | High |
| Live fetching straight from the browser to operator feeds? | **No, as a rule.** Use a caching proxy (Cloudflare Worker). Direct calls fail for keyed feeds, rely on untested CORS, expose visitors' IP addresses to operators and break rate limits | High |
| Sub-8kW chargers covered by the open data duty? | **Yes**, for public charge points of non-micro-business operators. Regulation 10 has no power threshold | High (direct reading of the SI and DfT guidance) |
| Source hierarchy | Operator feed, then Open Charge Map, then OSM, then user reports, all with provenance | High |
| "Free" label | Only when the operator's tariff explicitly says free. A missing tariff shows "Price unknown" | High |
| Code licence | Apache-2.0 or MIT. Do not copy ocpdb code unless you accept AGPL-3.0 | Medium (your choice) |
| Data licence | Operator data under OGL v3.0 with per-operator attribution; OSM data in a separate ODbL layer | Medium |

---

## 1. Pluggable operator feeds

### Verified facts

- The regulations define the data standard: "'data requirement' means version 2.2.1 of the Open Charge Point Interface protocol" (reg 2, SI 2023/1168, https://www.legislation.gov.uk/uksi/2023/1168/made). [legislation](https://legislation.gov.uk/uksi/2023/1168/made)
- DfT guidance says operators must open the location, EVSE and connector objects (OCPI 8.3.1 to 8.3.3) and "the tariff object", and that "the price may change regularly but this must be opened on the same basis as other reference data" (https://www.gov.uk/government/publications/the-public-charge-point-regulations-2023-guidance/public-charge-point-regulations-2023-guidance). [www](https://www.gov.uk/government/publications/the-public-charge-point-regulations-2023-guidance/public-charge-point-regulations-2023-guidance)
- The same guidance allows operators to "employ a third party to assist in the hosting and communication of the required data". [www](https://www.gov.uk/government/publications/the-public-charge-point-regulations-2023-guidance/public-charge-point-regulations-2023-guidance) This is why white-label hosts such as Eco-Movement exist.
- **mobidata-bw/ocpdb** (https://github.com/mobidata-bw/ocpdb) is licensed AGPL-3.0. Its README lists one row per source, with `name`, `uid`, `realtime` and `credentials` columns, and each source has its own importer. [github](https://github.com/mobidata-bw/ocpdb) [github](https://github.com/orgs/mobidata-bw/repositories) Copy that pattern as an idea, not as code. Since March 2026 its API serves OCPI 3.0, and since April 2026 it also has DATEX II endpoints (https://mobidata-bw.de/dataset/e-ladesaulen). [mobidata-bw](https://mobidata-bw.de/dataset/e-ladesaulen) The README says some shared libraries "are served from binary butterfly's private package index". [github](https://github.com/mobidata-bw/ocpdb) **Reusing its code directly may therefore be awkward as well as bringing AGPL obligations.**

### Recommended design

Keep one YAML file per operator in `/operators`, checked against a schema in CI:

```yaml
# operators/chargy.yaml
id: chargy
display_name: char.gy
ocpi_country_code: GB
ocpi_party_id: CGY            # from tariff path /GB/CGY/; confirm from data
adapter: ocpi_221             # ocpi_221 | eco_movement_pcpr | gridserve | static_file | custom
base_url: https://char.gy/open-ocpi
auth: {method: none, secret_name: null}   # secret NAME only, never the value
rate_limit: {min_seconds_between_requests: 2}
supports_single_location: needs_testing
cors: needs_testing
attribution: "Contains data from char.gy published under the Public Charge Point Regulations 2023, used in line with the Open Government Licence v3.0."
engagement:
  status: open_anonymous
  evidence: [{date: 2026-10-06, url: "https://help.char.gy/support/solutions/articles/77000576948-public-charge-point-regulations-2023"}]
access_requested: null
access_granted: null
enabled: true
```

| Adapter | Covers | Notes |
|---|---|---|
| `ocpi_221` | char.gy, Pod (once a token is granted), any standard OCPI feed | Handles offset/limit and Link-header pagination, plus `date_from` |
| `eco_movement_pcpr` | bp pulse, Shell Recharge, ubitricity, Community by Shell Recharge (per the OSM wiki) | [openstreetmap](https://wiki.openstreetmap.org/wiki/EV_charge_points_in_the_United_Kingdom) Same endpoints for every operator; only the token differs |
| `gridserve` | Gridserve | `ec-subscription-key` header; [gridserve](https://www.gridserve.com/wp-content/uploads/2024/11/GRIDSERVE-PCPR-API-Developer-Documentation.pdf) slow rate limit |
| `static_file` | GeniePoint downloads, council CSVs, FOI spreadsheets | Column mapping set in YAML |
| `custom` | Jolt and anything non-standard | Under 150 lines each, fully tested |

Adding an operator once a key is granted takes three steps: copy a YAML file, store the key as a secret under its `secret_name`, and record one fixture response. A Claude Code skill (`/add-operator`) can walk you through this.

### Eco-Movement PCPR API

- Eco-Movement's PCPR reference pages list two endpoints on `open-chargepoints.com`:
  - `GET https://open-chargepoints.com/api/ocpi/cpo/2.2.1/tariffs` ("Returns raw tariffs that were shared with Eco-Movement by the CPOs using OCPI"), limited to "30 requests per 1 hour". [eco-movement](https://developers.eco-movement.com/reference/get-tariffs-pcpr-api)
  - `GET https://open-chargepoints.com/api/statuses` ("Returns realtime updates for all EVSES of a CPO"), limited to "1 request per 30 seconds". [eco-movement](https://developers.eco-movement.com/reference/get-statuses-pcpr-api)
  - Sources: https://developers.eco-movement.com/reference/get-tariffs-pcpr-api and https://developers.eco-movement.com/reference/get-statuses-pcpr-api.
- The PCPR locations page says the endpoint returns "a list of all locations or a specific location (using the location's id)", and that "Eco-Movement recommends that you retrieve the entire dataset once a day" (https://developers.eco-movement.com/reference/locations-pcpr-api). [eco-movement](https://developers.eco-movement.com/reference/locations-pcpr-api) The exact locations URL is **unverified**; it is probably `https://open-chargepoints.com/api/ocpi/cpo/2.2.1/locations`.
- Eco-Movement's general Data API uses an `Authorization: Token <token>` header (https://developers.eco-movement.com/reference/getting-started-data-api). [eco-movement](https://developers.eco-movement.com/reference/getting-started-data-api) The PCPR pages show a header credential, so the PCPR API probably works the same way (**likely, not confirmed**).
- Access appears to be granted per operator. AMPECO describes Eco-Movement as handling requests through "a request form in the CPOs' website" (https://www.ampeco.com/blog/eco-movement-solve-station-visibility-and-compliance/). [ampeco](https://www.ampeco.com/blog/eco-movement-solve-station-visibility-and-compliance/) bp pulse's FAQ also uses a request form. [bppulse](https://www.bppulse.com/en-gb/help-and-support/public-ev-charging/public-charge-point-regulations) **Whether one token covers several operators is unverified**, so plan for one secret per operator.
- **Other multi-operator hosts** (Fuuse, Monta, Clenergy, Virta, ChargePoint, Paua, Hubject, Gireve, Zapmap): no public PCPR endpoints were found. AMPECO now offers Eco-Movement through its marketplace, so AMPECO-based operators may end up on the same API. That is an **inference**.

### OCPI libraries

No maintained OCPI 2.2.1 client in Python or TypeScript with a checked licence was verified. Write your own Pydantic models for the subset you need, following the official spec PDF cited in the regulations (https://evroaming.org/app/uploads/2021/11/OCPI-2.2.1.pdf), and export JSON Schema from them for the front end.

### Secrets

- Scheduled fetches read keys from **GitHub Actions secrets**, referenced by name in the registry. In Phase 3, the Worker reads them from **Cloudflare Worker secrets**.
- Never commit any of the following: keys, tokens, Basic auth credentials, signed agreements, `.env` files, raw responses that echo keys, or correspondence containing personal email addresses. Protect against this with `.gitignore`, a pre-commit secret scanner and a Claude Code hook that blocks edits to secret-like files.
- Jolt publishes a shared `apiKey` on its own help page (https://support.joltcharge.com/hc/en-gb/articles/27955558493207-UK-Public-Charge-Point-Regulations-Open-Data-Request). [joltcharge](https://support.joltcharge.com/hc/en-gb/articles/27955558493207-UK-Public-Charge-Point-Regulations-Open-Data-Request) [joltcharge](https://support.joltcharge.com/hc/en-gb/articles/27955558493207-UK-Public-Charge-Point-Regulations-Open-Data-Request) Because it is public, it can go in the registry with that link. Expect Jolt could revoke it.

---

## 2. Live price and availability on demand

### PCPR timing provision (exact text)

> "A charge point operator must ensure that EVSE object status data held in accordance with paragraph (1) is updated within 30 seconds of a change from one EVSE object status to another EVSE object status." (reg 10(4)) [legislation](https://legislation.gov.uk/uksi/2023/1168/made)

This applies to the data the operator **holds**. Regulation 10(5) separately requires data to be "made available to the public free of charge and in a machine readable format without any requirement to agree to terms and conditions regarding the use of that data", [ldodds](https://blog.ldodds.com/2023/07/13/the-public-charge-point-regulations-and-other-examples-of-open-data-and-standards-in-uk-legislation/) [legislation](https://legislation.gov.uk/uksi/2023/1168/made) but sets no explicit delay limit for the public copy. So report the staleness you measure rather than claiming an operator has breached the 30-second rule.

### Fetching a single location

- OCPI 2.2.1 lets a client fetch one Location, EVSE or Connector by ID (`{locations_url}/{location_id}[/{evse_uid}[/{connector_id}]]`). This is from general knowledge of the spec and was **not re-read here**, so confirm it against the PDF.
- **Gridserve** explicitly documents `GET /locations/{location-id}` (https://www.gridserve.com/wp-content/uploads/2024/11/GRIDSERVE-PCPR-API-Developer-Documentation.pdf). [gridserve](https://www.gridserve.com/wp-content/uploads/2024/11/GRIDSERVE-PCPR-API-Developer-Documentation.pdf) **Eco-Movement** documents fetching a single location by ID. [eco-movement](https://developers.eco-movement.com/reference/get-specific-location)
- **char.gy** documents only `/open-ocpi/locations` and `/open-ocpi/tariffs`, [char](https://help.char.gy/support/solutions/articles/77000576948-public-charge-point-regulations-2023) so fetching by ID **needs testing**. **Jolt** documents only `tariffs/{tariffId}`, [joltcharge](https://support.joltcharge.com/hc/en-gb/articles/27955558493207-UK-Public-Charge-Point-Regulations-Open-Data-Request) so fetching a location by ID **needs testing**. [joltcharge](https://support.joltcharge.com/hc/en-gb/articles/27955558493207-UK-Public-Charge-Point-Regulations-Open-Data-Request) **GeniePoint** and **Go Zero** are **unknown**.
- OCPI has **no bounding-box query**, so the options are:
  - fetch everything daily and build your own spatial index (recommended);
  - fetch live by ID, using the IDs from your daily index;
  - poll whole-network status endpoints on a timer.

### CORS: needs testing (no documented results found)

Run these and check the response for an `access-control-allow-origin` header:

```bash
curl -s -D - -o /dev/null -H "Origin: https://example.github.io" "https://char.gy/open-ocpi/locations"
curl -s -D - -o /dev/null -H "Origin: https://example.github.io" "https://api.joltcharge.com/v1/uk/public/locations?apiKey=$JOLT_API_KEY"
```

Even if CORS turns out to be open, route requests through your proxy. It keeps visitors' IP addresses private, respects rate limits and gives you caching.

### Proxy options and free tiers

| Option | Free tier (as found) | Verified? |
|---|---|---|
| **Cloudflare Workers** | 100,000 requests/day, 10 ms CPU per request, 50 subrequests per request, 5 cron triggers; KV 100,000 reads/day; static asset requests free | [github](https://github.com/cloudflare/cloudflare-docs/blob/production/src/content/docs/workers/platform/limits.mdx) [cloudflare](https://developers.cloudflare.com/workers/platform/pricing/) Yes, Cloudflare docs (https://developers.cloudflare.com/workers/platform/pricing/). Cloudflare's blog adds that the KV free tier includes "1,000 each of write, list and delete operations per day" and that over-limit operations "will fail with an error" (blog.cloudflare.com/workers-kv-free-tier) |
| Deno Deploy, Vercel, Netlify, Val Town, Fly.io | Not checked | **Not verified** |
| Raspberry Pi behind Cloudflare Tunnel | Your own hardware | Not verified; depends on your home broadband |

**Recommendation: Cloudflare Workers (free plan).** Cache responses for 60 to 120 seconds with the Cache API rather than KV, because the free KV write allowance is small. On the free plan, going over the limit makes requests fail; you are not billed. [blazingcdn](https://blog.blazingcdn.com/en-us/cloudflares-pricing-for-developers-a-closer-look-at-workers-pages) The 10 ms CPU limit may be too tight for parsing a whole network's status, so test that early (**uncertain**).

### Hybrid plan

1. **Daily (Actions):** full locations and tariffs for every operator, published with `fetched_at`.
2. **Every 30 to 60 minutes (Actions):** status snapshot for open feeds, labelled "status as of HH:MM".
3. **On click (Worker, Phase 3):** `GET /live/<operator>/<location_id>`, cached for 60 seconds, returning normalised statuses with `fetched_at`. Some operators allow only one request per 30 seconds: Gridserve (from earlier research, not re-verified) and Eco-Movement `/statuses`. For those, serve from a cached network-wide snapshot.

**Volume (illustrative):** 500 visitors a day making 10 clicks each is 5,000 Worker requests, or 5% of the free tier. But a one-request-per-30-seconds limit allows only 2,880 calls a day, so snapshot mode is mandatory for those operators.

### Re-serving gated data

The guidance says: "The data must be made available without any requirement to agree to terms and conditions regarding the use of that data. However, terms and conditions covering the means of access to the data and API(s) are permissible." [www](https://www.gov.uk/government/publications/the-public-charge-point-regulations-2023-guidance/public-charge-point-regulations-2023-guidance) In practice:

- Honour access terms such as rate limits and keeping keys private.
- Treat "no redistribution" clauses as inconsistent with reg 10(5).
- Do not breach anything you have signed. Before signing an agreement such as InstaVolt's "Open Data Agreement" (https://instavolt.co.uk/public-charge-point-regulation-data/), ask in writing whether you may republish with attribution, and record the reply. [instavolt](https://instavolt.co.uk/public-charge-point-regulation-data/) This is general information, not legal advice.

---

## 3. Status pages and "name and shame"

### Two separate pages

**(a) Feed health (automatic):** for each operator, show:
- last success and last attempt;
- HTTP status;
- record counts;
- % of locations with valid UK coordinates;
- % of connectors with a resolvable tariff;
- % of EVSEs with a status;
- median `last_updated` age;
- schema errors with examples;
- a 30-day trend.

**(b) Engagement (manual, with evidence):**

| Label (neutral) | Meaning |
|---|---|
| Open, no registration | Anonymous machine-readable feed |
| Open, published shared key | Key published by the operator (e.g. Jolt) |
| Key issued on request | Form or email, no contract |
| Signed agreement required | Contract needed before access (e.g. InstaVolt) |
| Requested, no reply after N days | Dated request |
| Request declined | Dated refusal, quoted |
| No public feed found | Search date and method stated |
| Possibly out of scope | E.g. the operator says it is a micro-business |

Each label links to dated evidence in `/evidence/<operator>/`, with no personal names or emails. Generate both pages as static HTML from the pipeline's logs. Upptime-style monitors only check whether a URL responds, not data quality.

### Government accountability: verifiable facts

- Schedule para 26 says the enforcement authority "must from time to time publish information on (a) civil sanctions that have been imposed; and (b) enforcement undertakings that have been agreed", unless it "considers that publication would be inappropriate". [legislation](https://legislation.gov.uk/uksi/2023/1168/made)
- OPSS publishes half-yearly enforcement lists up to 31 March 2026 (https://www.gov.uk/government/publications/opss-enforcement-actions). [www](https://www.gov.uk/government/publications/opss-enforcement-actions) The **1 October 2025 to 31 March 2026** list contains only Construction Products and Product Safety entries, with **no PCPR entries**. [www](https://www.gov.uk/government/publications/opss-enforcement-actions/opss-enforcement-actions-1-october-2025-to-31-march-2026) [www](https://www.gov.uk/government/publications/opss-enforcement-actions/opss-enforcement-actions-1-october-2025-to-31-march-2026) The earlier lists and the OPSS enforcement undertakings page were **not checked**. Check them before publishing any claim that there has been no enforcement.
- Fleet News (12 May 2026) reported: "The OPSS did not respond to requests for comment on how it is enforcing the regulations, whether any operators have been fined". ChargeUK said calls for immediate enforcement "may be premature" (https://www.fleetnews.co.uk/news/charge-point-enforcement-concerns-raised-over-ev-uptime-rules). [fleetnews](https://www.fleetnews.co.uk/news/charge-point-enforcement-concerns-raised-over-ev-uptime-rules)
- DfT's July 2024 request for information said: "we do not see a need for DfT to build a data platform to serve open data to consumers" (https://www.contractsfinder.service.gov.uk/Notice/9b22d88e-38ba-4055-8e0e-84c58a196aa0). [service](https://www.contractsfinder.service.gov.uk/Notice/9b22d88e-38ba-4055-8e0e-84c58a196aa0)
- The Transport Committee inquiry "Supercharging the EV transition" closed to evidence on 30 January 2026. It took oral evidence on 4 March, 25 March and 29 April 2026, the last session with minister Keir Mather MP and Richard Bruce of OZEV (https://committees.parliament.uk/work/9523/supercharging-the-ev-transition/). [parliament](https://committees.parliament.uk/work/9523/supercharging-the-ev-transition/) Whether a report has been published was **not checked**. In earlier Public Accounts Committee evidence, Richard Bruce said "There will be third-party providers scraping this data off chargepoint companies" (https://committees.parliament.uk/oralevidence/15242/html/). [parliament](https://committees.parliament.uk/oralevidence/15242/html/)
- The OPSS enforcement policy (dated 26 January 2026) lists the PCPR under compliance notices and enforcement undertakings (https://www.gov.uk/government/publications/safety-and-standards-enforcement-enforcement-policy/opss-enforcement-policy). [www](https://www.gov.uk/government/publications/safety-and-standards-enforcement-enforcement-policy/opss-enforcement-policy)

Suggested wording: "As of [date], OPSS's published enforcement lists for [periods checked] contain no entries under the Public Charge Point Regulations 2023."

### Defamation basics (general information, not legal advice; not re-checked against the Act)

- The Defamation Act 2013 requires **serious harm** to reputation, and for a business that trades for profit, **serious financial loss**.
- The main defences are **truth**, **honest opinion** and **publication on a matter of public interest**.
- Under the *Derbyshire* principle, government bodies cannot sue for defamation, but **individual officials can**. Never name individual civil servants.
- Practical rules:
  - Use dated, evidenced facts and neutral labels, e.g. "does not publish an anonymous feed as of 6 October 2026" rather than "is breaking the law".
  - Offer a right of reply and publish replies.
  - Keep a corrections log and fix errors within 48 hours.
  - Label opinions clearly and keep them separate from the facts.

---

## 4. Reducing reliance on OSM

| Rank | Source | Default confidence | Licence |
|---|---|---|---|
| 1 | Operator PCPR feed | High | OGL-in-line basis (PCPR) |
| 2 | Operator website, static file or FOI | Medium-high | Recorded per source |
| 3 | Open Charge Map | Medium | User-contributed data under CC BY 4.0; imported data "copyright the original Data Provider" (openchargemap.org/about/terms) |
| 4 | OpenStreetMap | Medium | ODbL |
| 5 | User report | Low until confirmed | CC BY 4.0, with consent |

Every record carries `source_id`, `source_url`, `licence`, `fetched_at`, `last_confirmed_at`, `method` and `confidence`.

**Matching:**
1. Match on the exact eMI3 `evse_id` (e.g. `GB*XXX*E...`). OCPI's `evse_id` is "Compliant with the specification for EVSE ID from 'eMI3 standard version V1.0'" (DfT guidance, table 10). [www](https://www.gov.uk/government/publications/the-public-charge-point-regulations-2023-guidance/public-charge-point-regulations-2023-guidance)
2. Match on OSM `ref`/`source:ref` tags. The OSM wiki suggests `source:ref` text for Gridserve IDs (https://wiki.openstreetmap.org/wiki/EV_charge_points_in_the_United_Kingdom). [openstreetmap](https://wiki.openstreetmap.org/wiki/EV_charge_points_in_the_United_Kingdom)
3. Otherwise match on the same operator within roughly 50 m (a starting heuristic, not a standard). Flag anything else for review.
4. Never overwrite operator data with gap-filler data.

**Auto-discovery:**
- **No authoritative public list of UK operators with OCPI party IDs or eMI3 IDs was found**, and it is **not verified** who issues GB operator IDs.
- Operators must notify the Secretary of State of their roaming providers (reg 6(2) and (3)), [instavolt](https://instavolt.co.uk/public-charge-point-regulation-data/) and DfT's contractor ingests the feeds for government use. [legislation](https://legislation.gov.uk/uksi/2023/1168/made) [service](https://www.contractsfinder.service.gov.uk/Notice/Attachment/3f6da4fd-2533-4289-a49e-ebad9a25c086) Both are FOI targets.
- Once a base URL is known, version endpoints can be probed (`GET {base}/versions`, e.g. Pod's `https://ocpi.podenergy.com/ocpi/cpo/versions`). Base URLs cannot be discovered without a directory.
- **EU model:** under AFIR, operators feed 27 National Access Points (https://www.eco-movement.com/bringing-your-charging-network-online-the-ampeco-eco-movement-benefit/). [eco-movement](https://www.eco-movement.com/bringing-your-charging-network-online-the-ampeco-eco-movement-benefit/) ocpdb both imports from and publishes to Germany's Mobilithek. [github](https://github.com/mobidata-bw/ocpdb) No UK equivalent has been announced as far as this research found. The Dutch, French and Norwegian models were **not checked**.
- Practical approach: a monthly workflow that probes candidate base URLs in the registry, plus a watchlist built from the OSM wiki.

---

## 5. Login or no login

**Recommendation: no login in Phase 1.**

| Need | Phase 1 | Defer |
|---|---|---|
| Preferences, favourites, home location | `localStorage` plus URL parameters (`?free=1&connector=ccs&minkw=50`) | Accounts, sync |
| Add or disable an operator; record engagement | Pull request editing YAML and evidence | Git-based CMS |
| Refresh | Workflow dispatch button | |
| Fix wrong data | `/overrides/*.yaml` with reason and evidence | |
| User reports | GitHub issue forms; links to edit OSM or Open Charge Map | Moderated form via Worker; GitHub OAuth; Cloudflare Access |

**Privacy:** with no accounts and no analytics, the site itself processes almost no personal data. GitHub and Cloudflare still see visitors' IP addresses, so say so in a short privacy notice. Under PECR, using `localStorage` counts as storing information on the user's device, just like cookies. Storage that is strictly necessary for a feature the user asked for (such as saved filters) is generally exempt from consent; analytics is not (**medium confidence, not legal advice**).

**User options:**
- free (confirmed only);
- maximum price per kWh;
- "price unknown";
- connector type;
- power;
- network;
- live availability (Phase 3);
- data source and confidence;
- access restrictions;
- units shown as p/kWh including VAT;
- home location;
- favourites.

**Admin options:**
- add or disable an operator;
- record engagement and evidence;
- trigger a refresh;
- review reports;
- apply overrides;
- publish corrections;
- rotate secrets.

---

## 6. Dataset and code licensing (general information, not legal advice)

- DfT guidance: "Data must be open in line with the Open Government Licence." [www](https://www.gov.uk/government/publications/the-public-charge-point-regulations-2023-guidance/public-charge-point-regulations-2023-guidance)
- OGL v3.0 requires you to "acknowledge the source of the Information in your product or application by including or linking to any attribution statement specified by the Information Provider(s) and, where possible, provide a link to this licence". The default wording is "Contains public sector information licensed under the Open Government Licence v3.0." Where listing every attribution is impractical, you "may include a URI or hyperlink to a resource that contains the required attribution statements" (https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). [city](https://openaccess.city.ac.uk/id/eprint/20764/7/Open%20Government%20Licence.pdf) [nationalarchives](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/)
- **Uncertainty:** the OGL is written for public sector information, [nationalarchives](https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/) and most operators are private companies. "In line with" probably means "on equivalent terms". Suggested wording: "Contains charge point data published by [Operator] under the Public Charge Point Regulations 2023, re-used in line with the Open Government Licence v3.0. Source: [feed URL], retrieved [date]."
- **ODbL (general understanding, not re-verified):** keep OSM-derived records in their own file and map layer, credited "© OpenStreetMap contributors". Kept separate, they form a collective database. If you use OSM to fix operator records, the merged result becomes a derivative database that must be shared under ODbL. Map images are produced works and need only attribution.
- **Open Charge Map:** its terms say user-contributed data "is licensed under a Creative Commons Attribution 4.0 International (CC BY 4.0)", but "Data imported from 3rd party Data Providers is copyright the original Data Provider in each case", and apps must show "the appropriate Data Provider attribution (including license terms)" visibly to the end user (openchargemap.org/about/terms). Give it a separate layer and store the licence per record and per data provider.
- **Code:** Apache-2.0 (permissive, with a patent grant) or MIT. If you reuse ocpdb code you must use AGPL-3.0, which means publishing your source if you run a modified version as a network service.
- **Published data:**

| File | Licence |
|---|---|
| `operators-combined.geojson` | OGL v3.0, with per-operator attribution |
| `osm.geojson` | ODbL |
| `ocm.geojson` | Open Charge Map's terms |
| `reports.geojson` | CC BY 4.0 |

- **`DATA_LICENCES.md`:**
  - per-source table (feed URL, licence, attribution, retrieval date, access terms);
  - how the data layers are kept separate;
  - corrections contact;
  - "check at the charger" disclaimer.

---

## 7. FOI programme (later phase)

| # | Body | Ask |
|---|---|---|
| 1 | Department for Business and Trade (OPSS) | "Since 24 November 2023, how many complaints, information notices, compliance notices, civil penalties and enforcement undertakings have there been under the Public Charge Point Regulations 2023, by regulation? How many concern regulation 10? How many staff (FTE) work on PCPR enforcement?" |
| 2 | DfT (OZEV) | "Please provide the list of operators and open data endpoint URLs from which DfT or its open data contractor collects PCPR data, and any data quality reports." |
| 3 | DfT | "Please provide the contract, statement of work and deliverables for the EV open data aggregation contract that followed the July 2024 request for information." |
| 4 | DfT | "Please list the operators that have notified roaming providers under regulation 6(2) or 6(3)." This is close to a full list of non-micro operators. |
| 5 | DfT | "Please provide summary results of the 2025 reliability reports under regulation 8." |
| 6 | DfT | "Please provide the final National Chargepoint Registry dataset and the records explaining why there is no public replacement." |
| 7 | Local councils, combined transport authorities and NHS trusts | "Please list each EV charger you own or host: location, operator, power, tariff (including free units) and access restrictions." |

**Existing requests:** there is a WhatDoTheyKnow series to English councils about PCPR compliance; for example, Halton Borough Council's response is marked successful (https://www.whatdotheyknow.com/request/private_public_charge_point_stat_68). [whatdotheyknow](https://www.whatdotheyknow.com/request/private_public_charge_point_stat_68) Other topics were not checked, so search WhatDoTheyKnow before filing.

**EIR and RPSI (general, not re-verified):** charger location data may count as environmental information under the EIR 2004, which presume disclosure and have no fixed cost limit. Expect the commercial confidentiality exception for Zapmap's product. The RPSI Regulations 2015 do not cover material owned by third parties, so they are a weak route.

**Tips:** the usual deadline is 20 working days. Keep requests narrow to stay under the cost limit. If refused, ask for an internal review, then complain to the ICO. File through WhatDoTheyKnow so the answers are public.

---

## 8. Sub-8kW and chargers outside the duty

### Exact position (high confidence)

- **Who it applies to:** reg 4 says "Regulations 5 to 10 apply to a charge point operator that is not a micro business" and "Regulation 11 applies to all charge point operators". [legislation](https://legislation.gov.uk/uksi/2023/1168/made)
- **No power threshold in reg 10.** The 8kW threshold appears only in reg 5 (contactless: "a new public charge point with a power of 8 kilowatts or above"). The 50kW threshold defines "rapid charge point", which matters for contactless on existing units and for reliability (regs 5(2) and 7). [legislation](https://legislation.gov.uk/uksi/2023/1168/made)
- **What counts as public (reg 3, formatting simplified):** a "public charge point" is one "intended for use primarily by members of the general public". This includes points accessible only "during specific hours" or "situated in a public car park, whether or not that car park is available only to persons intending to purchase specific goods or services". It excludes workplace charge points and points "restricted for the exclusive use by" a specific manufacturer's vehicles, "a person engaged in a specific occupation", or "an occupier of, or visitor to, residential premises". [legislation](https://legislation.gov.uk/uksi/2023/1168/made)
- **Free and simple chargers (guidance):** coverage "includes public charge points which provide electricity free of charge". Also: "For any public charge point that is not technically capable of transmitting data and is akin to a 3-pin plug, the charge point operator must make public only the reference data." [www](https://www.gov.uk/government/publications/the-public-charge-point-regulations-2023-guidance/public-charge-point-regulations-2023-guidance) [www](https://www.gov.uk/government/publications/the-public-charge-point-regulations-2023-guidance/public-charge-point-regulations-2023-guidance)
- **So any statement that the rules only apply at "8kW and above" is wrong** as far as open data goes.

**Chargers at hospitals, leisure centres and similar sites:** if the public can use a charger, it is in scope. For a free tariff, OCPI says `tariff_ids` "should be set and point to a defined 'free of charge' tariff" (DfT guidance, table 11). [www](https://www.gov.uk/government/publications/the-public-charge-point-regulations-2023-guidance/public-charge-point-regulations-2023-guidance) A free unit showing no price is therefore a data-quality gap worth logging. If the bays are staff-only, they are probably workplace chargers and out of scope.

| Not in regulated feeds | Best source |
|---|---|
| Micro-business operators | Open Charge Map, OSM, user reports |
| Workplace and staff-only (e.g. staff bays at offices, hospitals or depots) | FOI to the site owner; label "restricted" |
| Residential and driveway peer-to-peer (the guidance lists "charge points located on a private driveway which are made available for peer-to-peer charging" as not public) [www](https://www.gov.uk/government/publications/the-public-charge-point-regulations-2023-guidance/public-charge-point-regulations-2023-guidance) | Platform sites where their terms allow |
| Manufacturer-exclusive | Operator website; OSM |
| Occupation-only (taxi, emergency services) | Council FOI; label "restricted" |
| Gated but in scope | Interim OCM or OSM, clearly badged |

Public hotel, pub and supermarket chargers **are in scope**; the guidance lists "supermarket and hotel car parks". [www](https://www.gov.uk/government/publications/the-public-charge-point-regulations-2023-guidance/public-charge-point-regulations-2023-guidance)

**Display:**
- Operator data: solid markers.
- Gap-fillers: hollow markers with a badge ("OSM", "Open Charge Map", "User report: unverified") and "last confirmed [date]".
- Never show a price or "free" on a gap-filler unless the source states it.

**Reports without login:** use a GitHub issue form (location, operator, connector, price seen, consent tick) with labels as the moderation queue. Add "fix this on OSM / Open Charge Map" links next to it.

---

## 9. Repository structure and Claude Code

```
/operators/            one YAML per operator + schema
/adapters/             ocpi_221, eco_movement_pcpr, gridserve, static_file, custom/
/pipeline/             fetch, normalise, tariffs, merge, publish, runlog
/schema/               Pydantic models; exported JSON Schema
/overrides/  /evidence/<operator>/  /status/  /site/  /proxy/ (Phase 3)
/tests/fixtures/<op>/  recorded sample responses
/docs/adr/             decisions; ROADMAP.md; CHANGELOG.md; DATA_LICENCES.md; CORRECTIONS.md
/.claude/              settings.json, skills/, agents/
/.github/workflows/    ci, fetch-daily, status-snapshot, deploy, keepalive
```

**Schema:**
- **Location:** id `{source}:{country}:{party}:{location_id}`, name, address, coordinates, operator, access (`public | customers | restricted | unknown`), opening hours, EVSEs and provenance.
- **EVSE:** status and `status_at`.
- **Connector:** standard, `max_kw` and `tariff_ids`.
- **Tariff:** carries a derived `price_state` = `priced | free_confirmed | unknown`.
- **Price rule:** `free_confirmed` only when a referenced tariff exists and every component is zero. The guidance says prices are "excl. VAT" and that "Not providing a VAT is different from 0% VAT", [www](https://www.gov.uk/government/publications/the-public-charge-point-regulations-2023-guidance/public-charge-point-regulations-2023-guidance) so show "VAT not stated" where VAT is missing.

**Quality:**
- pytest with recorded fixtures;
- ruff;
- Pydantic validation and a JSON Schema check on outputs;
- Dependabot;
- branch protection on `main`.

**Claude Code (official docs; features change quickly, so re-check before setup):**
- **Building blocks:**
  - **CLAUDE.md** loads at every session start, so keep it short. [claude](https://code.claude.com/docs/en/features-overview)
  - **Skills** (`.claude/skills/<name>/SKILL.md`) hold longer procedures and are invoked with `/name` or automatically. `commands/*.md` work through the "same mechanism as skills". [claude](https://code.claude.com/docs/en/claude-directory)
  - **Subagents** live in `agents/*.md`. [claude](https://code.claude.com/docs/en/claude-directory)
  - **Hooks** run outside the model on tool events, so use them to enforce hard rules. [claude](https://code.claude.com/docs/en/features-overview)
  - **Settings** live in `settings.json`. [claude](https://code.claude.com/docs/en/claude-directory)
  - Sources: https://code.claude.com/docs/en/claude-directory, https://code.claude.com/docs/en/features-overview, https://code.claude.com/docs/en/hooks.
- **Cloud sessions:** available at claude.ai/code, in the mobile app's Code tab, or via `claude --cloud`. They are "available on Pro, Max, and Team plans" and need GitHub connected. The Claude GitHub App enables Auto-fix on pull requests, and `/schedule` sets up recurring tasks (https://code.claude.com/docs/en/claude-code-on-the-web, https://code.claude.com/docs/en/web-quickstart). [claude +2](https://code.claude.com/docs/en/claude-code-on-the-web) Cloud environments support network access levels, setup scripts and, on Pro and Max, stored API credentials (https://code.claude.com/docs/en/cloud-environments). [claude](https://code.claude.com/docs/en/cloud-environments)
- **GitHub Action:** `anthropics/claude-code-action@v1`, installed via `/install-github-app`, responds to `@claude` in issues and pull requests. Pro and Max users can authenticate with `CLAUDE_CODE_OAUTH_TOKEN` from `claude setup-token` (https://code.claude.com/docs/en/github-actions). [claude +2](https://code.claude.com/docs/en/github-actions)
- **Limits and costs:** sessions share your plan's usage limits. [wmedia](https://wmedia.es/en/tips/claude-code-cloud-sessions-from-browser) Exact Pro and Max allowances were **not verified**.

**Solo process:**
1. One issue per task, with acceptance criteria.
2. Claude works on a branch and opens a small pull request.
3. You review CI and the preview, then merge.
4. Deploy only from protected `main`.
5. A hook blocks edits to `.env*`/`*secret*` files and stops force pushes.
6. Record decisions as ADRs.

**GitHub limits (official docs):** published Pages sites "may be no larger than 1 GB", have "a soft bandwidth limit of 100 GB per month", and deployments "timeout if they take longer than 10 minutes" (https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits). [github](https://docs.github.com/en/pages/getting-started-with-github-pages/github-pages-limits) Also: "In a public repository, scheduled workflows are automatically disabled when no repository activity has occurred in 60 days" (https://docs.github.com/actions/managing-workflow-runs/disabling-and-enabling-a-workflow), [github](https://docs.github.com/actions/managing-workflow-runs/disabling-and-enabling-a-workflow) so add a keepalive workflow. GitHub Docs say "Use of the standard GitHub-hosted runners is free and unlimited on public repositories" (docs.github.com/en/actions/reference/runners/github-hosted-runners); larger runners are always charged. Move to Cloudflare Pages or R2 if you approach either limit.

**Front end:**
- MapLibre GL JS with a clustered GeoJSON layer. 50,000 slim points should come to a few MB gzipped (**an estimate; measure it**). Load details per location on click. Switch to PMTiles only if the initial payload goes over about 5 MB.
- Basemap: OpenFreeMap or a self-hosted Protomaps extract. Their terms, and those of MapTiler and OS Maps API, were **not verified**.
- Accessibility: add a list view, keyboard navigation, text labels as well as colour, and WCAG AA contrast.

---

## 10. Phased roadmap (effort estimates are rough)

| Phase | Scope | Done when | Effort | Main risks |
|---|---|---|---|---|
| 1 | Registry, three open adapters (char.gy, Jolt, GeniePoint), tariffs, static map, feed-health page, licences page | Live on github.io; daily refresh green for 14 days; "free" only when confirmed | 3 to 6 weekends | Feed quirks; tariff complexity |
| 2 | Access requests and engagement log; add adapters as keys arrive | Every known operator has a dated status; at least 3 gated feeds live | 1 to 2 hours a week | No replies; restrictive agreements |
| 3 | Worker for live status and price; snapshot mode | Clicking shows live status with a timestamp; within the free tier for 30 days | 2 to 4 weekends | CPU limit; rate limits |
| 4 | OCM and OSM layers, reports, overrides, sub-8kW and exempt chargers | Badged layers; working moderation queue | 2 to 4 weekends | Licence mixing; duplicates |
| 5 | Accountability page, FOIs, corrections policy | Dated government page; at least 5 FOIs filed | Ongoing | Wording slipping into defamation risk |

**Name ideas (not checked for clashes; check Companies House, UKIPO, domains, GitHub and app stores):** PlugLedger, Open Socket Map, ChargeCensus UK, KerbLog, TruePlug Map. Avoid anything close to Zapmap, ChargeFinder, PlugShare, Electroverse, Open Charge Map, WattsUp, Bonnet or Chargemap.

---

## Claude Code kickoff brief (paste into a new session)

```markdown
# Project kickoff: open UK EV charger map

## Goal
A free public map of UK public EV chargers built from operator open data published under the Public
Charge Point Regulations 2023 (SI 2023/1168, reg 10, OCPI 2.2.1), with tariffs, a data-health status page
and an operator engagement log. Owner: a hobbyist, not a professional developer.

## Principles (non-negotiable)
1. Operator feeds first. OSM, Open Charge Map and user reports only fill gaps, in separate layers.
2. Provenance on every record: source_id, source_url, licence, fetched_at, last_confirmed_at, confidence.
3. Never show "Free" unless a referenced operator tariff exists and every price component is zero.
   Missing or unresolvable tariff = "Price unknown". Missing VAT = "VAT not stated".
4. No secrets in the repo. Keys live in GitHub Actions secrets (later Cloudflare Worker secrets),
   referenced by name in operator YAML.
5. No personal data: no accounts, no analytics, no names or personal emails in evidence files.
6. Status pages: factual, dated, neutral wording with linked evidence. No accusations of law breaking.
7. British English. No em dashes anywhere.
8. Accuracy over guessing. Write "unknown" or "needs testing" and open an issue.
9. Tests use recorded fixtures; never hit live feeds in unit tests.
10. Small pull requests; main is protected; every change has an issue.

## Architecture
- Python 3.12 pipeline (uv, Pydantic v2, httpx, pytest, ruff) on GitHub Actions.
- /operators/*.yaml -> adapters (ocpi_221, eco_movement_pcpr, gridserve, static_file, custom)
  -> normalise -> tariffs (price_state) -> merge -> publish static files.
- Outputs: site/data/locations.geojson (slim), site/data/loc/<shard>/<id>.json, site/data/status/*.json,
  site/status/index.html, manifest.json with fetched_at per operator.
- Front end: static MapLibre GL JS in /site on GitHub Pages.
- Phase 3 only: Cloudflare Worker in /proxy for cached live status.

## First ten tasks
1. Scaffold: Apache-2.0 LICENSE, README, CLAUDE.md, .gitignore (.env*, *.key, raw/), uv, ruff, pytest,
   pre-commit secret scanner, ci.yml. Accept: CI green; pre-commit blocks a fake key.
2. Schema: Pydantic models (Location, EVSE, Connector, Tariff, Provenance); export JSON Schema.
   Accept: round-trip tests; CI checks the schema is up to date.
3. Registry: YAML schema, validator, seed files for every operator in the blueprint (open, gated and
   not located), engagement status only where no feed. Accept: `uv run python -m pipeline.registry --validate` passes.
4. ocpi_221 adapter: pagination, date_from, polite delays, retries. Record trimmed char.gy fixtures.
   Accept: fixture tests pass; `--live chargy --max-pages 1` works.
5. Jolt custom adapter (published apiKey with source link) and static_file adapter for GeniePoint.
   Accept: fixture tests pass.
6. Tariff module: resolve tariff_ids, compute price_state and indicative p/kWh inc. VAT.
   Accept: tests for free_confirmed, missing tariff, unresolvable id, time-based tariff.
7. Merge and publish slim GeoJSON, sharded detail JSON, manifest. Accept: outputs validate; size logged.
8. Run log and status page (health metrics plus separate engagement table linked to /evidence).
   Accept: renders from fixtures with neutral labels.
9. Front end: map, clustering, filters, detail panel with provenance and timestamps, URL state,
   localStorage, list view. Accept: usable on a mid-range phone; Lighthouse accessibility >= 90.
10. Workflows: fetch-daily (cron + dispatch), deploy (Pages from main), keepalive; DATA_LICENCES.md;
    privacy notice. Accept: 3 consecutive green scheduled runs; site live.

## Test commands
uv run ruff check . && uv run ruff format --check .
uv run pytest -q
uv run python -m pipeline.run --fixtures
uv run python -m pipeline.run --live chargy --max-pages 1
```

### Draft CLAUDE.md

```markdown
# CLAUDE.md

## What this is
Open map of UK public EV chargers from operator open data (Public Charge Point Regulations 2023,
reg 10, OCPI 2.2.1). Static site on GitHub Pages; Python pipeline on GitHub Actions.

## Commands
- Lint: uv run ruff check . && uv run ruff format --check .
- Test: uv run pytest -q
- Offline pipeline: uv run python -m pipeline.run --fixtures
- Validate registry: uv run python -m pipeline.registry --validate

## Hard rules
- Never commit or print secrets. Reference keys by secret_name only.
- Never call live feeds in tests. Use tests/fixtures.
- Never label a charger "Free" unless price_state == free_confirmed.
- Never overwrite operator data with OSM, Open Charge Map or user reports.
- Status wording: neutral, dated, evidenced. No claims that anyone broke the law.
- British English. No em dashes. Write "unknown" or "needs testing" rather than guessing.
- One issue per change; small PRs; never push to main.

## Adding an operator
Use /add-operator: copy operators/_template.yaml, pick an adapter, set secret_name, record a trimmed
fixture, add tests, add attribution to DATA_LICENCES.md, add an evidence entry.
```

### Template access-request email

```text
Subject: Request for access to your open charge point data (Public Charge Point Regulations 2023)

Hello,

I'm a volunteer building a free, non-commercial map of UK public EV chargers,
using prices and availability from operators' own data. It's open source and I credit every operator.

Regulation 10(5) of the Public Charge Point Regulations 2023 asks operators to make reference and
availability data "available to the public free of charge and in a machine readable format without
any requirement to agree to terms and conditions regarding the use of that data". DfT's guidance adds
that the data should be open in line with the Open Government Licence, and that terms covering the
means of access to an API are fine.

Could you let me know the endpoint for your OCPI 2.2.1 locations and tariffs data, and how I can get
access? I'm happy to keep any key private, stick to your rate limits and fetch reference data no more
than once a day.

Could you also confirm I can show the data publicly on the map with attribution to you? If there are
any conditions, please let me know so I can describe your access route accurately.

Thank you very much for your help.

Best wishes,
[project name]
[project URL]
```

---

## Caveats: what could not be verified

- **Eco-Movement:** the user guide was not read. Still unconfirmed: the exact locations URL, how keys are issued, whether one token covers several operators, its terms, and its own list of UK operators.
- **Untested:** CORS and single-location fetching for char.gy, Jolt, GeniePoint and Go Zero.
- **OCPI:** the single-object GET is stated from general knowledge of the spec; confirm against the PDF.
- **Free tiers:** only Cloudflare's were checked; its KV write limit of 1,000 a day comes from Cloudflare's blog (blog.cloudflare.com/workers-kv-free-tier), as quoted in a search result.
- **OPSS:** only the October 2025 to March 2026 enforcement list was read. The earlier lists and the undertakings page were not.
- **Transport Committee:** whether a report is out is unknown. No 2026 consultation, CMA follow-up, or statements from Which?, the AA or FairCharge on PCPR open data were found.
- **From earlier research, not re-verified:** Gridserve's terms and the earlier feed list.
- **Charger totals:** Parliament cited DfT's 88,513 public charging devices at 1 February 2026. Zapmap's Q3 2026 statistics, reported by EV Fleet World on 6 October 2026, give 124,738 public EV chargers at 48,298 locations at the end of September 2026, up 9% year on year. Zapmap's statistics page (zapmap.com/ev-stats/how-many-charging-points) explains the difference: "For 2026, the metric used to track the size of the public charging network has changed from devices to EV chargers". It gave 121,171 chargers on 94,595 devices at 46,731 locations at 30 June 2026. These figures come from search snippets; the articles themselves could not be read.
- **Legal points:** defamation, ODbL, PECR, FOI/EIR and RPSI are general understanding, not re-checked against primary sources, and are not legal advice.
- **Not found:** an authoritative UK list of operators with OCPI or eMI3 IDs, or who issues GB eMI3 IDs.
- **Not checked:** basemap terms, maintained OCPI libraries, and name clashes.
- **Claude Code:** features and plan limits change often; exact Pro and Max allowances were not verified.
