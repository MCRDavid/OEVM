# Prices and VAT: ten networks state it, two do not

Ten of the twelve networks whose data the map uses give a VAT rate with their prices. char.gy and
Clenergy EV give none, so their prices could not be compared directly with anyone else's. By the
project owner's decision of 22 October 2026, the map adds VAT at 20% to those two networks' prices,
so that every price on the map includes VAT. This post sets out what the feeds say and how the map
shows it.

## What OCPI 2.2.1 asks for

In OCPI 2.2.1, the data requirement under the regulations, each price in a tariff is given excluding
VAT, with the VAT rate in a separate field. The specification reads a missing VAT rate as no VAT
applying, which is different from a rate of 0.

## What the feeds send

Counted from the map's data after the daily run of 22 October 2026 (04:18 UTC), by each location's
price line:

| Network | Priced, VAT rate given | Priced, no VAT rate | Price unknown, free or no energy price |
|---|---|---|---|
| Arnold Clark Charge | 2 | 0 | 124 |
| ChargePlace Scotland | 1,288 | 0 | 191 |
| char.gy | 0 | 4,846 | 1,147 |
| Clenergy EV | 0 | 1,395 | 5 |
| Evolt Network | 617 | 0 | 48 |
| GeniePoint | 302 | 0 | 3 |
| Jolt | 70 | 0 | 0 |
| Mer UK | 175 | 0 | 0 |
| MFG EV Power | 598 | 0 | 0 |
| ParkRecharge | 286 | 0 | 0 |
| PoGo Charge | 156 | 0 | 5 |
| ScottishPower Recharge | 63 | 0 | 2 |

Even where the rate is given, it is written differently: as the number 20, as 20.0, or, from Arnold
Clark Charge and ScottishPower Recharge, as the text "20.0000". In the samples of each feed kept for
this project's tests, every rate given is 20; no rate of 0 was seen. Whole feeds have not yet been
checked for a rate of 0.

## char.gy and Clenergy EV

Read strictly by OCPI 2.2.1, a price with no VAT rate is the final price. That does not fit what we
found:

- char.gy's feed gives 0.325, 0.4917 and 0.45 pounds per kWh. Its [pricing
  page](https://char.gy/pricing) gave 39p, 59p and 54p when checked on 9 October 2026: in each case
  the feed price plus 20%. The page does not itself say whether its prices include VAT.
- Clenergy EV's website gives no charging prices and says nothing about VAT on charging (read 22
  October 2026). Its tariff file, read once on 22 October 2026, held 131 tariffs, 126 of them in
  pounds, and none of its 142 price components gave a VAT rate. Only 23 of the 126 prices per kWh in
  pounds are whole pence as published, but 120 come to a whole penny once 20% is added: 0.4167
  becomes 50p, for example, and 0.5417 becomes 65p. That suggests round prices with VAT taken off,
  but it is our inference: Clenergy EV has not said so, and it needs confirming.

## What the map does now

Before 22 October 2026 the map showed these two networks' prices as published, marked "excl. VAT",
so a char.gy charger read "from 32.5p excl. VAT" beside other networks' prices that included VAT. A
driver comparing the two figures could pick the wrong charger.

The project owner decided on 22 October 2026 that, for char.gy and Clenergy EV, VAT at 20% is added
to every price that gives no VAT rate. The decision and its evidence are recorded in each network's
operator file and on the [transparency page](transparency/). The same char.gy charger now reads
"from 39p", and its details say "including VAT, with VAT at 20% added by this project where the
operator's feed does not state it". The operator's own tariffs are published unchanged in each
location's data file; only the prices shown are worked out with VAT added. Any other network whose
prices give no VAT rate keeps the "excl. VAT" mark until a decision is recorded for it.

## Other ways prices differ

Prices also differ between feeds in ways that VAT does not explain, set out in [the post on data
quality](findings/data-quality/): tariffs in euros, US dollars or Canadian dollars in UK feeds,
tariffs that chargers name but that are missing from the feed, a test tariff with every price zero,
and prices sent as text rather than numbers. The map shows prices in pounds only, never converts
currencies, and shows "Price unknown" rather than guess.
