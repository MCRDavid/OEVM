# Mer UK fixtures

Response downloaded from Mer UK's "Mer Live Charge Point Data" link on 10 October 2026, in
one request, with `python -m pipeline.run --live mer_uk --save-raw`, from the link on Mer's
"Live Charge Point Data" page:

- https://uk.mer.eco/wp-json/ozev/v1/data (176 locations and 61 tariffs)

The response holds both modules: `{"data": {"locations": {...}, "tariffs": {...}}}`, each an
OCPI 2.2.1 response object with its own status_code. It sends no paging headers. To keep
the fixture short:

- `data.json` keeps 6 of the 176 locations, chosen to cover the statuses AVAILABLE,
  CHARGING, BLOCKED, OUTOFORDER and UNKNOWN, AC single phase, AC three phase and DC (CCS
  and CHAdeMO), one location with regular opening hours (the only one in the feed that is
  not 24/7), two with the extra "parkingType" field, and a tariff with no tariff_alt_text.
- It keeps the 4 tariffs those locations refer to.
- Every record is exactly as Mer UK sent it, and the two response objects keep their
  timestamp, status_code and status_message. The content-type and Link headers were kept;
  the Link header points at the WordPress API root, not at a next page.

`manifest.json` tells `python -m pipeline.run --fixtures` how to replay it.

## Source and licence

Contains data from Mer UK published under the Public Charge Point Regulations 2023, used
in line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: https://uk.mer.eco/wp-json/ozev/v1/data, retrieved 10 October 2026.
- This data belongs to Mer UK. It is not covered by this project's Apache-2.0 code
  licence. See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
