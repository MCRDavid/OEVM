# 0023: Private and taxi-only chargers, grouping on the map, and each charge point listed

Date: 2026-10-12. Status: accepted.

On 11 October 2026 the repository owner asked for four changes to the map:

- a way to turn the grouping of nearby chargers on the map on and off;
- chargers that are not for public use, such as Evolt Network's "Arthur House - Private
  Use Only", hidden by default, with a way to show them;
- where a location has several chargers, each one listed in the details with its own name
  or id and status;
- a small note at the foot of the details with the site's and each charger's references.

## What the feeds say

OCPI 2.2.1 has no field that says a location is private. A location whose `publish` flag
is false is never kept at all (ADR 0002), and `publish_allowed_to` only applies to those.
EVSE `parking_restrictions` (EV_ONLY, PLUGGED, DISABLED, CUSTOMERS, MOTORCYCLES) say who
may park, not who may charge. In Evolt Network's response of 12 October 2026, every
location named private or restricted had no other field saying so. So the operator's own
name for a location is the only sign.

The same response marks 78 EVSEs `TAXI_ONLY`, which is not an OCPI 2.2.1 value; at 26
locations every EVSE has it. PoGo Charge's response has it too. On 12 October 2026 the
owner chose "Hide them" on a decision card: taxi-only locations are hidden with private
ones, and each such charge point is labelled "Taxis only".

## Decisions

- **Private by name, from a fixed list of phrases.** `pipeline/access.py` lists the
  phrases, matched as whole words in any mix of capitals: "private use", "private access"
  or "private only"; "private" at the end of the name or in brackets; "not public",
  "non-public" or "no public access"; "restricted access" or "restricted use"; staff,
  fleet, employees, residents, tenants, members or permit holders "only"; and "staff car
  park". Words that often name a place rather than a rule ("Fleet" in Fleetwood Road,
  "Depot", "Residential", "Visitor Centre", "Blue Badge holders only") are not counted.
  The map file carries the words found (`priv`), for every location, including last good
  copies kept under ADR 0018, so the rule is the same everywhere.
- **Taxi-only by the owner's decision per operator.** `nonstandard_parking_restrictions`
  in the operator file records the date, basis, evidence and the values it covers, and
  may read a value only as `taxis_only`. Without it a value outside OCPI 2.2.1 is ignored
  and logged, as before. Evolt Network and PoGo Charge have the decision. A location
  where every charge point is `taxis_only` is flagged in the map file (`taxi`).
- **Hidden unless asked, never removed.** The map and list hide both kinds unless the
  visitor ticks "Show chargers marked private or restricted" (`priv=1` in the address).
  It counts as a filter. The data is published unchanged; the details say why such a
  location is hidden.
- **Auditable.** The transparency page lists the phrases and the operators' decisions,
  and the feed health page lists every location hidden in the latest run, with why. The
  manifest counts them per operator (`private`).
- **Grouping is a display choice.** A "Group" button on the map and a box in the filters
  switch MapLibre's clustering (`setClusterOptions`) on and off. It is on by default,
  carried as `group=0` in the address when off and saved with the filters only after
  "Remember my settings", and it is not counted as a filter or cleared by "Clear filters".
- **Each charge point listed.** EVSEs now keep `physical_reference` (the label on the
  charger) and their parking restrictions. The details list one box per charge point, named
  by its label, else its EVSE ID, else its place in the list, with its EVSE ID when that
  differs, its status in the colours of ADR 0015, any parking restrictions, and its
  connectors and prices.
- **Reference numbers last.** A small note at the foot of the details gives the operator's
  location id, the id on this map, and each charge point's EVSE ID and uid, for quoting
  when reporting a fault or a mistake.

## Consequences

- Names are not a reliable signal: a private site with a plain name stays on the map, and
  a public one whose name uses a listed phrase is hidden. The lists on the transparency and
  feed health pages let anyone check, and the phrases can be changed in one place.
- A last good copy kept from before this change has no `taxi` flags until its operator is
  fetched again, because its detail files predate the parking restrictions.
- Showing every point with grouping off is slower to draw at country zoom on older phones.

## Amended 30 October 2026: "taxi only" in a name

bp pulse's feed of 30 October 2026 names 33 of its 1,136 locations "[E-TAXI ONLY] ..." (70
EVSEs, all in and around London), with no parking restriction or other field saying so. On
30 October 2026 the repository owner chose "Hide unless asked" on a decision card: "taxi
only" and "taxis only" join the phrases in `pipeline/access.py`, so such locations are
hidden with private ones unless the visitor asks, and listed on the feed health page. No
other feed on the map that day had "taxi only" in a location name ("Taxi Rank" and "Taxi
Hub" are places, not rules, and are not caught). The phrase applies to every operator, as
the others do; taxi-only parking restrictions still need the per-operator decision above.
