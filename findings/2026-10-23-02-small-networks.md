# Finding small networks: an operator id register, platform addresses and a key that came at once

Searching the web for "OCPI" or "AFIR" finds few of the UK's smaller charging networks. On 23
October 2026 we found three more networks whose data anyone can collect, not through a search engine
but by working through the UK register of operator ids and the addresses that charging software
platforms give their customers. Another network sent a key within minutes of asking. This post sets
out the routes that worked and the ones that do not reach the UK.

## What a published feed has to look like

Regulation 10(5) of the [Public Charge Point Regulations
2023](https://www.legislation.gov.uk/uksi/2023/1168/regulation/10/made) asks for the data to be
available "in a machine readable format" (quoted in full in [the first
post](findings/no-single-list/)). OCPI 2.2.1 is how operators must hold the data, but the regulations
do not say the published copy must be OCPI. A feed can be plain JSON, CSV or a spreadsheet, and it
can be published by a site owner, such as a council, rather than under a network's brand. So
searching only for "OCPI" can miss it.

Two more points matter for small networks. [Regulation
4(1)](https://www.legislation.gov.uk/uksi/2023/1168/regulation/4/made) says "Regulations 5 to 10
apply to a charge point operator that is not a micro business", so the smallest owners have no duty
under regulation 10 to publish at all. And [regulation
1(2)](https://www.legislation.gov.uk/uksi/2023/1168/regulation/1/made) says "These Regulations
extend to England and Wales, Scotland and Northern Ireland".

## AFIR and DATEX II do not reach Great Britain

The EU's Alternative Fuels Infrastructure Regulation (AFIR, Regulation (EU) 2023/1804) has operators
in EU member states give their data to a national access point, often in the DATEX II format. Great
Britain has no such access point (see [the first post](findings/no-single-list/) on what replaced
the national register). Searches for "AFIR", "National Access Point" and "DATEX II" found no UK
feed. Monta's AFIR endpoints, for example, accept only Denmark and Belgium (see [the post on
Monta's feed](findings/monta-feed-and-prices/)). Whether AFIR also applies in Northern Ireland is
unknown to us; the UK regulations cover it either way.

## The register of operator ids

[EV Roam](https://www.evroam.org.uk/), run by Renewable Energy Assurance Limited, issues the GB and
IE operator ids that OCPI party ids are built from, and publishes its register. Read on 23 October
2026, it had 123 entries, 100 of them with an operator (CPO) id. Registering is voluntary, so the
register is not complete: char.gy, MFG EV Power, Tesla and Ionity, for example, are not in it.

About half of the operator ids matched a network already in our register. We read the website of
each of the rest. That found the feeds below, one more request form ([Drax Energy
Solutions](https://energy.drax.com/drax-network-of-public-chargers/), whose form says requests are shared with Eco-Movement, as for bp pulse, Shell Recharge and Ionity), and
about 15 networks that look public but show no data route on their own sites.

## Platform addresses

Many small networks publish through an address on their software platform rather than their own:
Fuuse, Clenergy, SWARCO's smartcharging.uk, Hubeleon and Monta all do this. The platforms publish no
index of these addresses, and search engines do not list them. Public certificate transparency logs,
which record the web addresses that security certificates are issued for, show the names a platform
uses for its customers. We treat such a name only as a lead: an address goes into the register only
when the operator's own page, or a reply from the operator, names it.

## Feeds named on the operators' own pages

Found on 23 October 2026, each called once to see that it answers:

| Network | What its own page links | First look |
|---|---|---|
| [Urban Fox](https://urbanfox.network/public-charge-point-regulations-data-access/) | Its own open data API: "Our OCPI-compliant open data API is publicly available ... without needing to request access" | 138 locations; many of the same sites are in Monta's list |
| [Globe EV](https://globeev.co.uk/open-data/) | An address on Clenergy's platform, from its open data page | 109 locations, none already on the map |
| [Bright.Green Energy](https://bright.green/open-data/) | Locations and tariffs files on its "Public Charge Point Regulation Data" page | 15 locations: 13 marked GB, 2 in Slovakia |
| [3ti Energy Hubs](https://3ti.co.uk/3ti-public-charge-points/) | Fuuse addresses for six sites, used by its own live status page | Not read yet |

None of them is on the map yet. Each needs its terms read and an entry in the register first, and
Urban Fox's own feed and Monta's copy of the same sites must not both be shown.

## Car parks

Some car park companies run charging under their own name. On 11 October 2026 we read the websites
of the UK's larger car park operators. Three present the chargers in their car parks as their own:
[APCOA](https://www.apcoa.co.uk/ev-charging-services/electric-vehicle-charging/electric-vehicle-charging)
(APCOA Connect), [CitiPark](https://www.citipark.co.uk/), through its subsidiary CitiCharge, and
[Saba Parking UK](https://www.sabaparking.co.uk/en/electric-charging-points), formerly Indigo. None
of the three links any open data on the pages we read. Others host chargers run by networks already
in the register: Q-Park says it "partners with Blink Charging", and NCP's car parks have Roam, Be.EV
and bp pulse chargers.

## A key that came at once: PLUG Charging

PLUG Charging's [open data page](https://plugcharging.co.uk/open-data) offers an OCPI 2.2.1 API with
locations, live availability and tariffs. A key is free and is emailed after registering with a
name, email address and website. The project registered on 23 October 2026, and the key arrived
straight away. The page says "The data published through this API is made available under the Open
Government Licence v3.0" and "Each key can make 120 requests a minute", and its API access terms say
"These terms govern access to the API only. They do not restrict how you use the data."

A first read on 23 October 2026 took two requests and returned 177 locations, all in the UK, with
478 of their 485 connectors linked to a tariff in the feed. It is not on the map yet.

Our view: PLUG Charging's page answers every question this project has had to ask other operators,
on licence, rate limit and how to get access, in one place.

## The words operators use

Operators rarely put "OCPI" in a page title. The words on the pages where we found data or request
forms, between 9 and 23 October 2026, include "Public Charge Point Regulation Data", "Public Charge
Point Regulations data access", "PCPR Data Requests", "PCPR RFI Files", "Open Data Request", "request
compliance data", "Charge Point Open Data", "UK Open Data", "Open Access Location Data", "live charge
point data" and "public feed". Addresses that keep turning up end in /open-data/, /opendata/,
/public-charge-point-regulations/, /pcpr/ or /developers.

Working from a list of who exists, such as the EV Roam register and the platforms' customer names,
and reading each operator's own site for those words, found more than any search term did. None of
the three new feeds showed up in a web search.
