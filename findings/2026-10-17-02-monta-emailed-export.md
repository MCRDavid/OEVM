# Monta: open data by emailed export, one site owner at a time

Monta provides the charging software used by many UK site owners, from businesses to a town
council and the Northern Ireland Assembly. Its help page tells each operator on Monta to export its
open data as a file sent by email, fill in nine fields by hand, and publish it. Of the Monta sites
whose pages we could read, we found none that publishes the result where it can be collected. Monta's developer pages
also describe a UK data feed, but say it needs an access token.

## What Monta's help page says

Monta's help page
"[How do I export open data for my charge points?](https://monta.com/help/en_US/monta-hub-reporting-compliance-data-exports-third-party-publishing/export-open-data-charge-points)"
(read 17 October 2026) gives these steps in Monta Hub, its back office for operators:

1. "Log in to Monta Hub."
2. "Navigate to Charge Points."
3. "Click Export."
4. "For Export type, select Open data."
5. "Click Export. The report is generated and emailed to you once ready."
6. "Download the file and fill in the 9 fields that require manual input before publishing."

The page says "Open data is exported for your whole operator, covering all of your charge points
in one export", and that the export "currently covers 40 of the 49 fields" that, by Monta's
count, the regulations ask for. The nine fields left to fill in by hand are related_locations, parking_type, directions,
facilities, images, time_zone, opening_times, energy_mix and floor_level. The page does not give
the file's format, and does not say where the finished file should be published.

## Who has to publish it

The regulations define a charge point operator as "the owner of a charge point or any person
operating a charge point on behalf of the owner"
([regulation 2](https://www.legislation.gov.uk/uksi/2023/1168/regulation/2/made)). The
Department for Transport's
[guidance](https://www.gov.uk/government/publications/the-public-charge-point-regulations-2023-guidance/public-charge-point-regulations-2023-guidance)
adds: "The 'operator' is the entity controlling the functioning of the charge point. Where there
are multiple parties responsible for distinct aspects of the charge point, such as branding,
software or maintenance, the body responsible for controlling the functioning of the charge point
would be considered the operator."

Zapmap's [guide to Monta](https://www.zapmap.com/ev-guides/public-charging-point-networks/monta)
says "Monta provides the software rather than the physical hardware" and counted 1,441 public
chargers at 390 locations on Monta at the end of September 2026. On our reading, which is not
legal advice, the operator of many of those chargers is the business or council that owns them.
Monta's help page describes one way for each of them to make the data available: export its own
file, complete it and publish it.

The pages we read on 17 October 2026 show what that looks like. Cinderford Town Council's
[charging page](https://cinderfordtowncouncil.gov.uk/community/electric-vehicle-charging-points)
(four chargers) says "Payment is through the Monta app". The Northern Ireland Assembly's
[visitor page](https://www.niassembly.gov.uk/visit-and-learning/planning-your-visit/electric-charging-points)
(two chargers) asks drivers to download the Monta application. Neither page links any open data.
Both are pages for drivers, so that does not show whether the data is published elsewhere, for
example through Monta (see below). Whether any operator meets the regulations is for the
enforcement authority to decide.
The larger networks on Monta that we know of are evyve, which announced in January 2026 that it
had selected Monta and still takes data requests through a form shared with another company, Eco-Movement, and Home and
Business Charging, whose own website we have not yet been able to confirm.

## Why this is hard to use

The guidance names an API as the most widely used method and says "Other methods may be
feasible", but asks operators to "consider the burden required with any method that does not
have the potential for automation". Unless
Monta's own feed (below) covers them, a file emailed to each operator and completed by hand can
only be collected once each operator puts it at a fixed address and says where. Of the Monta
sites whose pages we could read on 17 October 2026, we found none that had.

## Monta's developer pages

Monta's [Public API documentation](https://docs.public-api.monta.com/reference/get-open-data-locations)
(updated 28 April 2026) lists an "Open Data" section, "List UK charge points in OCPI 2.2.1
Location format", described as "Intended for AFIR-style aggregators and government open-data
consumers". The documentation says it needs an access token from an application registered in
Monta's portal and explains how a signed-in Monta user creates one. Its
[Integration Notes](https://docs.public-api.monta.com/reference/integration-notes) (updated
9 September 2025) give a general limit for Monta's API of "10 requests per minute across all
applications of a single user", without saying which endpoints it covers. It does not
say whether someone who is not a Monta customer may use this endpoint, and sets out no terms or
licence for the data. The help page above does not mention it. The project does not collect data
from this feed; whether it can serve as a public source for Monta's UK chargers is, we think, a
question to put to Monta first.

## Fuuse: links for each customer, published by each customer

Zapmap's [guide to Fuuse](https://www.zapmap.com/ev-guides/public-charging-point-networks/fuuse),
another back office provider, counted 2,799 chargers at 722 locations on Fuuse at the end of
September 2026. Fuuse gives each customer two data links, but its
[help centre](https://support.fuuse.io/hc/en-gb/articles/4696535102239-Open-Data-Access-ODA-Links-Overview)
(read 17 October 2026) says "Fuuse has no obligation to provide ODA data to members of the
public - it is up to the CPOs to make this available to their customers via their website". Each link
contains a long random identifier, so in practice it can only be found where the customer
publishes or shares it.

So far we have found the links for two Fuuse customers: Arnold Clark Charge, in its website
footer, and ScottishPower Recharge, in a blog post. Their two feeds held 191 locations between
them on 17 October 2026. Zapmap lists both as networks of their own, so they are probably not
among the 722 locations in its Fuuse guide. Be.EV and Charge My Street, which also run on Fuuse,
and Fuuse's own network WattStop (to which the City of Edinburgh Council began moving its public
chargers in March 2026; the council says most have moved), link no data on the pages we read on
17 October 2026.

## What would help

If Monta and Fuuse each published, or hosted, one list of their UK customers' data addresses,
thousands of chargers could be collected at once, and each small site owner would not have to
work out how to publish a file on its own. The project has not asked either company yet; any
request will be listed on the [transparency page](transparency/).
