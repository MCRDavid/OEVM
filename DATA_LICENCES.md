# Data licences and sources

General information, not legal advice. Last reviewed 8 October 2026.

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
| Attribution | Each operator's statement is in its registry file (`operators/<id>.yaml`) and listed below. The site will show attribution with the data and link to this page and the licence. |
| Provenance | Every record stores its source URL, licence, fetch time and method. |
| No endorsement | Neutral wording only. [DISCLAIMER.md](DISCLAIMER.md) says the project is not affiliated with or endorsed by any operator or public body. |
| No logos or trade marks | Operator logos and brand marks are never used. Names are used only to say where data comes from. |
| Publish flag | OCPI 2.2.1 says a location with `publish` set to false may not be published on a website or app. The adapter never keeps those locations, or any without a publish flag. |
| Access terms | Rate limits are set in each registry file and keys are kept as secrets. An operator is only switched on once its own pages have been read and its terms recorded (`licence.checked`). |
| Faithful data | Data is converted between formats but not "corrected". Values that are not valid are recorded as unknown and logged. Operator data is never overwritten with data from other sources. |
| No personal data | Operator feeds hold charger data, not personal data. Evidence files must not contain names or personal email addresses. |

## Sources

| Source | Data | Licence | Attribution | Terms checked | Used for |
|---|---|---|---|---|---|
| char.gy | https://char.gy/open-ocpi/locations and https://char.gy/open-ocpi/tariffs | OGL v3.0, on the PCPR basis above | Contains data from char.gy published under the Public Charge Point Regulations 2023, used in line with the Open Government Licence v3.0. | 7 October 2026: char.gy's open data page states no other licence or terms | Test fixtures in `tests/fixtures/chargy/`. Not yet published on a site. |
| Jolt | https://api.joltcharge.com/v1/uk/public/locations and https://api.joltcharge.com/v1/uk/public/tariffs/{tariffId} | OGL v3.0, on the PCPR basis above | Contains data from Jolt published under the Public Charge Point Regulations 2023, used in line with the Open Government Licence v3.0. | 7 October 2026: Jolt's help page, read in a browser because it returns a browser check to automated requests, states no licence, terms or rate limits. 8 October 2026: the same article, read through the help centre's article data, says the same | Nothing yet. Switched off until its adapter is built. |

The other operators in `operators/` have no data in this project yet. Each gets a row here
when its terms have been checked and it is switched on.

Gridserve's API Fair Use Policy was read on 8 October 2026. It says intellectual property
in the API Data remains Gridserve's and describes the data as confidential and
proprietary, so its licence is recorded as unknown and it stays switched off until the
terms for the data are clarified with Gridserve (see `operators/gridserve.yaml`).

## Planned layers, kept separate

These are planned in the blueprint. Each source's terms must be read and recorded here
before its layer is built.

| File | Source | Licence |
|---|---|---|
| `operators-combined.geojson` | Operator feeds | OGL v3.0, with each operator's attribution |
| `osm.geojson` | OpenStreetMap | ODbL. Kept as a separate layer so it is not merged into operator data. |
| `ocm.geojson` | Open Charge Map | Open Charge Map's terms, recorded per record and per data provider |
| `reports.geojson` | User reports | CC BY 4.0, with the reporter's consent |

## Other material this repository quotes

- **Legislation and government guidance:** short extracts from legislation.gov.uk and
  gov.uk. Contains public sector information licensed under the Open Government Licence
  v3.0.
- **OCPI 2.2.1 specification:** © EVRoaming Foundation, made available under the Creative
  Commons Attribution-NoDerivatives 4.0 International licence. This project cites it by
  section number and quotes a few words. It does not copy or redistribute the document.
  https://evroaming.org/app/uploads/2021/11/OCPI-2.2.1.pdf
