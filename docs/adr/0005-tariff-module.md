# 0005: Connector prices from tariffs

Date: 2026-10-08. Status: accepted.

Blueprint task 6: resolve each connector's tariff ids, work out its price state and an
indicative price per kWh including VAT.

## Decisions

- `pipeline/tariffs.py` prices every connector from the tariffs it lists. Wording stays in
  `pipeline/pricing.py`, which is still the only way prices are shown.
- **No tariff listed** means "Price unknown". OCPI 2.2.1 says a free connector should still
  point to a free tariff, so a missing tariff is never read as free.
- **Unresolvable tariff ids** (listed but not in the operator's tariff data) are recorded
  on the connector. If none can be found, the price is unknown.
- **Free** only when every listed tariff was found and every one is confirmed free. One
  tariff that could not be read withholds "Free".
- **Several tariffs:** ones of type `ad_hoc_payment` are preferred, because that is the
  price someone pays at the charger without an account. Otherwise all are used, and
  different prices are all shown.
- **Conditions** are worded from each tariff element's restrictions, following OCPI
  2.2.1 section 11: the first element whose restrictions match applies for each kind of
  charge, and an element with no restrictions is the price "otherwise". Elements after it
  can never apply and are not shown. For example, GeniePoint's parking fees now read
  "plus £6.67 per hour parked after 90 minutes".
- **Indicative price per kWh:** the lowest and highest energy price that can apply,
  including VAT when the operator states it, otherwise marked "excl. VAT". It is a guide
  for filters and map labels; the full text explains the price.
- Run reports now include a price summary and the share of connectors with a tariff that
  was found, a feed health measure the blueprint lists for task 8.

## Amendment, 10 October 2026: tariffs in a related operator's feed

Where the owner records `tariffs_from` in an operator file, a tariff id that only a related
operator's feed holds can be resolved from that feed, by exact id only and only when that
operator was fetched in the same run. The tariff keeps its own provenance and the map says
which feed it came from. See ADR 0020.
