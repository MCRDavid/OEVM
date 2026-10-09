# 0013: Correcting coordinates that are obviously the wrong way round

Date: 2026-10-09. Status: accepted.

Clenergy EV's feed (9 October 2026) has two locations with UK postcodes whose latitude
and longitude are the wrong way round, which puts them in the sea off east Africa. Until
now the project left any location outside the UK off the map and never changed an
operator's figures. On 9 October 2026 the repository owner decided that where the swap is
obvious, the location should be shown in the right place, with the correction shown on
the site and recorded against the operator as inaccurate data.

## Decisions

- **Opt-in per operator, by the owner only.** `swapped_coordinates` in the operator file
  records the date and the basis, like `missing_publish_flag` and `relay`. Without it,
  nothing is corrected.
- **Only obvious swaps.** A location is corrected only when all of these hold: its
  published point is outside the map's UK limits, the same two numbers the other way round
  fall inside them, its country is GBR, and its postcode is a UK postcode. The postcode
  test matters because the UK limits also take in the Republic of Ireland: a Clenergy EV
  site with an Irish postcode has the same pattern and is not moved. (Since ADR 0016 "in
  the UK" uses the UK's outline, so a swap that lands in Ireland is not taken either.)
- **Nothing else is changed or taken from another source.** The two numbers are the
  operator's own; no position is looked up from a postcode, OpenStreetMap or anywhere
  else. The location record otherwise stays as published.
- **Visible everywhere it matters.** The location's detail file keeps the operator's own
  figures in `coordinates_corrected` and the map shows a note saying what was swapped. The
  manifest counts and lists corrected locations per operator. The operator file records a
  dated finding naming each corrected location, and the transparency page shows the
  decision and the finding.
- **Neutral wording.** The note and the finding say what was published and what the map
  shows, and nothing about why.

## Consequences

- Two Clenergy EV locations appear on the map that would otherwise be missing.
- The finding names the locations as of 9 October 2026. The manifest is the daily record;
  the finding is updated when a run shows new or fixed cases.
