# Evolt Network fixtures

Responses downloaded from the "Locations" and "Tariffs" links in Evolt Network's FAQ
answer "Does Evolt Network offer open data API access?" on 10 October 2026, one request
each, with `python -m pipeline.run --live evolt --save-raw`:

- https://info.smartcharging.uk/public_feed/locations/3666 (710 locations)
- https://info.smartcharging.uk/public_feed/locations/3666/tariffs (289 tariffs)

Each file is one OCPI 2.2.1 response holding every record, with X-Total-Count and X-Limit
headers equal to the number of records and a `meta` object giving the same total. Location
and connector ids are JSON numbers rather than strings. To keep the fixtures short:

- `locations_page1.json` keeps 8 of the 710 locations, chosen to cover:
  - the statuses AVAILABLE, CHARGING, INOPERATIVE and UNKNOWN, AC single phase, AC three
    phase and DC;
  - tariffs with a session fee after a minimum duration, a price per hour and a minimum
    price, and a tariff whose only price is a flat fee of 0;
  - one location whose connectors name a tariff that is not in Evolt's tariff response
    (it is in ChargePlace Scotland's, and in
    `tests/fixtures/chargeplace_scotland/tariffs_page1.json`);
  - a location with 18 EVSEs, three of whose connectors give 0 for max_amperage and
    max_electric_power;
  - two locations that are not shown on the map, one on the Isle of Man and one with
    country AUS in Western Australia;
  - "Cadworks Castle Building Services", whose postcode (G2 7LP) is in Glasgow but whose
    longitude is 4.26275, in the North Sea; the map shows it with the minus sign added,
    by the repository owner's decision recorded in `operators/evolt.yaml`.
  X-Total-Count, X-Limit and `meta.total` were changed to 8 to match.
- `tariffs_page1.json` keeps the 8 tariffs those locations name that are in the response,
  and the 6 tariffs that the PoGo Charge and ChargePlace Scotland fixture locations name,
  which are only in this response, so the tests can check they are used by the repository
  owner's decisions recorded in `operators/pogo_charge.yaml` and
  `operators/chargeplace_scotland.yaml` (ADR 0020). Its X-Total-Count, X-Limit and
  `meta.total` were changed to 14 to match.
- Every record is exactly as sent, in the order sent. The content-type, X-Total-Count and
  X-Limit headers were kept.

`manifest.json` tells `python -m pipeline.run --fixtures` how to replay them.

## Source and licence

Contains data from Evolt Network published under the Public Charge Point Regulations 2023,
used in line with the Open Government Licence v3.0
(https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/).

- Source: the two URLs above, linked from https://evoltnetwork.co.uk/faqs/, retrieved
  10 October 2026.
- This data belongs to Evolt Network. It is not covered by this project's Apache-2.0 code
  licence. See `DATA_LICENCES.md` at the repository root.
- The data is a snapshot for testing and will go out of date. Do not use it to find a
  charger.
