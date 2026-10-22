# 0026: Price labels on the map

Date: 2026-10-17. Status: proposed.

The owner asked for the price of each charger to be shown above its point on the map, so
people can see the cheapest place to charge nearby without opening every charger: the
cheapest price the visitor can use there, through the charging plans they ticked, or
otherwise through a free app or paying at the charger by contactless card.

## Decisions

- **One label per point: the lowest price per kWh the visitor can pay there.** It is the
  lowest of each connector's label and the fixed price of a plan the visitor ticked
  (`site/assets/js/labels.js`). Only the price per kWh is compared, as in a site's
  details (ADR 0016): fees per session or for staying longer are left out, and the key
  and the details say so.
- **Every tariff a connector lists counts.** The price shown for a connector prefers its
  pay-at-the-charger tariffs (`pipeline/tariffs.py`), but the label uses the lowest price
  among all of them, because the operator's own app or account is free to use and is
  often cheaper (GeniePoint: 82.8p with its app, 92.4p by contactless, 17 October 2026).
  OCPI 2.2.1 cannot say whether a tariff needs a paid subscription, so a feed tariff is
  taken as open to anyone, as the details already list it. Tariffs from a related
  operator's feed count only where ADR 0020 already matched them by exact id. A tariff
  outside its own start and end dates when it was fetched does not count.
- **"Free" only for a connector confirmed free.** A label says "Free" only when the
  connector's price state is free_confirmed. "0p" is never shown, because it reads as
  free. A tariff that charges nothing per kWh at all (only by time or per session) is
  left out, because it is not priced per kWh. When a connector that is not confirmed free
  lists a free tariff, or one that is free per kWh only at some times, it has no label:
  its lowest price per kWh is 0p, which a label could not say. Tariffs the owner named in
  zero_price_tariffs (ADR 0022) give no label.
- **The lowest figure, with its VAT basis.** A price whose VAT is not stated is marked
  "excl. VAT" (char.gy and Clenergy publish no VAT) and VAT is never added. The lowest
  figure wins whether or not its VAT is stated, because a higher price including VAT
  could be the dearer one: 30p plus any VAT is still less than 60p. Prices are compared
  to the tenth of a penny the label shows. On a tie, a price including VAT comes first,
  then a price that applies all the time. A price that applies only in some cases (at
  some times, or at some speeds or amounts of energy, as the tariff's restrictions say)
  is marked "from", for example "from 32.5p excl. VAT" for char.gy's weekday night price.
- **Plans count only once ticked.** A plan from `providers/` counts at a location only
  when the visitor ticked it under "Your charging plans", its provider publishes a fixed
  price including VAT, and it names the location's network. Plans nobody ticked are left
  out because many are limited (taxi drivers only, off-peak hours, one council area).
  Discounts are never turned into prices (ADR 0016). A plan whose price applies only at
  some times (`only_at_some_times` in its provider file, such as off-peak plans) is
  marked "from". A plan is compared like any other price including VAT; on a full tie
  the operator's own price is kept, as it needs no plan. A label from a plan is drawn in
  amber and the list and details say "with your plan".
- **Labels follow the filters.** Only connectors that match the power, connector, price
  and status filters count, so a rapid charger is never labelled with a slow connector's
  price. No label shows a price above the "Maximum price per kWh" filter; a price whose
  VAT is not stated is held to it as published, since VAT could only raise it. The line
  in a site's details ("Cheapest here") names the tariff only when one listed tariff
  alone gives that price, and follows filter changes while the details are open.
- **Wording stays in the pipeline.** Each kind of connector in `data/locations.geojson`
  carries `low` (the lowest price per kWh, in pence), `lvat`, `lvar` and `lt`, the label
  worded by `pipeline/pricing.py` (`map_label`); plans in `data/plans.json` carry `label`
  (`plan_label`). The browser only picks one. The map file grows by about 17%
  before compression (7% gzipped, measured on the fixtures).
- **Readable at a glance.** Labels appear from zoom 11 (about a town). Where labels would
  overlap, the cheapest are placed first and the others left out; a label never covers
  a numbered circle's count, and the letters in the points are drawn over the labels.
  Grouped points (numbered circles) have no label. Pressing a label opens its own
  charger, even where it lies over a neighbouring point. The list shows the same label
  for each charger, so the information does not depend on seeing the map. Where a
  browser hands back made-up pixels from a canvas (Tor Browser, for example), labels are
  drawn with a halo instead of a box.

## Needs testing

- Whether any operator's feed lists a tariff that needs a paid subscription (OCPI 2.2.1
  has no field for it). If one does, the label could show a price that needs one.
- The "Maximum price per kWh" filter still hides chargers by their highest
  pay-at-the-charger price, so a charger can be hidden by it while its label, from the
  operator's app, is under the limit.
- No tariff in the feeds sampled on 17 October 2026 (Glasgow and Leeds) gave a start or
  end date, or a price per kWh that is 0p at some times, so those rules have only been
  tested with made-up tariffs.
