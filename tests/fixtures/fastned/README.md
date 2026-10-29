# Fastned fixtures

Responses recorded from Fastned's UK Open Data API (OCPI 2.2.1) on 24 October 2026 by
`python -m pipeline.run --live fastned --save-raw raw`, run once in GitHub Actions with the
key from the `FASTNED_API_KEY` secret, sent in the `x-api-key` header. The addresses come from
Fastned's key email of 24 October 2026:

- https://uk-public.api.fastned.nl/uk-public/ocpi/cpo/2.2.1/locations (42 locations in one page)
- https://uk-public.api.fastned.nl/uk-public/ocpi/cpo/2.2.1/tariffs (1 tariff in one page)

To keep the fixtures short:

- `locations_page1.json` keeps 7 of the 42 locations, chosen to cover DC connectors from
  50 kW to 400 kW, AC three-phase Type 2 cables, EVSEs with one, two or three connectors, the
  statuses AVAILABLE, BLOCKED, CHARGING, OUTOFORDER, REMOVED and UNKNOWN, REMOVED EVSEs with no
  `evse_id`, on-street and car park parking, a location in Northern Ireland, and the location
  whose postal code is in the LE area although it is in King's Lynn.
- `tariffs_page1.json` is the whole tariffs response: the one tariff every connector names.
- `X-Total-Count` was changed to match the trimmed location count. Every record is exactly as
  Fastned sent it.

Only the content-type, x-total-count and x-limit headers were kept; the key is never in a
response. `manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from Fastned published under the Public Charge Point Regulations 2023, used in
line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/). Adapted from
Fastned's data.

- Source: https://uk-public.api.fastned.nl/uk-public/ocpi/cpo/2.2.1/locations and
  https://uk-public.api.fastned.nl/uk-public/ocpi/cpo/2.2.1/tariffs, retrieved 24 October
  2026, under Fastned's Fair Use Policy for its UK Open Data API,
  https://www.fastnedcharging.com/en-gb/uk-open-data (see ADR 0028).
- This data belongs to Fastned. It is not covered by this project's Apache-2.0 code licence.
  See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
