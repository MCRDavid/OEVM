# 0027: An operator's own feed in place of copies in another operator's feed

Date: 2026-10-23. Status: accepted.

Urban Fox publishes its own OCPI 2.2.1 feed (138 locations on 23 October 2026). Monta's
open data feed, already on the map, also carries Urban Fox locations under Urban Fox's own
OCPI party, GB UFX, with different location ids: 95 were on the map on 23 October 2026,
and 39 of the first 50 locations in Urban Fox's own feed are within about 30 metres of one
of them. Switching Urban Fox on as it is would show most of these sites twice. The
repository owner decided on 23 October 2026 that the operator's own feed wins: Urban Fox
is switched on, and Monta's GB UFX locations are left off while Urban Fox's own locations
are on the map.

## Decisions

- **Opt-in per operator, by the owner only.** `own_feed_over_copies` in the operator file
  of the network whose own feed is shown records the date, the basis, the evidence and the
  operators whose feeds carry the copies. It needs the network's own `ocpi_country_code`
  and `ocpi_party_id`, cannot name the network itself, and the registry checks every named
  operator exists. Without it both feeds are shown as published.
- **Copies are matched by party, not by place or name.** A copy is a location that a named
  operator's feed sends under the network's country and party codes, so its record id
  starts `<named operator>:<country>:<party>:`. Coordinates and names are never compared,
  so nothing depends on guessing which two records are the same site, and a site only the
  other feed carries is left off too while the network's own feed is on the map.
- **Only while the network's own feed is on the map.** The copies are left off when the
  network has at least one location on the map, from this run or from its last good copy
  (ADR 0018). When it has none, for example on a day its fetch fails and no copy can be
  kept, the copies are shown, so the sites do not vanish from the map.
- **Nothing is changed.** Neither feed's records are altered. The copies' map points and
  detail files are simply not written.
- **Visible.** The manifest counts the locations left off per feed (`replaced`,
  `replaced_ids` and `replaced_by`), the run report says how many, the feed health page
  lists them under "Shown from the network's own feed" with their ids, and the
  transparency page shows the decision in the network's row.

## Consequences

- Urban Fox's sites appear once, from Urban Fox's own feed and under its own attribution.
- A kept copy of the other feed holds only what was on the map when it was written, so on
  a day both feeds fail it may lack the copies; this is accepted as rare.
- Other platform feeds that carry networks with their own feeds (Monta carries several
  parties) can be handled the same way, each by its own recorded decision.
