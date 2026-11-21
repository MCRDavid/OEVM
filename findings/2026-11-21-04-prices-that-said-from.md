# Prices that said "from" but never changed

A price label on the map says "from" when its price applies only at some times, so a driver knows
the price may be higher when they arrive. Between 15 and 21 November 2026 three ways that feeds
write a price that never changes made labels say "from" all the same: a start date that had
already passed, a day that runs from midnight to 23:59, and a day price and a night price that are
the same. By the project owner's decisions, the map now reads each of these as one price that
applies at any time.

OCPI 2.2.1 lets each part of a tariff carry conditions, such as a time of day, days of the week or
a date range. Where a price has a condition, the map's details say when it applies, and the label
marks it "from". In each case below, the feed's tariffs are published unchanged in each location's
data file; only the wording and the labels changed.

## A start date that had passed

Every bp pulse tariff gives a start date of 23 October 2025. Read in November 2026, its prices said,
for example, "65p per kWh from 23 October 2025", and its labels said "from 65p". On 15 November 2026
the owner decided that a start date that has passed when a tariff is read is left out of when its
price applies. The price then counts as applying at any time, and its label no longer says "from".
A start date still to come is shown as before.

## Midnight to 23:59

After that change, every Shell Recharge label on the map still said "from 89p", because its tariffs
apply from midnight to 23:59 every day, and the map treated that as a time of day. On the live data
of 16 November 2026, ChargePoint, ESB ecars, ESB Energy, evpoint, Mer UK and RAW Charging gave the
same times. The owner decided that day that midnight to 23:59 means all day, as midnight to
midnight already did. Other times, such as midnight to 23:58 or 07:00 to 23:59, are still said as
they are.

## The same price day and night

Go Zero's tariffs, first read on 20 November 2026, each give two energy prices, one from 22:00 to
06:00 and one from 06:00 to 22:00 every day, at the same figure. The details said "66p per kWh
from 22:00 to 06:00, 66p per kWh from 06:00 to 22:00 including VAT", and the label said "from
66p", which suggests the price can be higher. See [the post on Go Zero's
feed](findings/go-zero-and-no-data-route/).

On 21 November 2026 the owner decided to show one price when a tariff costs the same at every hour.
The map now does so only when every part gives exactly the same prices, no part has a condition
other than a time of day, each applies on every day of the week, and their times together cover
the whole day. Go Zero's prices now read "66p per kWh including VAT", with a plain "66p" label.
Anything else, such as a lower price at night, an hour with no price, weekdays only or a limit on
the amount of energy, is said as before. A sample of 42 published locations from the 13 networks
with "from" labels on 20 November 2026 showed no other change.

If a label still says "from" where a network's price never changes, please [report a
mistake](report/).
