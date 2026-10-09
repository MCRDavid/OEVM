# 0012: Map layout, point colours, dark mode and "Find my location"

Date: 2026-10-09. Status: accepted.

The repository owner asked for an easier map: clearer navigation, filters by speed, cost
and "not broken", different colours for map points, a dark mode, and a button that moves
the map to the visitor's location if the map provider allows it. This builds on ADR 0008.

## Decisions

- **Points are coloured by their fastest connector.** Five colours: 150 kW or more
  (ultra-rapid), 50 to 149 kW (rapid), 8 to 49 kW, under 8 kW, and power unknown. 8 kW is
  the contactless threshold in regulation 5 of the Public Charge Point Regulations 2023,
  50 kW is their "rapid charge point", and 150 kW matches the existing ultra-rapid step in
  the power filter. Points also grow slightly with speed, so colour is not the only cue.
  The letter on each point still shows the price (F free confirmed, £ priced, ? unknown).
  Every colour has at least 4.5:1 contrast with the white letter and a white outline so
  it stands out on light and dark maps. Speed was chosen over price because price is
  already shown on the point and is unknown for many chargers.
- **A key** sits over the map as a `details` element: open on wide screens, closed on
  phones so it does not cover the map.
- **"Hide out of service" filter.** Each kind of connector in `locations.geojson` gains
  `out`: true when the operator reported its charge point as `out_of_order`,
  `inoperative`, `planned` or `removed` in the fetch the file was built from. `blocked`
  (often a parked car) and `unknown` do not count. The filter (`?ok=1`) hides a location
  only when none of its connectors that meet the other filters is free of that report.
  Locations where every connector was reported out of service are drawn faded and say
  so in the list. The wording always says "reported" and "at the last daily fetch",
  because the status is a daily snapshot, not live (live status is Phase 3). This adds
  about 11 bytes per connector kind before gzip and very little after.
- **Quick filters** in the header for the three most used choices (rapid, free, hide out
  of service). They change the same state as the full form, and the Filters button shows
  how many filters are on. The filter form has a "Show chargers" button that closes it,
  and on wide screens its sections sit in columns.
- **Dark mode** follows the device's light or dark setting by default, with a
  "Dark mode" button to switch. The page colours come from CSS variables; the map
  switches to OpenFreeMap's Dark style, from the same host as Liberty, so the Content
  Security Policy and the request guard do not change. The chargers are added again
  whenever a style loads. The choice is saved only when "Remember my settings" is on,
  in the same `localStorage` key (`theme` beside `filters`); otherwise it lasts for the
  visit. Offline builds get a plain dark test style as well.
- **"Find my location"** uses MapLibre's own `GeolocateControl`, which asks the browser
  for one position (no tracking) and moves the map there, up to zoom 12. It is added only
  in a secure context with the Geolocation API. The site stores and sends nothing, but
  the map then fetches tiles for that area and the hash shows the position, so the
  privacy notice now says both (rule 6). A refusal or failure is explained in the notice
  area.

## Not done

- Preview screenshots and tests use the offline style, never OpenFreeMap (its terms
  forbid automated collection), so the dark basemap itself has only been checked by
  reading its style file and headers.
- Testing with a real screen reader and on real phones, as in ADR 0008.
