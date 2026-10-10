# Data licences and sources

General information, not legal advice. Last reviewed 9 October 2026.

## The short version

- This project's **code** is licensed under Apache-2.0 (see [LICENSE](LICENSE)). That
  licence covers only the code written for this project. **It does not cover any data.**
- **Data keeps its own licence.** Each source's data is used under that source's terms. It
  is never relicensed, never put under Apache-2.0 and never presented as this project's
  own work.
- Every record carries its source URL, licence and the time it was fetched. Every source
  is listed below with its attribution.

## Operator data: the legal basis

- **Public Charge Point Regulations 2023, regulation 10(5):** operators must make reference
  and availability data "available to the public free of charge and in a machine readable
  format without any requirement to agree to terms and conditions regarding the use of
  that data".
  https://www.legislation.gov.uk/uksi/2023/1168/regulation/10/made
- **DfT guidance (updated 21 October 2024):** "Data must be open in line with the Open
  Government Licence." It adds that "terms and conditions covering the means of access to
  the data and API(s) are permissible".
  https://www.gov.uk/government/publications/the-public-charge-point-regulations-2023-guidance/public-charge-point-regulations-2023-guidance
- So operator data is used in line with the Open Government Licence v3.0 (OGL), and each
  operator's terms for access (such as rate limits and keeping keys private) are followed.
- The OGL was written for public sector information and most operators are private
  companies. "In line with" is read here as "on the same terms as". That reading is an
  interpretation, not settled law.

## What the OGL v3.0 asks of us

From the licence text (https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/),
read 7 October 2026:

1. **Acknowledge the source** with the provider's attribution statement and, where
   possible, a link to the licence. With many providers, a link to a page listing all the
   attribution statements is allowed.
2. **No suggestion of endorsement.** The licence gives no right to suggest "any official
   status" or that a provider endorses this project or its use of the data.
3. **Things the OGL does not cover:** personal data, third-party rights the provider
   cannot license, and trade marks, logos and other intellectual property.
4. **No warranty from the provider.** The data is supplied "as is".

## How this project meets those terms

| Requirement | What the project does |
|---|---|
| Attribution | Each operator's statement is in its registry file (`operators/<id>.yaml`) and listed below. The map page shows every statement under "Data sources and credits", repeats the operator's statement and licence link in each charger's details, and links to this page. |
| Provenance | Every record stores its source URL, licence, fetch time and method. |
| No endorsement | Neutral wording only. [DISCLAIMER.md](DISCLAIMER.md) says the project is not affiliated with or endorsed by any operator or public body. |
| No logos or trade marks | Operator logos and brand marks are never used. Names are used only to say where data comes from. |
| Publish flag | OCPI 2.2.1 says a location with `publish` set to false may not be published on a website or app. Those locations are never kept. Locations with no publish flag are not kept either, unless the operator file records the repository owner's decision, with its reason and evidence, in `missing_publish_flag` (Jolt, decided 8 October 2026, because Jolt publishes the feed itself as open data under the regulations). The transparency page shows each decision. |
| Access terms | Rate limits are set in each registry file and keys are kept as secrets. An operator is only switched on once its own pages have been read and its terms recorded (`licence.checked`). |
| Faithful data | Data is converted between formats but not "corrected". Values that are not valid are recorded as unknown and logged. Operator data is never overwritten with data from other sources. |
| No personal data | Operator feeds hold charger data, not personal data. Evidence files must not contain names or personal email addresses. |

## Sources

| Source | Data | Licence | Attribution | Terms checked | Used for |
|---|---|---|---|---|---|
| char.gy | https://char.gy/open-ocpi/locations and https://char.gy/open-ocpi/tariffs | OGL v3.0, on the PCPR basis above | Contains data from char.gy published under the Public Charge Point Regulations 2023, used in line with the Open Government Licence v3.0. | 7 October 2026: char.gy's open data page states no other licence or terms | Test fixtures in `tests/fixtures/chargy/`. Published on the live map, https://mcrdavid.github.io/OEVM/, since 8 October 2026 (fetched with 4 seconds between requests since 9 October 2026, 6 seconds before; see `operators/chargy.yaml`). |
| Jolt | https://api.joltcharge.com/v1/uk/public/locations and https://api.joltcharge.com/v1/uk/public/tariffs/{tariffId} | OGL v3.0, on the PCPR basis above | Contains data from Jolt published under the Public Charge Point Regulations 2023, used in line with the Open Government Licence v3.0. | 7 October 2026: Jolt's help page, read in a browser because it returns a browser check to automated requests, states no licence, terms or rate limits. 8 October 2026: the same article, read through the help centre's article data, says the same | Test fixtures in `tests/fixtures/jolt/`. Published on the live map, https://mcrdavid.github.io/OEVM/, since 8 October 2026. |
| GeniePoint | https://opendata.geniepoint.co.uk/locations and https://opendata.geniepoint.co.uk/tariffs | OGL v3.0, on the PCPR basis above | Contains data from GeniePoint published under the Public Charge Point Regulations 2023, used in line with the Open Government Licence v3.0. | 8 October 2026: GeniePoint's open data page, read in a browser because it returns a browser check to automated requests, states no licence or terms for the data. The Equans website's general terms of use, read the same day, restrict reproducing material on its sites without permission; the repository owner decided to read them as not covering the open data files, which regulation 10(5) requires to be available without terms on their use (see `operators/geniepoint.yaml`) | Test fixtures in `tests/fixtures/geniepoint/`. Switched on for the daily run. Its files refused requests from GitHub's servers in the first run on 8 October 2026, so the owner decided the same day to fetch them through the project's relay on Cloudflare Workers (ADR 0010); the first run through the relay, the same evening, fetched both files. The data is passed on unchanged and keeps this licence and attribution. |
| Clenergy EV | https://api.clenergy.online/development/pcpr/locations and https://api.clenergy.online/development/pcpr/tariffs | OGL v3.0, on the PCPR basis above | Contains data from Clenergy EV published under the Public Charge Point Regulations 2023, used in line with the Open Government Licence v3.0. | 9 October 2026: Clenergy EV's open data page, https://www.clenergy-ev.com/open-data/, says the files are there "to meet UK Government Public Charge Point Regulations" and states no licence, terms or rate limit; the site links no terms of use | Test fixtures in `tests/fixtures/clenergy_ev/`. Switched on for the daily run once this row is merged. The data is passed on unchanged and keeps this licence and attribution. |
| MFG EV Power | https://opendata.motorfuelgroup.net/locations and https://opendata.motorfuelgroup.net/tariffs | OGL v3.0, on the PCPR basis above | Contains data from MFG EV Power published under the Public Charge Point Regulations 2023, used in line with the Open Government Licence v3.0. | 9 October 2026: MFG's EV Power page links both files under its open data FAQ and states no licence, terms or rate limit for the data | Test fixtures in `tests/fixtures/mfg_ev_power/`. Switched on for the daily run from 9 October 2026 (see `operators/mfg_ev_power.yaml`). |
| Mer UK | https://uk.mer.eco/wp-json/ozev/v1/data (locations and tariffs in one response) | OGL v3.0, on the PCPR basis above | Contains data from Mer UK published under the Public Charge Point Regulations 2023, used in line with the Open Government Licence v3.0. | 10 October 2026: Mer's "Live Charge Point Data" page, https://uk.mer.eco/live-charge-point-data/, says "As per OZEV regulations, we have hosted our location and tariff data in a machine-readable format" and states no licence, terms or rate limit for the data. Mer's terms and conditions, read the same day, grant "a revocable right to use the Content for your personal (non-commercial) use", where Content includes material and data on its website; the repository owner decided the same day to read them as not covering the open data, which regulation 10(5) requires to be available without terms on its use (see `operators/mer_uk.yaml`) | Test fixtures in `tests/fixtures/mer_uk/`. Switched on for the daily run once this row is merged. The data is passed on unchanged and keeps this licence and attribution. |

The other operators in `operators/` have no data in this project yet. Each gets a row here
when its terms have been checked and it is switched on.

Gridserve's API Fair Use Policy was read on 8 October 2026. It says intellectual property
in the API Data remains Gridserve's and describes the data as confidential and
proprietary. On 9 October 2026 the repository owner decided that regulation 10(5), which
requires the data to be available without terms on its use, takes priority over those
terms, so the data will be used in line with the Open Government Licence. It stays
switched off, with no row above, until a key is granted and its adapter is built (see
`operators/gridserve.yaml`).

## Planned layers, kept separate

These are planned in the blueprint. Each source's terms must be read and recorded here
before its layer is built.

| File | Source | Licence |
|---|---|---|
| `locations.geojson` (operator layer, built by `pipeline/publish.py`) | Operator feeds | OGL v3.0, with each operator's attribution in the file, in every detail file and in `manifest.json` |
| `osm.geojson` | OpenStreetMap | ODbL. Kept as a separate layer so it is not merged into operator data. |
| `ocm.geojson` | Open Charge Map | Open Charge Map's terms, recorded per record and per data provider |
| `reports.geojson` | User reports | CC BY 4.0, with the reporter's consent |

## The background map and software served with the site

The map page (blueprint task 9, ADR 0008) shows a background map from an outside service
and serves one open source library from the site itself. Neither is project data or
project code, and neither is relicensed.

| Item | Source | Licence | Credit shown |
|---|---|---|---|
| Background map files (vector tiles) | OpenFreeMap, `https://tiles.openfreemap.org/styles/liberty` | Map data from OpenStreetMap under the ODbL; tiles built to the OpenMapTiles schema. Used under OpenFreeMap's terms, read 8 October 2026 | MapLibre's attribution control, always expanded, shows the style's credit ("OpenFreeMap © OpenMapTiles Data from OpenStreetMap", linking to openstreetmap.org/copyright). The page footer repeats it. Text only, no logos |
| MapLibre GL JS (the version pinned in `package.json`) | npm package `maplibre-gl`, copied into the build by `pipeline/build_site.py` | BSD-3-Clause (its `LICENSE.txt`, published at `vendor/maplibre-gl/LICENSE.txt`) | Footer link to the licence, and `vendor/maplibre-gl/THIRD_PARTY_NOTICES.txt` with the licence of each package it bundles |

OpenFreeMap's terms forbid automated collection without permission, so tests and CI use
a plain local style (`--offline-style`) and never contact it. The operator data on the
map keeps its own licence and attribution, listed in the page's "Data sources and
credits" and in every detail file.

## Country outlines used to decide what is in the UK

| Item | Source | Licence | Credit |
|---|---|---|---|
| Land outlines of the UK and its neighbours (`pipeline/data/uk_and_neighbours.json`) | Natural Earth 1:10m Cultural Vectors, Admin 0 Countries, version 5.1.2, from https://github.com/nvkelso/natural-earth-vector, trimmed to the UK, Ireland, the Isle of Man, the Channel Islands, France, Belgium and the Netherlands near the UK | Public domain. Its licence file says "All versions of Natural Earth raster + vector map data found on this website are in the public domain" and "No permission is needed to use Natural Earth. Crediting the authors is unnecessary." (read 9 October 2026) | Made with Natural Earth. Used only to decide which charger locations are in the UK; nothing from it is shown on the map or added to charger records |

## Other material this repository quotes

- **Legislation and government guidance:** short extracts from legislation.gov.uk and
  gov.uk. Contains public sector information licensed under the Open Government Licence
  v3.0.
- **OCPI 2.2.1 specification:** © EVRoaming Foundation, made available under the Creative
  Commons Attribution-NoDerivatives 4.0 International licence. This project cites it by
  section number and quotes a few words. It does not copy or redistribute the document.
  https://evroaming.org/app/uploads/2021/11/OCPI-2.2.1.pdf
