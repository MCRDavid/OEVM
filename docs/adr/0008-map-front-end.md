# 0008: Map front end

Date: 2026-10-08. Status: accepted.

Blueprint task 9: a map with clustering, filters, a details panel with provenance and
timestamps, settings in the page address, opt-in saved settings and a list view. Accept:
usable on a mid-range phone, Lighthouse accessibility score of 90 or more.

## Decisions

- **No build tool.** The page is plain HTML, CSS and JavaScript modules in `site/`.
  `pipeline/build_site.py` copies them into a build folder with the map files, MapLibre
  and `assets/config.json`. The committed `site/` folder is never written to.
- **MapLibre GL JS, served from the site.** It is pinned to one version in `package.json`
  (6.11.2 when this was decided, updated by Dependabot since) and
  installed with `npm ci`; the build copies its three module files and CSS, its licence
  and a `THIRD_PARTY_NOTICES.txt` built from the licences of the packages it bundles.
  Visitors' browsers contact no script host. Version 6 needs WebGL2.
- **OpenFreeMap basemap (Liberty style).** Chosen by the repository owner on 8 October
  2026 over a self-hosted extract. It needs no key and, by its own statement and our
  header checks that day, sets no cookies. A self-hosted Protomaps UK extract was sized
  at about 310 MB up to zoom 12 and over GitHub Pages' 1 GB site limit at zoom 14, so it
  is the fallback if OpenFreeMap stops. OpenFreeMap's responses carry Cloudflare's
  Network Error Logging headers; the owner accepted them on 8 October 2026, on condition
  that the privacy notice and the page footer mention them (`docs/PRIVACY_AND_COOKIES.md`,
  rule 2).
- **The list is the accessible view.** Points drawn on a map canvas cannot be reached by
  keyboard or screen reader, so the list shows the same chargers as buttons, nearest the
  centre of the map area first, up to 200 at a time with a note when there are more. A
  skip link leads to it. On small screens the page shows the map or the list, switched
  with two buttons; from 60em wide it shows both. If MapLibre cannot start (no WebGL2 or
  no module support) or the basemap style cannot be loaded, the page says so and shows
  the list. A map hidden behind the list view starts only when it is first shown, so it
  never opens at the wrong place.
- **Details panel.** On a phone it is a sheet over the bottom of the page, and the rest of
  the page is made inert while it is open, so keyboard focus cannot move behind it. On a
  wide screen it covers only the list column, which is made inert, so the header,
  filters and map stay usable. Escape or Close returns focus to what opened it.
- **Text from feeds is never markup.** Every value is added with `textContent` or as a
  text node, links are made only for http and https addresses, and no MapLibre popup is
  used (its `setHTML` does not clean input). Tests feed markup through a location's name
  and attribution and check nothing runs.
- **Content Security Policy** in a meta tag, as GitHub Pages cannot send headers: scripts,
  styles and fonts from the site only; connections and images also from
  `tiles.openfreemap.org`. No inline scripts or styles. A worker started from a file
  takes its policy from that file's own response headers, which GitHub Pages does not
  send, so MapLibre's tile requests are also checked in the page: `transformRequest`
  lets requests go only to this site and the hosts listed in `config.json` (`origins`),
  and sends anything else to an address on this site that does not exist.
- **Referrer policy `strict-origin`:** requests from the page, to this site or the tile
  host, carry only the site's origin, never the page address with its filters. MapLibre's
  worker is started from a file, so its tile requests follow the browser's default policy
  instead, which for a request to another host also sends only the origin. Filters
  loaded from saved settings are kept out of the address until the visitor changes one,
  so a reload or bookmark does not send them to the web host either.
- **Settings.** Filters live in the page address (`?minkw=50&plug=ccs`), written with
  `history.replaceState`, and MapLibre keeps the map position after the `#`. Values that
  are not valid are ignored. Saving to `localStorage` happens only after the visitor
  turns on "Remember my settings on this device"; "Forget my settings" deletes the one
  key. Filters in the address take priority over saved ones.
- **Price wording comes from the pipeline.** The details panel shows each connector's
  text and the list shows each location's summary (`pt`), both written by
  `pipeline/pricing.py`; the page never words a price. A location is `free` only when
  every connector is `free_confirmed`; a mix says "some connectors free (confirmed)".
- **Filters apply to one connector at a time.** Each location in the slim layer lists
  each kind of connector once (`cons`: standard, power, price state and pence per kWh
  including VAT), and a location matches when one connector meets every connector
  condition together. This adds about 17 bytes per location after gzip in the recorded
  fixtures, roughly 0.85 MB for 50,000 locations.
- **Tests never contact OpenFreeMap.** Its terms forbid automated collection, so the
  browser tests build with `--offline-style`, a plain local style, and run Chromium with
  every outside host blocked. They check that the page makes no outside requests, logs no
  errors (including Content Security Policy errors), saves nothing until the visitor opts
  in, and scores at least 0.9 for accessibility in Lighthouse on a phone. MapLibre 6
  draws the cluster counts with local fonts when a style has none.

## Not done yet

- Favourites and a home location (the privacy rules already cover them; a home location
  would be visible to the map host as an area, so the notice must say so first).
- Deployment to GitHub Pages and the daily data run (blueprint task 10; see ADR 0009).
- Live status on click (blueprint section 2, later phase).
- Testing with a real screen reader and on real phones. The phone check so far is a
  412 by 823 pixel browser window with software WebGL.
