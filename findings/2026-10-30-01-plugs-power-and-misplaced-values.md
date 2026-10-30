# Plugs that disagree with their power, and other values in the wrong place

On 30 October 2026, while working out how the map could show AC and DC charging apart, the
project compared each connector's plug with the power type and power its feed gives. Almost all
agree. Six connectors at four sites give a power type that does not match their plug, seven sites give
Type 2 connectors more AC power than such a connector normally takes, and Blink Charging gives
voltages that make some of its chargers look faster than they probably are. Other feeds put the
start of a name in the floor level field, and the operators' own notes, now shown in site details,
include an old price and sites said to be not for public use.

## Power type against plug

OCPI 2.2.1 gives each connector a standard, which is the plug, and a power type: AC on one, two or
three phases, or DC. CCS and CHAdeMO connectors are for DC charging, and Type 2 connectors are
normally for AC.

A check of 1,253 location files from the map of 30 October 2026 found the power type agreeing with
the plug on 3,755 of the 3,761 connectors where both were known. The project then checked the raw
feed pages it kept from 29 and 30 October 2026 and the two emailed copies, 42,185 connectors with
both a plug and a power type from 38 networks (for some networks only the first page), and found
the same six and no others:

| Network | Site | Connectors | Power type given |
|---|---|---|---|
| Connekt (emailed copy of 26 October 2026) | Boyndie Visitor Centre | 2 Type 2 sockets | DC, 40 kW |
| Evolt Network | Elm Street Car Park, Ipswich | 1 CCS and 1 CHAdeMO socket | AC, one phase, 7 kW |
| ScottishPower Recharge | Storage Vault - Hamilton | 1 Type 2 cable | DC, 50 kW |
| ChargePoint | EVPOINT SBX KETTERING | 1 Type 2 socket | DC, 22 kW |

Whether the plug or the power type is wrong in each case is unknown and needs confirming by the
network. The map shows each connector's power as the feed gives it, so the Ipswich site shows as a
7 kW site.

## More AC power than a Type 2 connector normally takes

Most Type 2 connectors give AC at up to 22 kW, and some rapid chargers give up to 43 kW AC through
a Type 2 cable. Across the whole map on 30 October 2026, seven sites gave a Type 2 connector marked
as AC well over that, from 46 to 200 kW:

| Network | Site | Type 2 connectors | What the feed gives |
|---|---|---|---|
| PoGo Charge | Merkland Drive Kirkintilloch Glasgow, and Hamilton Int Park | 2 sockets at each | AC, three phases, 415 V, 278 A, 200 kW, the same 200 kW as each site's CCS sockets |
| Aldi Stores Limited | Aldi - Sheffield - Brimington | 2 cables on a charger whose id ends "DC01" | AC, three phases, 1,000 V, 160 A, 160 kW |
| ChargePlace Scotland | Whitburn Swimming Pool, West Main Street, Whitburn | 2 sockets | AC, three phases, 415 V, 70 A, 50 kW |
| Evolt Network | Ardgay Regeneration, Drovers Square, Ardgay | 2 sockets | AC, three phases, 415 V, 70 A, 50 kW |
| Blink Charging | Manzil Way, Oxford | 2 sockets | AC, three phases, 400 V, 63 A, no power figure |
| Blink Charging | Leisure Centre Car Park, Hartlepool | 2 sockets | AC, three phases, 240 V, 64 A, no power figure |

The map shows power as the feed gives it, or works it out from voltage and current where the feed
gives none, so these sites show as rapid or ultra-rapid chargers. At the Aldi site the charger's id
and the 1,000 volts suggest a DC charger given the wrong plug and power type; that is inferred and
needs confirming by the network.

## Voltage between lines

OCPI 2.2.1 gives the maximum voltage of a three-phase AC connector line to neutral, about 230 volts
in the UK, so its power is voltage times current times three. Blink Charging gives every
connector's maximum power as 0 watts (see [the post on Eco-Movement's
networks](findings/eco-movement-networks/)), so the map works out its power from voltage and
current.

In Blink's feed of 29 October 2026, 384 of its 3,493 AC connectors, at 74 of its 875 locations,
give 400 volts, the voltage between two lines of a UK three-phase supply, and 288 of them say they
are single phase. A 32 amp single-phase socket at 400 volts works out at 12.8 kW, where 230 volts
gives 7.4 kW, and a 32 amp three-phase socket works out at 38.4 kW, where 230 volts gives 22 kW. On
30 October 2026, 41 Blink locations showed 12.8 kW as their fastest connector and 20 showed 38.4 kW.
The map shows what the feed gives, read as OCPI 2.2.1 defines it; that 7.4 and 22 kW are meant is
inferred and needs confirming by Blink.

Several other feeds also give voltages well above 230 on AC connectors, among them ChargePlace
Scotland, Evolt Network, ChargePoint and RAW Charging, but they give a power figure for almost all
of them, which the map uses instead.

## Floor levels that hold names

OCPI 2.2.1 gives each charge point an optional floor level of up to four characters, for the level
in a car park on which it stands. MFG EV Power's feed of 30 October 2026 gives "MFG " for 2,375 of
its 3,034 charge points and "Morr" for 616 of them, and Allego's of 29 October 2026 gives "Alle" for
158 of its 240 and "GB, " for 80. These look like the start of a name or an address, cut to four
characters (inferred). ChargePoint and RAW Charging send a mix, such as "-2" and "1" alongside "T2",
"A" and "B&Q". On 30 October 2026 the project owner decided to show floor levels in site details as
published, except MFG's and Allego's.

## Parking restrictions sent as text, now read

Five networks on Eco-Movement's platform, Allego, Lidl, ubitricity, Travis Perkins and drax-Ista,
send parking restrictions as one piece of text, such as "customers" or "ev_only,plugged", where
OCPI 2.2.1 has a list. The words are OCPI 2.2.1's own values, so from 30 October 2026 the project
reads them as that list and logs each one. In that day's run they covered 2,462 charge points,
among them all 1,408 of Lidl's, which say "customers". Any other word is still ignored.

## The operators' own notes

From 30 October 2026 site details show each operator's notes (OCPI 2.2.1's directions) as
published, said to be the operator's words that may be out of date, with prices taken only from
tariff data. In the feeds recorded on 29 October 2026:

- At 9 of Pod's first 1,000 locations the notes say "from the 4th March, this unit will become a
  paid service at 60p per kWh", with no year, and give Covid's effect on rail revenue as the reason.
  The tariff their connectors name gives 50p per kWh, read as including VAT by the owner's
  decision.
- At 6 of Pod's first 1,000 locations the notes say the chargers are not for public use, such as
  "Private workplace only, chargers not for public use." The map hides a location as private only
  by phrases in its name, so on 30 October 2026 these six were shown, with their notes.
- 183 of RAW Charging's 514 locations have the note "3$0 - Hospitality" and 46 have
  "3$0 - Leisure", which look like internal categories (inferred).
