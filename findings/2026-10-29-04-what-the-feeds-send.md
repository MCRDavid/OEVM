# What the feeds actually send: keys, gaps, copies and many versions of one standard

By 29 October 2026 the project had 109 networks in its register and 45 switched on. This post steps
back from single networks and looks at what comes back across all of them: how the data has to be
fetched, how much of it can be priced, where the same sites appear twice, and how many different
shapes one standard takes. The figures come from the run of 29 October 2026 that finished at 18:42
UTC, which read 36 networks and put 32,268 locations on the map. Nine more networks are read from
30 October 2026.

**Update, 29 October 2026:** a second run that evening read all 45 networks and put 32,855
locations on the map. Across them, 88% of connectors name a tariff the same feed supplies (63,395 of
72,279) and 87% of chargers give a status other than unknown. The nine networks added that evening
name a supplied tariff for every connector but one, at drax-Ista. The figures below are from the
earlier run.

## How the data is reached

Of the 45 networks switched on:

| Route | Networks |
|---|---|
| A feed anyone can read, with no key | 17 |
| A key printed on the network's own page (Jolt) | 1 |
| A key or token issued to the project | 25 |
| A copy of the data sent by email, with no feed | 2 |

Of the 25 keys and tokens, 22 came from Eco-Movement, one for each network it serves; the others are
PLUG Charging's, Fastned's and Monta's. Most of the data comes through a few software platforms
rather than the networks' own servers: 22 networks through Eco-Movement, 4 through Fuuse, 3 through
SWARCO's smartcharging.uk and 2 through Clenergy, 31 of the 45 in all.

The other 64 networks in the register are not on the map:

| Where things stand | Networks |
|---|---|
| No open data or way to ask for it found on the network's own website | 28 |
| Not yet established | 13 |
| Access on request (a key, form or invitation), not on the map yet | 12 |
| Asked, no reply yet | 2 |
| Waiting on the project owner's decision | 1 |
| A signed agreement is asked for | 1 |
| May not be a charge point operator in scope | 7 |

So far the engagement logs record 23 access requests sent, 26 keys or tokens granted and 6 other
replies. Two networks answered with
their data as files attached to an email rather than an address to fetch it from (see [the post on
three requests answered](findings/three-requests-answered/) and [the post on Zest](findings/zest-monthly-copy/)).
Elsewhere, prices appear only on websites (see [the post on six more
networks](findings/six-more-networks/)).

## What comes back

In the run of 29 October 2026 the 36 feeds sent 32,667 locations, with 67,697 chargers and 69,252
connectors. Across them:

- 87% of connectors name a tariff that the same feed supplies, so a price can be worked out.
- 86% of chargers give a status other than unknown.
- On the map, 29,179 locations show a price, 2,893 show "Price unknown" and 196 show as free.
- ubitricity's 12,531 locations are 39% of the map.

## Missing tariffs

Most feeds price almost every connector. A few price very few:

| Network | Connectors | Naming a tariff the feed supplies |
|---|---|---|
| PoGo Charge | 813 | 0 (806 priced from Evolt Network's feed, by the owner's decision) |
| Arnold Clark Charge | 429 | 2 |
| Monta | 2,743 | 54 |
| Enfield Council | 32 | 2 |
| ChargePlace Scotland | 5,236 | 1,523 (and 26 from Evolt Network's feed) |
| char.gy | 6,032 | 4,850 |
| ScottishPower Recharge | 187 | 176 |
| PLUG Charging | 486 | 477 |

Other feeds supply a tariff that cannot be shown as a price: every price zero (127 Urban Fox
locations show "Price unknown" by the owner's decision, while 108 Pod locations show as free, also
by the owner's decision), tariffs in US dollars (ChargePoint and RAW Charging), and one Jolt tariff
whose price is not a number. GeniePoint's tariff list repeats 154 records.

## Status

char.gy sends "WORKING" and "FAULTED" (shown as working and out of order by the owner's decision),
BrightGreen sends "idle" and Jolt "preparing", none of them OCPI 2.2.1 values. ChargePlace Scotland
gives a status for 58% of its chargers and evpoint for 73%. The two emailed copies show every status
as unknown by design, because a status from the day a copy was made says nothing about now.

## One standard, many shapes

43 of the 45 networks switched on have at least one difference from OCPI 2.2.1 or data quirk
recorded in their operator files. Among them, from the run of 29 October 2026 or the operator
files:

- **Ids as numbers**: ChargePlace Scotland, Evolt Network and PoGo Charge send location and
  connector ids as numbers rather than text.
- **Lists as text**: Allego, Lidl and ubitricity send parking restrictions as a single string, 2,456
  times between them.
- **Values OCPI does not have**: "TAXI_ONLY" (Evolt Network and PoGo Charge), power types "fast" and
  "ultrarapid" and countries "GB" and "SK" (BrightGreen), a maximum power of 0 (Allego and Blink
  Charging), and time zones such as "Europe/Jersey", "Atlantic/St_Helena" and "Europe/Warsaw" for
  places in Great Britain.
- **An older version**: Roam uses OCPI 2.1.1 field names.
- **No publish flag**: Jolt and Roam, shown by the owner's decision.
- **VAT**: 18 networks give no VAT rate (the map adds 20% by the owner's decision), 4 state a rate
  but appear to include it already, one cannot be told either way, and the rest state a rate, which
  the map applies as OCPI 2.2.1 says (see [the post on prices and VAT](findings/prices-and-vat/)).
- **Old dates**: half of GeniePoint's locations were last updated more than 721 days before the
  run, half of BrightGreen's more than 342 and half of Roam's more than 323. Across the other feeds
  the median was under 2 days.
- **Paging**: Monta pages by cursor in its own format, Eco-Movement links to a page past the end,
  and the smartcharging.uk feeds send everything in one response.

**Update, 30 October 2026:** five networks, not three, send parking restrictions as text: Travis
Perkins and drax-Ista do too, and in the run of 30 October 2026 the five did so 2,462 times. From
that day the map reads them as a list. More differences, in plugs, power and floor levels, are in
[the post on plugs and power](findings/plugs-power-and-misplaced-values/).

## The same sites in more than one feed

- **Copies on platforms**: Monta's feed carries sites of networks that also publish their own. By
  the owner's decision the map shows Urban Fox's and evyve's own feeds and leaves 319 Monta copies
  off.
- **Shared party ids**: eight networks share GB GFX, three share GB CPI (ChargePoint, evpoint and
  RAW Charging), and two each share GB ESB and GB CEV.
- **Shared tariffs**: PoGo Charge's and some ChargePlace Scotland connectors name tariffs found only
  in Evolt Network's feed; 834 connectors are priced that way, by exact tariff id.
- **Networks in transition**: five sites appear in both ChargePlace Scotland's feed and Connekt's
  copy under the same or nearly the same name, with different charger ids, and at least two of them
  have no chargers listed in ChargePlace Scotland's feed. 133 of its 1,479 locations list none. Its [Transition
  Resource Hub](https://chargeplacescotland.org/transition-resource-hub/) says "many charge points
  across Scotland are being transferred to new operators" by the end of December 2026. Whether these
  are the same chargers is unknown.

Apart from these, true duplicates look rare. Only 42 pairs of points from different networks lie
within 10 metres of each other among the 32,268 on the map, mostly street chargers of two networks
on the same road or two networks in one car park.
