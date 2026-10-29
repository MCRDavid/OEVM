# Six more networks on the map, and prices that are only on websites

The daily run of 24 October 2026 put six more networks on the map: PLUG Charging, Urban Fox, Globe
EV, BrightGreen, Enfield Council and 3ti, 445 locations between them. Their feeds show the same
quirks as the larger networks' feeds, and one shows every site in two cities as free when its own
website gives a price. Elsewhere, several operators publish prices on their websites but no data
that can be collected. This post sets out what was found on 23 and 24 October 2026.

## On the map since 24 October 2026

Locations mapped in the daily run of 24 October 2026 (04:17 UTC), from the [feed health
page](status/):

| Network | Mapped | How the data is published |
|---|---|---|
| PLUG Charging | 177 | OCPI 2.2.1 API with a free key, sent on registering |
| Urban Fox | 138 | Its own OCPI API, no key |
| Globe EV | 109 | Files on Clenergy's platform, linked from its open data page |
| BrightGreen | 8 | Locations and tariffs files on its own site |
| Enfield Council | 7 | Two Fuuse links on the council's charging page |
| 3ti | 6 | A pair of Fuuse links for each of its sites |

Points worth knowing about each, all recorded with their dates on the [transparency
page](transparency/):

- **Urban Fox** sites also appear in Monta's feed under Urban Fox's party id, with different ids.
  By the project owner's decision, Urban Fox's own feed is shown and Monta's copies are left off:
  95 of them on 24 October 2026.
- **Globe EV** gives no VAT rate. Of its 10 prices per kWh in pounds, 9 come to a whole penny once
  20% is added, the same pattern as Clenergy EV's prices on the same platform. By the owner's
  decision, the map adds VAT at 20% and says so in each price.
- **BrightGreen** listed 15 locations on 23 October 2026: 13 in the UK, 5 of them marked not for
  publishing, and 2 in Slovakia, which are left off. Every charger's status is "idle", which is not
  an OCPI 2.2.1 value, so status shows as unknown. Each tariff also carries a display price, such
  as "£0.59" for a price of 0.59 with VAT at 20%; by the owner's decision the map reads the price as
  including VAT, as the display price shows it. One site with a Milton Keynes postcode is missing
  its longitude's minus sign and is shown in the right place, with a note.
- **Enfield Council**'s page names the two links "In accordance with The Public Charge Point
  Regulations 2023". 30 of its 32 connectors name no tariff, so they show "Price unknown".
- **3ti** publishes one pair of files per site rather than one feed. For one of its six sites, in
  Medway, both addresses answered with no content (HTTP 204) on 23 October 2026, the location
  address twice, so that site is not on the map. Its prices state VAT at 20%, for example 29.17p plus VAT, which is 35p per kWh.

## Free in the feed, priced on the website

127 of Urban Fox's 138 locations, 116 of them in Newport and 9 in Plymouth, name only tariffs whose
energy price is zero and that give no other price (23 October 2026). As published, those sites
would read as free. Urban Fox's own website, read in a browser on 23 October 2026, gives "30 - 40p/kWh"
on every Newport charger's page and 43 to 50p per kWh in Plymouth. The map shows these sites as
"Price unknown" rather than "Free", by the owner's decision, and keeps the tariffs as published.
Every Urban Fox tariff also states VAT as 0.

## Prices on websites, but no data

Pages read in a browser on 23 October 2026 give prices that no open data we have found carries:

- **APCOA**: 73 of the 99 car park pages listed on its [charging
  pages](https://www.apcoa.co.uk/ev-charging-services/electric-vehicle-charging/electric-vehicle-charging)
  give a price per kWh, from 34p to 80p; three of them write "per kW". Many are railway station car
  parks. None of the pages links any data.
- **Whitnash Town Council**: two 22 kW chargers "at an introductory price of £0.50/kWh", paid
  through Monta's app.
- **East Riding of Yorkshire Council**: "The council has introduced a tariff for all its electric
  vehicle chargers. The cost has been set in line with the national average at £0.48 per kWh."

The map takes prices only from the operators' published data, so none of these is on it.

## An API that cannot feed a map

Believ's API documentation, read on 23 October 2026, describes one endpoint, which returns a single
charger by the label printed on it, limited to 100 calls per 24 hours. It gives no way to list
locations or chargers, so the project cannot find Believ's chargers through it, and Believ stays
off the map. In the one charger read that day, the address field held "GB" rather than a street
address.

## More networks with no route

Of the operator ids in the EV Roam register described in [the post on small
networks](findings/small-networks/), 15 more networks were recorded on 23 October 2026. 11 show no
data route on their own websites, 3 websites could not be read, and one may not be a charge point
operator in scope. An id costs money: EV Roam's [terms and
fees](https://www.evroam.org.uk/_files/ugd/ba22eb_43b30095ded54d7584b30b0f6ee690bc.pdf) (version
EVROAM.TC.050922.v1) ask "a one-off registration fee of £100" and "an annual fee of £250 for every
unique ID", and say "All fees are shown exclusive of VAT".

Some networks turn out to sit inside others. Joju says its chargers run "on the Mer network", but
Mer UK's feed, checked on 23 October 2026, names no Joju site and has none in Portsmouth or
Eastleigh, where Joju runs public chargers. Elmtronics' website did not load, and Mer's own [news
page](https://uk.mer.eco/news/mer-acquires-elmtronics-expandong-its-uk-ev-charging-business/) of 5
January 2022 says Mer Fleet Services Ltd acquired Elmtronics.

## Requests sent

On 23 October 2026 the project sent its first 16 access requests, each through the operator's own
web form; several of those forms pass requests to Eco-Movement. None had been answered by 24
October 2026. Each request and reply is listed with its date on the [transparency
page](transparency/).

**Update, 29 October 2026:** Fastned sent a key on 24 October 2026, Roam and Connekt replied on 26
October 2026, and Eco-Movement sent tokens for 13 networks the same day. See [the post on three
requests answered](findings/three-requests-answered/) and [the post on Eco-Movement's
networks](findings/eco-movement-networks/).
