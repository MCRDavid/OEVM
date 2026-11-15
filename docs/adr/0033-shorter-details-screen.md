# 0033: A shorter charger details screen

Date: 2026-11-15. Status: accepted by the repository owner on 15 November 2026.

On 15 November 2026 the repository owner said the details screen for a charger was too
wordy, with too much text and too many disclaimers, and asked whether it could be
simplified. A proposal with screenshots before and after was put to the owner, who
accepted it the same day and asked for the price wording to be shortened as well (a
separate change, recorded in ADR 0003). This records what was measured and what changes. It amends ADRs 0023, 0026,
0029, 0030 and 0032, which set some of the wording; each says so.

## What the check showed

The details screen of 15 locations on the live map (13 networks, data fetched 14 November
2026 at 04:17 UTC, statuses read at 23:31 UTC) was read in a 412 by 823 pixel phone
screen. It showed between 287 and 842 words, 7,486 in all, and took up to 5.3 screens of
scrolling (bp pulse, High Street, Milton Keynes: 9 charge points). Most of the length was
repetition rather than notices:

- Each charge point had its own box repeating its plug, power and whole price text, so a
  site with 9 alike posts gave the same 25-word price 9 times. Each box also gave its
  EVSE ID, which the reference numbers at the foot gave again.
- Each part carried its own caveat: the status time ("It may have changed since"), the
  notes ("As the operator published them ... Prices on this page come from tariff data"),
  the cheapest line ("the lowest price per kWh listed here, from the operator's tariff:
  how to pay is not stated. Other charges, such as a fee per session or for staying
  longer, are not included"), the tariff order and the plans (48 words).
- "3 of 4 charge points available" said what the coloured counts said.
- "Where this comes from" and the reference numbers took about a screen.
- Each plan took up to 8 lines, all open, and a "lowest published energy price here with
  any listed plan" line often gave the operator's own tariff again.

## Decisions

- **One box for each kind of charge point.** Charge points with the same connectors,
  power, price, parking rules, card payment, floor level and note share a box, in the
  operator's order. The box gives the connectors (fastest first) and the price once,
  then one line per charge point with its name, its status in its group's colour and
  symbol, and when the operator reported it ("14 Nov, 17:12", with the year only when it
  is not the year the feed was read). Where two charge points in one box share a name,
  each also shows its EVSE ID. Otherwise EVSE IDs are given in the reference numbers.
- **Status:** the coloured counts and "Status from the operator's feed, read <time>."
  The counts in words ("3 of 4 charge points available") stay for screen readers only.
- **Cheapest here:** "Cheapest here: 56p per kWh." with how it is paid for when every
  listed tariff giving that price agrees and the feed says, then "Any other charges are
  not included." With filters on it starts "Cheapest for your filters". The tariff's name
  and the network that published it are in the list of tariffs.
- **The operator's statements in one line:** "The operator says: car park; card payment
  (credit card); floor level 3." It is given once with the site when every charge point
  agrees, otherwise in the box of the charge points it applies to. Parking rules
  likewise ("Parking: customers only.").
- **Opened when asked for:** "All <n> tariffs listed here" (every readable tariff,
  cheapest first, as before), "Other ways to pay here (<n>)" (plans, in the same two
  groups, and the calculator), and "More about this data": when and where the data was
  fetched with its licence link, when statuses were read again, the full note for a copy
  an operator sent, the related operator's tariff feed, that prices come from tariff data
  and not from the operator's notes, the reference numbers, and the operator's own name
  for each tariff that was renamed.
- **One caveat:** "Prices and statuses are as the operator published them, and may have
  changed. Always check at the charger." (or the sent copy's own wording).
- **A plan in view only when it is cheaper** than every tariff listed here: "With a
  listed plan: 55p per kWh including VAT, Gold Member from Fastned (£4.99 a month)."
  Ticked plans the same way, as "With your plans".
- **Kept in view as before:** the attribution statement, Fastned's "Adapted from
  Fastned's data." included (ADR 0028); the operator's notes exactly as published, now
  "As published, and may be out of date."; the private or taxi-only note; a coordinate
  correction; the note where an operator's terms keep its plans off the map (ADR 0016
  wording); "Price unknown" with its reason; the out of service button; the links, now
  "View on OpenStreetMap" and "Report a mistake".
- **Nothing in the data changes.** Detail files, prices and their wording (all from
  `pipeline/pricing.py`) are as before.

## Amendments to earlier decisions

- ADR 0023: charge points are listed by kind, one line each, not one box each; EVSE IDs
  are in the reference numbers unless two charge points in one box share a name.
- ADR 0026: the line in a site's details says how the cheapest price is paid for, but no
  longer names the tariff or the network that published it.
- ADR 0029: the details show a short note in view ("A copy <operator> sent, made <date>
  and not updated since. Charge point status is not shown."); the full note, naming the
  channel, the day it arrived and the owner's decision, is under "More about this data",
  with the link to the files.
- ADR 0030: parking type, card payment and floor level are worded together as the
  operator's statement ("The operator says: ..."); the notes caveat is shorter, and that
  prices come from tariff data is said under "More about this data".
- ADR 0032: that statuses were read again is said under "More about this data"; the time
  under the counts is unchanged.

## Result

Over the same 15 locations the screen shows 2,921 words, 61% fewer, and at most 1.8
phone screens (bp pulse, High Street). Screenshots before and after, in light and dark,
are in the project's files (`details-screen/2026-11-15/`).

Amended 15 November 2026 by ADR 0034: where paying the operator directly is cheaper, a note
saying so, without the price, is kept in view under "Cheapest here".
