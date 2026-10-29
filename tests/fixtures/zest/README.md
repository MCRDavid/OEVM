# Zest fixtures

Zest publishes no address to fetch its data from. It sent its data by email on
28 October 2026 as two OCPI 2.2.1 responses made on 26 October, which are kept as sent,
gzipped, in `sent_copies/zest/` and shown on the map by the repository owner's decision of
29 October 2026 (`sent_copy` in `operators/zest.yaml`, ADR 0029). Nothing was fetched to
make these fixtures.

To keep the fixtures short:

- `locations.json` keeps 13 of the 2,005 location records: 9 locations, 4 of which (ids
  1358, 1660, 1918 and 1987) appear twice in the copy, with both records kept in their
  places. They cover 5, 7 and 22 kW Type 2 sockets, DC CCS at 120, 160 and 300 kW, the
  statuses AVAILABLE, CHARGING, OUTOFORDER, INOPERATIVE and UNKNOWN (all shown as unknown),
  and states sent as "undefined" or not sent.
- `tariffs.json` keeps the 8 tariffs those locations name, among them 93 and 530, whose
  idle fee is a PARKING_TIME price of 0.08 an hour while their text says "£0.10/min", and
  428, whose min_price is 0. Every tariff's text carries HTML tags.
- Every record, and each response's `status_code` and `timestamp`, is exactly as Zest sent
  it; only the other records were removed, and the JSON re-indented.

`manifest.json` tells `python -m pipeline.run --fixtures` to read these two files in place of
the ones named in `operators/zest.yaml`.

## Source and licence

Contains data from Zest, licensed under CC BY 4.0
(https://creativecommons.org/licenses/by/4.0/). Adapted from Zest's data. The data is not
covered by this project's Apache-2.0 code licence.
