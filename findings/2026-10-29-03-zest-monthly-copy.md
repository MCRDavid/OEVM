# Zest's data: a copy by email, to be asked for again each month

Zest offers its open data through a request form. Its reply to the project's request of 23 October
2026 came on 28 October 2026: two files attached to an email, made on 26 October, and a request to
fill in the form again each month for a newer copy. Like Connekt's, the copy is now on the map,
dated and with every charger's status unknown. The files repeat 42 locations, give one idle fee per
hour where the tariff's own words say per minute, and carry web page markup in their tariff
descriptions.

## How the data comes

Zest's [open data page](https://www.zest.uk.com/charge-point-open-data) offers the data "as per the
Public Charge Point Regulations 2023" through a request form, and says "Use of this data is licensed
under CC BY 4.0." (read 10 and 29 October 2026). The project used the form on 23 October 2026. The
reply of 28 October 2026 attached two OCPI 2.2.1 files, one for locations and one for tariffs, with
no web address or key, and said:

> Please find the OCPI Data request documents attached. We are currently working hard behind the
> scenes to implement automation for this process. In the meantime, please complete the form
> monthly to ensure we have an updated snapshot of the necessary information.

On 29 October 2026 the project owner decided to show the copy on the map, as for Connekt's (see
[the post on three requests answered](findings/three-requests-answered/)). It is dated when Zest
made it, 26 October 2026 at 10:29 UTC, every charger's status shows as unknown, and each location
says it comes from a copy that is not updated. Each newer copy Zest sends will replace it, and a
feed will replace both if Zest publishes one. The project is asking Zest for an address it can
fetch automatically. CC BY 4.0 asks for a note when data is changed, so the map says Zest's data is
adapted.

## What the copy holds

The locations file has 2,005 records for 1,963 locations: 42 location ids appear twice, and in each
pair the later record has the newer last updated time. The map keeps the later one, as for any feed
that repeats a record.

Tariffs 93 and 530, named by 620 connectors, give an idle fee as a parking time price of 0.08 pounds
before VAT. OCPI 2.2.1 defines that price per hour, while the tariffs' own text says "£0.10/min after
4 hours not charging". 0.08 plus VAT at 20% comes to about 10p, the figure in the text, so the two
may differ only in the unit; which is meant needs confirming by Zest. The map shows the price as the
data gives it, about £0.10 per hour parked including VAT, and shows Zest's own text with the tariff.

64 of the 67 tariffs give their description with web page markup, such as div, br and strong tags.
OCPI 2.2.1 says such text is "Text to be displayed to a end user. No markup, html etc. allowed."
The map shows each description as text only, with the tags taken out.

One tariff, 18, gives an energy price of 8.33 pounds per kWh before VAT. No connector in the copy
names it, so it is not shown.
