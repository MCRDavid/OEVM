# Monta: open data by emailed export, one site owner at a time

Monta provides the software behind many small charging sites in the UK, such as hotels, holiday
parks, councils and leisure centres. Its help page tells each operator on Monta to export its
open data as a file sent by email, fill in nine fields by hand, and publish it. We found no UK
network on Monta that publishes the result where it can be collected. Monta's developer pages
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
in one export", and that the export "currently covers 40 of the 49 fields" the regulations ask
for. The nine fields left to fill in by hand are related_locations, parking_type, directions,
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
Each one would then have to export its own file, complete it and publish it somewhere.

The pages we read on 17 October 2026 show what that looks like. Cinderford Town Council's
[charging page](https://cinderfordtowncouncil.gov.uk/community/electric-vehicle-charging-points)
(four chargers) says "Payment is through the Monta app". The Northern Ireland Assembly's
[visitor page](https://www.niassembly.gov.uk/visit-and-learning/planning-your-visit/electric-charging-points)
(two chargers) asks drivers to download the Monta application. Neither page links any open data.
The larger networks on Monta that we know of are evyve, which moved to Monta in January 2026 and
still takes data requests through a form shared with another company, Eco-Movement, and Home and
Business Charging, whose own website we have not yet been able to confirm.

## Why this is hard to use

The guidance asks operators to "consider the burden required with any method that does not have
the potential for automation". A file emailed to each operator, completed by hand and posted
wherever each one chooses can only be collected if every one of them puts it at a fixed address
and says where. On 17 October 2026 we found none that had.

## Monta's developer pages

Monta's [Public API documentation](https://docs.public-api.monta.com/reference/get-open-data-locations)
(updated 28 April 2026) lists an "Open Data" section, "List UK charge points in OCPI 2.2.1
Location format", described as "Intended for AFIR-style aggregators and government open-data
consumers". The documentation says it needs an access token from an application registered in
Monta's portal. It does not say who may register one, or set out terms or rate limits for it.
The help page above does not mention it. We have not used this feed; whether it can serve as a
public source for Monta's UK chargers needs testing and, we think, a question to Monta.

## Fuuse: links for each customer, published by each customer

Fuuse, another back office provider, counted 2,799 chargers at 722 locations in Zapmap's
[guide to Fuuse](https://www.zapmap.com/ev-guides/public-charging-point-networks/fuuse) (end of
September 2026). Fuuse gives each customer two data links, but its
[help centre](https://support.fuuse.io/hc/en-gb/articles/4696535102239-Open-Data-Access-ODA-Links-Overview)
(read 17 October 2026) says "Fuuse has no obligation to provide ODA data to members of the
public - it is up to the CPOs to make this available to their customers via their website". Each link
contains an account number that cannot be guessed, so the customer's own website is the only way
to find it.

So far we have found the links for two Fuuse customers: Arnold Clark Charge, in its website
footer, and ScottishPower Recharge, in a blog post. Together they cover 191 of Fuuse's 722
locations. Other networks known to run on Fuuse, such as Be.EV, Charge My Street and WattStop
(which took over the City of Edinburgh Council's public chargers in March 2026), link no data
on the pages we read on 17 October 2026.

## What would help

If Monta and Fuuse each published, or hosted, one list of their UK customers' data addresses,
thousands of chargers could be collected at once, and each small site owner would not have to
work out how to publish a file on its own. The project has not asked either company yet; any
request will be listed on the [transparency page](transparency/).
