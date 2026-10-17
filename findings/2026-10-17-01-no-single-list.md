# Why there is no single open list of the UK's public chargers

Since November 2024 every UK charge point operator has had to publish data about its public
chargers openly. There is still no public list of where each operator publishes it, and the
government buys its own picture of the network from a commercial aggregator. This post sets out
what the rules say, what replaced the national register, and how far this project has got.

## What the rules say

Regulation 10(5) of the
[Public Charge Point Regulations 2023](https://www.legislation.gov.uk/uksi/2023/1168/regulation/10/made)
says:

> "A charge point operator must ensure that reference data and availability data is made
> available to the public free of charge and in a machine readable format without any
> requirement to agree to terms and conditions regarding the use of that data."

[Regulation 2](https://www.legislation.gov.uk/uksi/2023/1168/regulation/2/made) defines the
"data requirement" as "version 2.2.1 of the Open Charge Point Interface protocol" (OCPI).
The Department for Transport's
[guidance on the regulations](https://www.gov.uk/government/publications/the-public-charge-point-regulations-2023-guidance/public-charge-point-regulations-2023-guidance)
(updated 21 October 2024) says "charge point operators must use the Open Charge Point Interface
(OCPI) to hold and open their data" and must "ensure that the required data can be communicated
to anyone who wished to receive it". It calls an application programming interface (API) "the
most widely used method" and asks operators to "consider the burden required with any method that
does not have the potential for automation".

We found nothing in the regulations or the guidance that says where an operator must publish its
data, or that asks it to list the address anywhere. Each operator chooses its own place, and
anyone who wants the data has to find each one.

## What replaced the national register

The National Chargepoint Registry, a public list of charge points run for the government, was
decommissioned on 28 November 2024. The government's
[page about it](https://www.gov.uk/guidance/find-and-use-data-on-public-electric-vehicle-chargepoints),
withdrawn on 2 December 2024, says "All public EV chargepoint operators are now required to share
open data free of charge." It gives no list of where that data is.

The Department for Transport had already said it would not build one for the public. Its
pre-tender notice "EV Open Data - Open Data Provider" (25 October 2024, on Contracts Finder; we
read the
[copy on Stotles](https://www.stotles.com/tenders/2024/W43/ev-open-data-open-data-provider)
because Contracts Finder refused automated reads) says:

> "Given the prevalence of such providers, we do not currently see a need for DfT to build a
> data platform to serve aggregated open data to consumers. There is however a clear need to
> build a solution to enable DfT, regulators and other government departments and agencies to
> use open data effectively."

## The government's contract with Zapmap

Zapmap
[announced on 16 September 2025](https://www.zapmap.com/news/dft-awards-zapmap-contract-deliver-electric-vehicle-chargepoint-open-data)
that the Department for Transport had awarded it a contract under which "Zapmap will aggregate
publicly available data from all public chargepoints in the UK" and provide it to the department
"on a periodic basis". The same announcement says the data "is also available to the rest of the
industry via the Zapmap Insights product suite", which is Zapmap's commercial offer.

[Highways Magazine](https://www.highwaysmagazine.co.uk/news/dft/dft-appoints-zapmap-chargepoint-open-provider)
(29 September 2025), reporting the award letter, says the agreement "initially commenced on
8 December 2024", was "set to run until 8 December 2025", allows "two one-year extensions", and
is worth "up to £1m" with an "initial commitment" of £240,000. We have not read the award notice
itself.

The department's
[methodology note](https://www.gov.uk/government/publications/electric-vehicle-charging-device-statistics-information/electric-vehicle-public-charging-infrastructure-statistics-methodology-note)
for its charging statistics (updated 21 May 2026) says the data is "collated by Zapmap" and that
"Zapmap compile CPO data with coverage of over 95% of the public charging network". So, by the
department's own account, the figures the government relies on do not include every public
charger. The note does not say how that share is measured or which chargers make up the rest.

The project owner reports having asked Zapmap to add public chargers that were missing from its
map, and says they have not been added. We have not checked this ourselves.

## How far this project has got

The daily run on 17 October 2026 mapped 11,471 locations from 12 networks. Zapmap's
[statistics](https://www.zapmap.com/ev-stats/ev-charging-statistics) count 48,298 charging
locations at the end of September 2026. The two are not counted the same way, so this is a rough
comparison only, but most of the network is not yet in data that anyone can collect without
asking first.

The project's register lists 65 networks. This is what getting each one's data takes, as shown
on the [transparency page](transparency/) on 17 October 2026:

| What getting the data takes | Networks |
|---|---|
| Nothing: published with no key | 11 |
| A key printed on the operator's own page | 1 |
| A key or login on request, by form, email or phone | 17 |
| A signed agreement | 2 |
| No route found on the operator's own website | 14 |
| Not known yet: website unreadable, not found or not yet checked | 18 |
| Possibly not public chargers | 2 |

## Our view

This section is the project owner's opinion, not a finding.

The regulations made the data open, but open data that nobody can find is of little use.
Everyone who wants a full picture has to repeat the same search, network by network, or buy the
picture from an aggregator. In the owner's view, when the government buys its picture from one
commercial provider, with no published check that we have found of how complete it is against
operators' own data, while the public has no list of where the data is, new apps, research and
competition in the UK's EV charging market are held back.

Three things would help a great deal, at little cost:

- a public register, kept by the government, of each operator's data address and how to reach it;
- platforms that serve many small operators, such as Monta and Fuuse, publishing one list of
  their customers' data addresses (see [the post on Monta](findings/monta-emailed-export/));
- published enforcement under regulation 10, in the way the enforcement authority says it
  publishes other actions (see [the post on enforcement](findings/reports-and-enforcement/)).
