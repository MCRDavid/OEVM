# ParkRecharge fixtures

Responses downloaded from the two "Access Reference Data" links on ParkRecharge's "Public
Charging and Open Data" page on 11 October 2026, one request each, with
`python -m pipeline.run --live parkrecharge --save-raw`:

- https://ocpi-pcpr.hubeleon.net/2.2.1/reference (447 locations)
- https://ocpi-pcpr.hubeleon.net/2.2.1/referencetariffs (469 tariffs)

The host's TLS certificate expired on 7 October 2026. Both files were read past it under
the repository owner's decision recorded in `operators/parkrecharge.yaml`
(expired_certificate, ADR 0021): the chain and host name were checked, and the server
presented the one certificate that decision names.

Each file is one OCPI 2.2.1 response holding every record, with no paging headers. To keep
the fixtures short:

- `locations_page1.json` keeps 10 of the 447 locations, chosen to cover the statuses
  AVAILABLE, CHARGING and UNKNOWN, AC single-phase, AC three-phase and DC connectors (CCS
  and CHAdeMO), last_updated given as "0000-00-00T00:00:00Z", a tariff that prices
  everything at zero, tariffs missing from the tariffs file, a connector with no power
  figure, the two locations named as test units, and one of the Argentine locations.
- `tariffs_page1.json` keeps every tariff those locations refer to that the tariffs file
  holds (8), including the Argentine one in pesos.
- Every record is exactly as sent. Only the content-type header was kept.

`manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from ParkRecharge published under the Public Charge Point Regulations 2023,
used in line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: the two URLs above, linked from https://parkrecharge.com/public-charging,
  retrieved 11 October 2026.
- This data belongs to ParkRecharge. It is not covered by this project's Apache-2.0 code
  licence. See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
