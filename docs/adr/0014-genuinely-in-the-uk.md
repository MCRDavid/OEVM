# 0014: Mapping only locations that are genuinely in the UK

Date: 2026-10-09. Status: accepted.

Until now a location was "in the UK" if its coordinates fell inside latitude 49.8 to 60.95
and longitude -8.7 to 1.8 (ADR 0006). That box also takes in the Republic of Ireland, the
Isle of Man, a strip of northern France and a lot of sea. In the run of 9 October 2026 it
let six Clenergy EV locations in Dublin and Maynooth onto the map, and one Clenergy EV
location in Leeds whose longitude has lost its minus sign, which showed in the North Sea.

On 9 October 2026 the repository owner said that operators may list sites outside the UK,
but the map should only show sites that are genuinely in the UK, and that feeds should
still be checked for coordinates the wrong way round.

## Decisions

- **The UK's outline, not a box.** `pipeline/geography.py` keeps the box as a first test,
  then checks the point against land outlines of the UK and its neighbours from Natural
  Earth (1:10m, public domain, `pipeline/data/uk_and_neighbours.json`, about 280 KB). A
  point on UK land is in; a point in Ireland, the Isle of Man, Jersey, Guernsey, France,
  Belgium or the Netherlands is out.
- **The coast.** The outlines are accurate to a few hundred metres, so a charger on a pier
  or harbour can sit just off them. A point off every outline counts as in the UK if it is
  within 2 km of the UK's outline and no nearer to any other country's. Anything further
  out is left off.
- **The land border with Ireland.** Within 2 km of it the outlines cannot be trusted to
  pick a side, so the postcode decides: a Northern Ireland postcode (BT) means the UK, and
  anything else, or none, means the location is left off and counted. Strabane and Lifford,
  either side of the River Foyle, are the test cases.
- **Nothing is moved or filled in.** The check only decides whether to show a point. A
  location left off is listed in the manifest as not mapped, as before. The only
  correction remains the owner's swapped coordinates rule (ADR 0013), which now uses this
  check for "the swapped point is in the UK".
- **Not used for anything else.** Natural Earth data never appears on the map or in a
  charger record. It is credited in `DATA_LICENCES.md` although its licence does not ask
  for it.

## Checked against the live feeds on 9 October 2026

MFG EV Power (597 locations), GeniePoint (306) and Clenergy EV (1,400) were checked
from their feeds, and Jolt (72) and char.gy (5,957 mapped) from the published map. Every
point not in the UK was tested for whether swapping latitude and longitude, or changing a
sign, would put it in the UK. Results are recorded as findings in the operator files:

- Clenergy EV: two swaps (corrected under ADR 0013), one in Ireland once swapped (left
  off), one missing minus sign (left off), six in Ireland and eight further afield.
- GeniePoint: one missing minus sign (Crewe Civic, already recorded, left off).
- MFG EV Power and Jolt: none.
- char.gy: its mapped points are all in the UK. The one location left off in that run
  could not be looked at, because char.gy refused the check's full fetch part way (HTTP
  403 at offset 2700). It needs checking in a later run.

## Consequences

- Six Clenergy EV locations in Ireland and one in the North Sea leave the map.
- A charger within 2 km of the Irish border with no postcode is left off. The manifest
  lists it, so it can be looked at if it happens.
- Checking about 9,000 points takes well under a second.
