# Go Zero's feed found, and eleven more networks with no data route

On 20 November 2026 Go Zero's open data feed, which this project could not find in October, turned
up behind a public dashboard linked from Go Zero's own website, and by the daily run of 21 November
2026 its 57 locations were on the map. The same day, checks of eleven other networks' websites in a
browser found no open data route for any of them, and showed that EasyGo is now EZO.

## Go Zero: the feed behind the dashboard

In October Go Zero's open data page answered "page not found" (see [the post on finding the
data](findings/finding-the-data/)). Archived copies of that page, from December 2024 to 5 October
2025, gave a locations address and a tariffs address on an older host, with no key. On 20 November
2026 that host answered "not found" to both.

The footer of Go Zero's home page, read on 20 November 2026, links a public live data dashboard of
its network. The dashboard's own script reads an OCPI 2.2.1 locations address on a newer host, with
no key. The tariffs path from the old page answered on the newer host too, with 57 tariffs. No page
found gives that exact address, so the map marks it as needing testing: if it stops answering, Go
Zero's prices show as unknown.

No terms for the data and no rate limit were found on Go Zero's pages on 20 November 2026. Every
connector links a terms page that answered "not found" that day, and the only terms on Go Zero's
website are for buying its charging units. Under the project owner's standing rule of 10 October
2026 for data with no terms of its own, the data is used under the Open Government Licence, as the
Department for Transport's guidance describes. The map asks the feed two seconds apart: two requests
for the daily fetch and one an hour for statuses.

What the feed sent on 20 and 21 November 2026:

- **57 locations, all new to the map.** Every one gives the OCPI party GB GOZ and a publish flag of
  true, with 158 charge points and 233 connectors. Going by their names as published, 29 are
  hotels, and the others include holiday lodges, campsites, community centres, garden centres,
  offices and a shopping centre. 10 have a DC charger. None appeared in another operator's feed, and 6 were within 200 metres of
  another network's charger on the map.
- **Prices without VAT, VAT stated.** Every price gives a VAT rate of 20 beside a price excluding
  VAT, as OCPI 2.2.1 describes, so the map adds it, and every price then comes to whole pence. On
  21 November 2026, 37 of the 57 locations showed 66p per kWh including VAT, and the others between
  22p and 79p.
- **The same price day and night.** Every tariff gives one price from 06:00 to 22:00 and another
  from 22:00 to 06:00, at the same figure. See [the post on prices that said
  "from"](findings/prices-that-said-from/).
- **An older field name.** Every location gives its parking type under OCPI 2.1.1's name rather
  than OCPI 2.2.1's, so the map shows its parking type as unknown.
- **A few mistyped addresses.** One postcode has a zero where the letter O belongs, one has no
  space, one city also holds the postcode, and one location name starts with a space. Each is shown
  as published; the coordinates, not the postcode, place a location on the map.

## EasyGo is now EZO

EasyGo, a network in Northern Ireland, holds an EV Roam operator id. Its website could not be read
from the cloud on 23 October 2026 because its security certificate check failed. In a browser on 20
November 2026, both of EasyGo's websites had certificates that had expired on 10 May 2026. Read past
the expired date on the owner's instruction that day, with every other check kept, both redirected
to EZO's websites, and EZO's home page, read on 22 October 2026, describes EZO as EasyGo's new name.
EasyGo is now listed only as EZO's former name. EZO's own website offers a request form for its
open data, which passes requests to Eco-Movement; as of 21 November 2026 it has not been sent.

## No data route found

Each of these was checked on its own website in a browser on 20 November 2026. None gave an open
data feed, a feed address, or a page saying how to ask for one.

- **LEAP24.** Its UK website refused an automated read on 23 October 2026, but could be read in a
  browser. It lists about a dozen charging sites, mostly in and around London, with support and
  policy pages and no open data, regulations, OCPI or API page. Its footer gives a support email
  address.
- **Dragon Charging.** The address in EV Roam's register now redirects to an installer's website,
  which links Dragon Charging's own site. That site lists 139 locations, mostly in Pembrokeshire and
  South West Wales, and says its customers can also use Clenergy's chargers. Clenergy EV's feed had
  no point at the Dragon location names checked, so Dragon's sites are very likely not in it
  (inferred).
- **Osprey.** Its only page on the regulations is still a post of 6 December 2023, with no feed
  address or request route. Its website gives a freephone number, an email link and a contact page.
- **Rontec CHARGE.** Rontec runs service stations and has its own charging brand, CHARGE. Its
  charging page and the rest of its website have no open data page, and no location in any feed on
  the map is named Rontec.
- **Alfa Power.** A guide to charging at motorway service areas names it, but the web address the
  guide gives showed a web host's holding page, and another likely address was for sale. No
  website, data route or contact route of its own was found.
- **Connected Kerb.** Its "Regulatory Data" link leads to a reliability report rather than open
  data.
- **Qwello.** Its UK website has no open data page; its parent company's site mentions only the
  EU's rules.
- **TotalEnergies and Source London.** TotalEnergies' UK pages say it bought Source London in 2021,
  and mention the regulations only for a reliability figure. Source London's own website did not
  answer on 10 October or 20 November 2026.
- **Wattif.** Its old address shows a parked page; its own website links only an app and a contact
  page.
- **Joju.** Its charging pages name the councils it works for, but have no open data page.
- **APCOA.** Its pages were unchanged since 23 October 2026, with no open data route.

Each record on the [transparency page](transparency/) now gives the contact route found. The next
step for each is a written request asking where its open data is published. None had been sent by
21 November 2026.

## Two networks already on the map

- **EG On The Move and evpoint.** EG On The Move's website described its own rapid charging brand
  at 70 sites on 20 November 2026. evpoint's feed held 38 locations that day, all named "EG GROUP",
  and evpoint says EG Group's older chargers moved to it, so the two very likely share sites
  (inferred). The difference between 70 and 38 is not explained.
- **Westmorland.** Westmorland's charging page lists six service areas, including both sides of
  Gloucester and of Tebay, and sends drivers to a SWARCO account. All six were on the map from the
  Evolt feed that day.
