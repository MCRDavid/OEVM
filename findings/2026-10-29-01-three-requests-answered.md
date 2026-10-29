# Three requests answered: Fastned's key, Roam's feed and Connekt's emailed copy

Three operators the project asked on 24 October 2026 have given it their data, each in a different
way. Fastned sent a key minutes after its form was filled in. Roam replied by email on 26 October
2026 with two addresses that need no key; its feed uses an older version of OCPI, allows five
requests an hour and gives two connectors the same id at ten sites, which are left off the map.
Connekt also replied on 26 October 2026, with its data attached to an email and no address to fetch
it from. This post sets out what we found in each.

## Fastned: a key within minutes

Fastned's [UK Open Data page](https://www.fastnedcharging.com/en-gb/uk-open-data) is its Fair Use
Policy for the data, followed by a form. The project filled in the form on 24 October 2026,
agreeing to the policy, and Fastned's automated email sent a key minutes later, with addresses for
OCPI 2.2.1 locations and tariffs. A first read that day took two requests and returned 42 locations and one tariff.

The policy says "Fastned retains all rights, title and interest in both the Data and the API" and
gives access "under a limited, non-exclusive, non-transferable, and revocable license for permitted
use as outlined in this Policy". It asks anyone who adapts the data to "acknowledge that Fastned's
source Data has been adapted". The project owner decided on 24 October 2026 to agree to the policy
and follow its attribution rules, so the map says the data is adapted from Fastned's. The policy
states no number for a rate limit: "Fastned may throttle your use of the APIs at any time." The map
reads the feed once a day.

Two points in the data of 24 October 2026:

- 38 of the 309 chargers, at 9 of the 42 locations, are marked REMOVED. They are the only ones with
  no EVSE id, which OCPI 2.2.1 allows. No location has every charger removed.
- One site in King's Lynn gives the postcode "LE34 3LW", while King's Lynn postcodes begin PE. The
  map places it by its coordinates, which are in King's Lynn, and shows the postcode as published.

## Roam: two addresses by email

We found no open data page on [Roam's website](https://www.roamcharging.com/) on 10 October 2026,
so on 24 October 2026 the project asked through its contact form. Roam's reply of 26 October 2026
gave a locations address and a tariffs address on data.evc.ninja (Roam [was called
EVC](https://www.roamcharging.com/news/evc-is-now-roam) until November 2024). Neither needs a key,
and neither the reply nor Roam's website states any terms for the data. Read once on 26 October
2026, they held 438 locations and 728 tariffs, all in pounds.

### Five requests an hour

No limit is stated in the reply or on the website, but the locations address answers with the
header "ratelimit-policy: 5;w=3600": 5 requests in each 3,600 seconds. The map keeps 721 seconds
between requests to the host, so its daily read of the two addresses takes about 12 minutes.

### An older version of OCPI

The records come in OCPI response objects but use OCPI 2.1.1 field names. Locations give type
rather than parking_type, and connectors give one tariff_id, voltage and amperage rather than
tariff_ids, max_voltage and max_amperage. No record gives a country code or party id. The map's
reader gives each field its OCPI 2.2.1 name, which has the same meaning, and takes GB and EVC from
the chargers' EVSE ids.

Each connector also carries its own id, EVSE id and status, which OCPI does not define for
connectors. Each charger's status matches its first connector's. Of the 1,039 chargers with two
connectors, the two connectors' statuses differed in 212 on 26 October 2026. The map shows each
charger's status as sent.

No location has a publish flag, which OCPI 2.2.1 requires (none of 438). Because Roam gave the
addresses as its open data under the regulations, the project owner decided on 26 October 2026 that
these locations may be shown. A flag set to false would still be respected.

### Ten sites left off

In 12 chargers at 10 locations, both connectors have the id 1. OCPI 2.2.1 requires connector ids to
differ within a charger, so, as with any feed, those 10 locations are not shown, and each is named
on the [feed health page](status/). They include, as Roam names them, "Hilton T5 Area B Heathrow
Airport", "Hilton T5 Area C Heathrow Airport", "Northwood Park" and "The Queen Elizabeth Hospital
Kings Lynn" (26 October 2026). Five other locations list no chargers at all and are shown as
published.

### Prices without VAT

Roam's tariffs give no VAT rate. On 26 October 2026 the most common price for AC connectors was
0.45 pounds per kWh (1,199 of 1,963). Roam's [membership
guide](https://www.roamcharging.com/help-and-advice/resources/is-signing-up-for-a-roam-membership-worth-it)
says pay-as-you-go prices "most commonly will be 54p per kWh for fast charging (22kW and below) and
66p per kWh for rapid charging", and 0.45 plus VAT at 20% is 54p. The most common DC price, 0.58
(150 of 213), comes to about 70p with VAT rather than 66p, so the guide may be older than the
tariffs. That the feed's prices leave out VAT is inferred from these figures; Roam does not say so.
By the owner's decision the map adds VAT at 20%, so 45p shows as 54p, and each price says the
project added it.

One connector at Norwood Hall Hotel, whose name in the feed reads "Schnieder French Test charger 2",
names a tariff called free_tariff, whose only price is a fixed fee of 0. Its status was UNKNOWN on
26 October 2026. It is shown as published, so the map lists it as free.

## Connekt: the data as an email attachment

Connekt offers its data under the regulations through a request form on its [Public Charge Point
Regulations page](https://www.connektcharging.com/public-charge-point-regulations), which we found
on 24 October 2026 and used the same day. Connekt replied by email on 26 October 2026 with two
attached OCPI 2.2.1 responses, one for locations and one for tariffs, made at 14:22 UTC that day.
The reply gave no web address and no key. The project is asking Connekt for an address it can fetch
automatically.

Regulation 10(5) asks for the data to be "made available to the public free of charge and in a
machine readable format". It does not name an API or a live feed. The Department for Transport's
guidance (updated 21 October 2024) calls an API "the most widely used method" and says "Other
methods may be feasible".

The emailed copy holds 362 locations under the party id GB CON, all marked for publishing and all
inside the UK, with 1,048 chargers of one connector each. Its 326 tariffs are all in pounds, each a
fixed fee plus a price per kWh, with VAT stated as 20%. 4 connectors name no tariff. In the city
field, 15 locations give "undefined" and 18 give "Scotland", and 145 addresses repeat the postcode
that is also in its own field.

A copy sent once does not change, so on 29 October 2026 the project owner decided to show it on
the map as an exception to the rule that no data on the map is more than 7 days old. Each location
says it comes from a copy Connekt sent, made on 26 October 2026 and not updated, and every
charger's status shows as unknown, because a status from that day says nothing about now. The
[feed health page](status/) shows Connekt in yellow as not fetched. The two files are kept exactly
as sent, gzipped, with their SHA-256 hashes, so anyone can check them.
