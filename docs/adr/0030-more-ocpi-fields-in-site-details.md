# 0030: More OCPI fields in site details

Date: 2026-10-30. Status: accepted.

A survey of 45 networks on 30 October 2026 (saved feed samples, and one page from each
of 16 no-key feeds fetched that morning) found that feeds send fields drivers would use
that the normaliser (`adapters/ocpi_221/normalise.py`) dropped. The owner chose on 30
October 2026 to add five of them, each in its own pull request:

1. Parking restrictions sent as one string, such as "ev_only,plugged", read as the OCPI
   2.2.1 list they name (PR #106; no new field).
2. The operator's notes, from OCPI 2.2.1 `directions`.
3. Card payment at the charger, from OCPI 2.2.1 `capabilities`.
4. The kind of parking, from OCPI 2.2.1 `parking_type`.
5. BrightGreen's plug types and statuses, from fields outside OCPI 2.2.1, by the owner's
   decision recorded in its operator file.
6. The floor level, from OCPI 2.2.1 `floor_level`, added by the owner on 30 October 2026,
   except for operators whose values the owner decided are not levels.

Parts 5 and 6 are added to this record by the pull requests that build them.

Fields the survey found and the owner did not choose stay dropped: images (visitors'
browsers would fetch them from the operator's storage), green energy claims, the owner
of a site (it can name a private individual), and fields that only repeat a standard one.

## Decisions

- **The operator's notes are shown as published.** OCPI 2.2.1 `directions` ("human-readable
  directions") is a list of texts in different languages, on a location and on each EVSE.
  The English text is kept (the first text when none is English), with spaces at either
  end removed; an empty text counts as none. In the 30 October survey it held parking
  rules, car park hours and access notes: Pod 593 of its first 1,000 sites ("EV charging is
  only permitted during the car parks specified opening hours, parking charges may
  apply"), GeniePoint 126 of 300 sites and 576 of 1,125 charge points ("Located in Hotel
  Car Park"), Mer 52 of 846 charge points ("Car Park Opening Times: 07:00 - 19:00",
  "Disabled Parking Bay"), ESB Energy 161 of 645 charge points ("Contactless payment
  available."), ChargePoint 99 of 331 sites.
- **Text only, nothing filtered.** Notes go into the page as text (`textContent`), with
  their line breaks, under the heading "Operator's notes". Nothing is changed, shortened or
  left out because of what it says, so some notes are out of date or look like internal
  codes (RAW Charging's "3$0 - Hospitality"). A few mention prices, such as "from the 4th
  March ... 60p per kWh". Prices on the map still come only from tariffs through
  `pipeline/pricing.py`; the details say the notes are as published, may be out of date,
  and that prices come from tariff data, not from the notes.
- **Shown once.** A note that every charge point at a site has, or that repeats the
  site's own note, is shown once with the site. A note that only some charge points have
  is shown with each of them as "Operator's note: ...".
- **Notes are not used to hide or label sites.** Restrictions are never read from the
  words of a note (a note saying "Disabled Parking Bay" does not add a Blue Badge
  restriction), and the private-site phrases of ADR 0023 are still matched against the
  location's name only.
- **Card payment, as the operator states it.** OCPI 2.2.1 `capabilities` on each EVSE are
  kept, in lower case, once each; a value that is not an OCPI 2.2.1 capability is ignored
  and logged (Pod sends an empty one on 41 of its first 4,351). Five of them say the charge
  point "has a payment terminal": CONTACTLESS_CARD_SUPPORT, CREDIT_CARD_PAYABLE,
  DEBIT_CARD_PAYABLE, CHIP_CARD_SUPPORT and PED_TERMINAL. Each charge point that lists any
  of them says "Card payment here, the operator says: contactless, credit card, ...". A
  charge point that lists none says nothing about payment: no capability is not read as
  no card payment, and nothing suggests a charge point lacks a terminal the regulations
  require. In the 30 October survey 41 of 45 networks sent capabilities. Some networks mark
  every charge point as credit card payable, lamp posts included (RAW Charging,
  ChargePoint, Allego, evpoint, Source EV), which may mean paying on a web page rather than
  at a terminal; that needs testing, so the wording stays the operator's statement.
- **Parking type, as the operator states it.** OCPI 2.2.1 `parking_type` is kept in lower
  case and shown under the address as "Parking type, the operator says: car park" (or
  multi-storey car park, underground car park, on the street, driveway, motorway services
  or rest area). A value that is not an OCPI 2.2.1 ParkingType is recorded as unknown and
  logged (Clenergy EV and Globe EV give "UNKNOWN" for every location). Roam's records use
  OCPI 2.1.1, whose `type` has the same values, so the Roam adapter reads `type` as
  `parking_type`. Some feeds give one value for nearly every site: all 438 of Roam's
  locations, racecourses and hotels included, say ON_STREET, and Fastned gives ON_STREET
  for a site whose address is "Hatton Cross Car Park". The owner decided on 30 October
  2026 to show every value as published, Roam's included; the wording says it is the
  operator's statement, and the operator files record these findings.
- **Floor level, as the operator states it, except where the owner decided otherwise.**
  OCPI 2.2.1 `floor_level` ("level on which the Charge Point is located (in garage
  buildings) in the locally displayed numbering scheme", up to four characters) is kept
  on each EVSE as published, with spaces at either end removed, and shown with the
  charge point as "Floor level, the operator says: -2". A value that is not text is
  ignored and logged. In the 30 October survey five networks sent it. ChargePoint (81 of
  1,167 charge points), RAW Charging (94 of 2,573) and Mer (2 of 846) mostly give levels
  such as "1", "2" and "-2", with a few that may not be ("T2", "LCFA", "B&Q", "="); those
  are shown as published. MFG (all 3,034) and Allego (all 240) give the first four
  characters of the location's name, such as "MFG ", "Morr", "Alle" and "GB, ". The
  owner decided on 30 October 2026 that no floor level is shown for those two operators,
  recorded in each operator file as `floor_level_not_read` and listed on the transparency
  page. Floor levels are left unread only where the owner records that decision; no one
  else adds one.
