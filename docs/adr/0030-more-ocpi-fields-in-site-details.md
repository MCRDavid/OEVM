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

Parts 3 to 5 are added to this record by the pull requests that build them.

Fields the survey found and the owner did not choose stay dropped: images (visitors'
browsers would fetch them from the operator's storage), floor level (mostly cut-off
names, not levels), green energy claims, the owner of a site (it can name a private
individual), and fields that only repeat a standard one.

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
