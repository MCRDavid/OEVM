# Thirteen networks through one platform: what Eco-Movement's feeds show

On 26 October 2026 Eco-Movement, which serves the regulation 10 data of many UK networks from one
platform, sent the project a token for each of 13 networks, after the project's requests through the
networks' own forms on 23 and 24 October 2026. On 29 October 2026 the 13 feeds listed about 17,300 locations,
nearly three quarters of them ubitricity's. The platform's rate limit makes reading them all take
nearly an hour a day. The feeds show three different ways of handling VAT, prices of zero,
tariffs in US dollars, a field in the wrong shape and time zones from far outside the UK. This post
sets out what we found.

## The networks

Locations each feed listed on 29 October 2026 (its X-Total-Count), before the map's own checks:

| Network | OCPI party | Locations listed |
|---|---|---|
| ubitricity | GB UBI | 12,531 |
| Pod | GB POD | 1,809 |
| Blink Charging | GB BLK | 875 |
| RAW Charging | GB CPI | 514 |
| Lidl | GB LDL | 414 |
| ChargePoint | GB CPI | 331 |
| evyve | GB DRI | 224 |
| ESB Energy | GB ESB | 202 |
| ESB ecars (Northern Ireland) | GB ESB | 125 |
| IONITY | GB IOY | 84 |
| Allego | GB ALL | 77 |
| evpoint | GB CPI | 38 |
| Source EV | GB SGB | 37 |

ChargePoint, evpoint and RAW Charging share the party GB CPI, each with its own token and feed.
Each is shown under its own name, and their record ids never overlap.

**Update, 29 October 2026:** nine more networks on the same platform were switched on that evening,
so 22 are read from the daily run of 30 October 2026. Eco-Movement emailed tokens for eight of them
on 27 October 2026, all under the OCPI party GB GFX: Aldi Stores Limited (266 locations listed on 29
October 2026), drax-Ista (32), Travis Perkins (15), Volvo (3), GFX-GB Drax (2), WCCC Edgbaston (2),
Drax Group (1) and Southampton Apartment Hotels (1). The emails do not say which request they
answer; that they answer the project's request through Drax's form on 23 October 2026 is inferred
from their names and the shared party. Drax's announcement of 10 June 2026 says Aldi "has
transitioned around 1,200 electric vehicle (EV) chargers at more than 250 stores across the UK over
to Drax". The ninth, Shell Recharge (GB TNM, 266 locations), came on 28 October 2026 in reply to the
request for Shell's networks. None of the nine gives a VAT rate, and most of their prices come to
whole pence once 20% is added (Aldi's 0.333 and 0.517 pounds per kWh are 40p and 62p), so by the
owner's decision the map adds VAT at 20%. Shell's tariff texts give the price before VAT, such as
"ALL: £0.74 per kWh" for a price of 0.7417.

## One platform, one rate limit

Every feed comes from open-chargepoints.com as OCPI 2.2.1, with the network's token in an
"Authorization: Token" header. Eco-Movement's documentation says "The `locations` endpoint has a
rate limit of 30 requests per 1 hour", and says the same of the `tariffs` endpoint. It does not say whether a
limit applies to each token or to each address, what kind of time window is used, or what happens
when a limit is reached. Each network has its own token, so the project owner decided on 29
October 2026 to read the limits as applying to each token: each network keeps 125 seconds between
its own requests, the networks are read one after another, and any two requests to the platform are
at least 2 seconds apart. A full read takes 26 pages of locations and 13 of tariffs, 39 requests in
about 55 minutes. Read as one allowance shared by every network, it would take about 80.

**Update, 29 October 2026:** later that day the project owner decided to read each token's limit
as an hourly allowance that may be used close together, rather than spread evenly, keeping one
request in hand. Eco-Movement's guide "strongly recommends limiting simultaneous GET requests to a
maximum of 5", so no more than 5 requests go to the platform at once. If any request is refused or
asked to wait, every network goes back to even spacing for the rest of the run. In a run that
evening all 22 networks were read in 1 minute 18 seconds, 57 requests, with nothing refused, and the
whole daily fetch took 14 minutes.

Every response recorded on 29 October 2026 linked to a next page that starts after the last record,
for example at offset 77 when the total was 77. The project stops once the stated total has
arrived, which saves one request per network for each of locations and tariffs.

## VAT, three ways

OCPI 2.2.1 gives each price excluding VAT, with the VAT rate alongside. Not every feed follows
that, so on 29 October 2026 the project owner decided how to read three groups of them. Each reading
is inferred from the figures and needs confirming by the network.

- **Pod, ESB Energy and ESB ecars** state VAT at 20%, but every energy price is already a whole
  number of pence: 823 of 823 at Pod (most often 38p and 42p per kWh), 19 of 19 at ESB Energy and
  9 of 9 at ESB ecars. Read as OCPI 2.2.1 says, Pod's 0.38 would become 45.6p and ESB Energy's 0.80
  would become 96p. By the owner's decision the stated VAT is read as already in these prices.
- **Allego, Blink Charging, evpoint, Lidl and RAW Charging** give no VAT rate, and their prices
  mostly come to whole pence once 20% is added: Allego's tariff text gives "Energy: 0.63 GBP/kWh"
  for a price of 0.525, Lidl's 0.6167 becomes 74p, and 56 of Blink's 57 and 55 of RAW's 67 energy
  prices come to whole pence that way. By the owner's decision the map adds VAT at 20% and says so
  in each price.
- **ChargePoint** gives no VAT rate, and its figures do not settle it: 120 of its 167 energy prices
  in pounds are whole pence as published and 106 once 20% is added. Its prices are shown as
  published and marked "VAT not stated".

Source EV is a fourth case. One of its two tariffs gives VAT as 0.2 on a price of 0.45 pounds per
kWh, while the other gives 20. OCPI 2.2.1 gives VAT as a percentage, so 0.2 reads as 0.2%, and the
map shows that tariff as published, at 45.1p per kWh. It probably means 20%, which needs confirming
by Source EV.

## Prices of zero, and prices in dollars

Two of Pod's tariffs have every price zero. In the first 1,000 of its locations, 163 connectors at
63 locations name one of them, at sites such as Sainsbury's stores, a McDonald's and schools. The
feed gives no charge, and on 29 October 2026 the project owner decided these connectors are shown
as published, so they show as free rather than "Price unknown". Whether drivers pay nothing at every
one of these sites needs confirming by Pod.

ChargePoint has two tariffs in US dollars, every price zero, and they are the only tariffs named by
115 connectors at 37 locations. RAW Charging has one such tariff, named by 29 connectors at 8
locations. The map shows only prices in pounds and never converts a currency, so these connectors
show "Price unknown".

## Fields in the wrong shape

- **Parking restrictions** come as a single string, such as "ev_only,plugged" or "customers",
  where OCPI 2.2.1 has a list of values: at 240 of Allego's chargers, 1,408 of Lidl's and 75 of
  ubitricity's. The map does not read them and shows those chargers' parking restrictions as
  unknown.
- **Power**: every connector at Allego and Blink Charging gives its maximum power as 0 watts. The
  map works out their power from voltage and current instead, which Eco-Movement's documentation
  says it validates and corrects.
- **Time zones**: 404 of Blink Charging's 875 locations give "UTC". Nine ChargePoint locations in
  England and Wales give "Europe/Jersey" (8) or "Atlantic/St_Helena" (1), two evpoint locations
  give "Europe/Jersey", one RAW Charging location gives "Atlantic/St_Helena", and one Lidl location
  in Hull gives "Europe/Warsaw". The map shows every time in UK time, so none of these changes
  anything on it.

**Update, 30 October 2026:** from that day the map reads parking restrictions sent as one piece
of text as a list, since the words are OCPI 2.2.1's own values. Travis Perkins and drax-Ista send
them the same way, so five networks did, at 2,462 charge points in the run of 30 October 2026.
Blink Charging's voltages make some of its chargers look faster than they probably are: see [the
post on plugs and power](findings/plugs-power-and-misplaced-values/).

## Outside the UK

12 of Pod's first 1,000 locations are on the Isle of Man, with postcodes starting IM and the
country given as GBR. The Isle of Man is a Crown Dependency, not part of the UK, so, like every
location outside the UK, they are left off the map and listed on the [feed health page](status/).

## evyve's two party ids

evyve's own feed uses the OCPI party GB DRI. EV Roam's register, described in [the post on small
networks](findings/small-networks/), lists evyve as GB*EVY, and Monta's feed carries the same 224
locations under GB EVY, with no prices. By the owner's decision of 29 October 2026, evyve's own
feed is shown, with its prices, and Monta's copies are left off while it is on the map, as for
Urban Fox.
