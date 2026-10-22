# What arrives: quirks in the data we can read

Twelve networks' data can be collected today, and none of it is perfect. Sites abroad sit in UK
feeds, coordinates point into the sea, test sites are published, and in one feed almost no connector
names a tariff. Every case below is recorded, with its date, on the [transparency
page](transparency/); items without a date here were found between 7 and 12 October 2026. The map
never replaces an operator's figures with someone else's; a value that cannot be trusted is shown as
unknown or left off the map, apart from the obvious coordinate corrections described below.

## Out of date

- ParkRecharge's location file, read on 11 October 2026, was dated 27 April 2026, although its page
  said the data is updated daily. 59 of its 447 locations gave their last update as
  "0000-00-00T00:00:00Z", which is not a valid date. The new feed it linked on 17 October holds 288
  locations.
- Clenergy EV gives every location's last update as the time of the request, so a location's own
  date does not show when it last changed; each charge point's date does vary (9 October 2026).

## In the wrong place

- **Sites outside the UK in UK feeds.** Clenergy EV marks every location as in the UK, but some
  coordinates are in the Caribbean, Canada and Ireland. Evolt Network has 45 locations with Isle of
  Man postcodes, marked as in the UK, and one in Western Australia (10 October 2026). ParkRecharge's
  April file had 7 locations in Argentina marked as in the UK. The map shows only points genuinely
  in the UK.
- **Latitude and longitude swapped.** Two Clenergy EV locations with UK postcodes, in London and
  Leeds, were published the wrong way round, which puts them far outside the UK.
- **A missing minus sign.** A Clenergy EV site in Leeds, an Evolt Network site in Glasgow and a
  GeniePoint site in Crewe each have a longitude east of Greenwich, which puts them in the North
  Sea.

The project owner decided that obvious swaps and missing minus signs at UK addresses are shown in
the right place, with the operator's own figures kept and a note on the location's details on the
map. Sites outside the UK are left off.

## Test, private and removed sites

- ParkRecharge's April file included two test units, "UK-HBN-PAYTERTEST" and "TR0047 Hubeleon Test
  Centre", both marked for publishing. Both are still in the new feed (17 October 2026), one now
  named "PR06767 H19 Test Unit"; the map leaves them off by the owner's decision.
- ScottishPower Recharge's two connectors at Glengarry name a tariff described as "Harbour test",
  with every price zero (11 October 2026). The map shows "Price unknown" there rather than "Free",
  by the owner's decision.
- PoGo Charge and Evolt Network mark some charge points TAXI_ONLY, which is not an OCPI 2.2.1 value.
  At 26 Evolt Network locations, such as taxi ranks and bus stations, every charge point is marked
  this way. The map hides such sites unless a visitor asks to see them.
- In ParkRecharge's new feed (17 October 2026), two location names begin "(REMOVED)" and
  "(Archived)" while their chargers report AVAILABLE or CHARGING.

## Prices that cannot be shown

- Only 2 of Arnold Clark Charge's 429 connectors name a tariff (10 October 2026), so nearly every
  site shows "Price unknown".
- 806 of PoGo Charge's 809 connectors, and 462 of ChargePlace Scotland's, name tariffs that are
  missing from their own feeds but found in Evolt Network's feed on the same host. The map prices
  them from Evolt Network's tariff only where the ids match exactly, by the owner's decision.
- 17 of the 447 tariff ids named in ParkRecharge's April file were missing from its tariff file.
- GeniePoint's tariff file repeats 22 tariffs 8 times each.
- char.gy publishes tariffs in euros and US dollars as well as pounds, though its locations name
  only the pound tariff (7 October 2026), and Clenergy EV has 5 of 129 tariffs in other currencies
  (9 October 2026). The map shows prices in pounds only.
- char.gy gives no VAT figure (7 October 2026). OCPI 2.2.1 reads a missing VAT figure as no VAT
  applying, but the map marks these prices "excluding VAT, VAT not stated" rather than assume.

## Not quite OCPI 2.2.1

The regulations name OCPI 2.2.1 as the data requirement. Most feeds we read differ from the OCPI
2.2.1 specification in some detail; whether any difference matters under the regulations is for the
enforcement authority, not this project. A few examples:

- PoGo Charge, Evolt Network and ChargePlace Scotland send ids as numbers rather than text.
- Jolt uses its own layout: its locations have no id and no publish flag, both of which OCPI 2.2.1
  requires, and it uses lower-case statuses, a "preparing" status and a connector type "CCS2", none
  of which are OCPI 2.2.1 values.
- char.gy reports a status of WORKING, and in a run on 7 October 2026 also FAULTED; neither is an
  OCPI 2.2.1 status.
- Mer UK sends locations and tariffs together from one address.
- Clenergy EV wraps its records in its own response format, at an address containing the word
  "development".
- ParkRecharge's old tariff file (read 11 October 2026) gave each tariff's elements as a single
  object rather than a list.
- Arnold Clark Charge and ScottishPower Recharge give no country code or party id, and send prices
  as text.

Each difference means more code to read the feed, and more ways for a price or a place to come out
wrong.

## Status unknown

On 10 October 2026, 2,145 of ChargePlace Scotland's 5,263 charge points and 645 of Evolt Network's
3,421 reported their status as UNKNOWN.

## Limits that are not written down

Few operators publish how often their data may be read. When ScottishPower Recharge's tariff file
was requested two seconds after its location file, the shared Fuuse host answered "The Fuuse API is
currently being rate limited" (11 October 2026). Clenergy EV's responses carry a limit of 6 but no
page says over what time. Gridserve's API Fair Use Policy sets a default of 1 request every 30
seconds per API key, while its developer documentation states no limit. This project keeps to at
least one second between requests to any host, and within any published limit with a margin on top.
