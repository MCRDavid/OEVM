# Charger statuses every hour, and what Eco-Movement's statuses endpoint sends

From 13 November 2026 the details screen for a charger shows statuses read again every hour,
rather than only by the daily fetch. For the networks on Eco-Movement's platform the project
reads a statuses endpoint, which in a test on 10 November 2026 sent a whole network's statuses in
one response. In that test, 2,272 of ubitricity's 14,215 matched charge points had a different
status from the daily fetch 23 hours earlier.

## Statuses every hour

On 12 November 2026 the project owner decided that statuses are read again every hour and served
from this site itself, so no new party sees which charger a visitor opens. They show on the
details screen only, with the time the feed was read. The points on the map and the "Hide out of
service" filter still come from the daily fetch.

The hourly refresh started on 13 November 2026. Its first runs that morning each read the
statuses of all 44 networks fetched from a feed in about 14 minutes, keeping to one fetch at a
time for each host and to each network's published rate limits. The two copies operators sent
by email, Connekt's and Zest's, are never refreshed, so their chargers keep "status unknown". The
site's status files were served with a cache time of 10 minutes on 13 November 2026, so a status
can be up to 10 minutes older in a visitor's browser than on the site.

A refresh reads only statuses. Prices, locations, coordinates and every check on them still come
from the daily fetch, and a status is shown only for a location that fetch has already put on the
map.

## Eco-Movement's statuses endpoint

The map reads 23 networks through Eco-Movement's platform. Its documentation describes a
statuses endpoint that "Returns realtime updates for all EVSES of a CPO", and says "The
`statuses` endpoint has a rate limit of 1 request per 30 seconds". On 10 November 2026 the project
asked it once with each of three networks' tokens: WCCC Edgbaston, Aldi Stores Limited and
ubitricity.

- **The address needs a trailing slash.** Without it the server answered HTTP 307, a redirect to
  the same address with a slash, for all three tokens; with the slash it answered normally.
- **One request returns a whole network.** ubitricity's response held 12,550 locations and 14,225
  charge points, Aldi's 266 and 1,140, and WCCC Edgbaston's 2 and 10, each with a total count and
  no link to a further page.
- **Only ids, times and statuses.** Each record gives a location id, a last updated time and, for
  each charge point, its uid, EVSE id, status and last updated time. There is no country code,
  party id or publish flag, so the map lays these statuses only over locations the daily fetch
  has already published.
- **The ids match the map.** Every Aldi and WCCC Edgbaston location matched the map files of the
  day before, as did 12,545 of ubitricity's 12,550, with five new since the daily fetch and five
  gone. Every charge point uid matched. One ubitricity charge point, with the same uid and EVSE
  id, was listed under two locations.
- **The statuses are OCPI 2.2.1 values.** ubitricity's were AVAILABLE (11,907), CHARGING
  (1,712), UNKNOWN (447) and OUTOFORDER (159), and every charge point gave a last updated time.
- **They change through the day.** Compared with the daily fetch 23 hours earlier, 2,272 of the
  14,215 ubitricity charge points that matched, and 47 of Aldi's 1,140, had a different status.

The hourly refresh asks each of these networks' statuses endpoints once an hour, well within
the published limit.
