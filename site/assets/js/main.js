// The map page. The list of chargers works on its own; the map is added on top when the
// browser can run it (MapLibre needs WebGL2). Nothing is saved on the device unless the
// visitor turns on "Remember my settings" (see settings.js).

import { renderDetail, detailUrl } from "./detail.js";
import { activeCount, defaults, matches, parse, serialise } from "./filters.js";
import { h } from "./dom.js";
import { allOut, formatKw, plugsSummary, speedBand } from "./format.js";
import { createSettings } from "./settings.js";

const LIST_LIMIT = 200;
// Point colours by fastest connector (format.js, SPEED_BANDS), matching app.css. Each has
// at least 4.5:1 contrast with the white letter drawn on it.
const SPEED_COLOURS = { ultra: "#9b2c74", rapid: "#b3460c", fast: "#0d6b62", slow: "#2f5d9e", unknown: "#5c5c5c" };
const SPEED_RADIUS = { ultra: 13, rapid: 12, fast: 11, slow: 10, unknown: 10 };
const CHARGER_LAYERS = ["clusters", "points", "cluster-count", "point-labels"];
const FONT = ["Noto Sans Regular"];
const $ = (id) => document.getElementById(id);
const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
const PREFERS_DARK = window.matchMedia("(prefers-color-scheme: dark)");
const WIDE = window.matchMedia("(min-width: 60em)"); // map and list side by side; matches app.css
const MAP_FAILED = "The map could not start in this browser, so chargers are shown as a list.";
const STYLE_FAILED = "The background map could not be loaded, so chargers are shown as a list.";

let storage = null;
try {
  storage = window.localStorage;
} catch {
  storage = null; // blocked by the browser; remembering settings is then unavailable
}
const settings = createSettings(storage);

const app = {
  config: null,
  features: [],
  filtered: [],
  operators: new Map(),
  state: defaults(),
  map: null,
  area: null,
  mapPending: false,
  lastTrigger: null,
  lastKey: null,
  detailRequest: 0,
  savedOnly: false,
  theme: null, // "light" or "dark" once the visitor picks one; until then the device decides
  plans: [], // data/plans.json; empty if it could not be loaded
  mine: new Set(), // ids of the plans the visitor says they have
  detail: null, // the open location's detail file, so the panel can be redrawn
};

async function loadJson(url) {
  const response = await fetch(url, { credentials: "same-origin" });
  if (!response.ok) throw new Error(`${url}: HTTP ${response.status}`);
  return response.json();
}

// #notice is a status region that stays in the page while empty, so screen readers
// announce text put into it later.
function notice(text) {
  $("notice").textContent = text;
}

// Filters and the page address

function hasFilterParams() {
  const keys = ["minkw", "plug", "free", "maxp", "unknown", "ok", "op", "view"];
  const params = new URLSearchParams(window.location.search);
  return keys.some((key) => params.has(key));
}

// Filters loaded from saved settings stay out of the address until the visitor changes
// one, so a reload or bookmark never sends saved settings to the web host.
function writeAddress() {
  const query = app.savedOnly ? "" : serialise(app.state);
  const url = `${window.location.pathname}${query ? `?${query}` : ""}${window.location.hash}`;
  window.history.replaceState(null, "", url);
}

function saveIfRemembered() {
  if ($("remember").checked && !settings.save(app.state, app.theme, [...app.mine])) {
    $("settings-message").textContent = "Your browser did not allow saving settings.";
  }
}

function stateToForm() {
  const form = $("filters");
  $("minkw").value = String(app.state.minkw);
  for (const box of form.querySelectorAll('input[name="plug"]')) box.checked = app.state.plugs.includes(box.value);
  for (const box of form.querySelectorAll('input[name="op"]')) box.checked = app.state.ops.includes(box.value);
  $("free").checked = app.state.free;
  $("maxp").value = app.state.maxp === null ? "" : String(app.state.maxp);
  $("unknown").checked = app.state.unknown;
  $("working").checked = app.state.working;
  showActiveFilters();
}

// The quick filters in the header and the count on the Filters button follow the form.
function showActiveFilters() {
  const count = activeCount(app.state);
  $("filter-count").textContent = count ? ` (${count})` : "";
  $("quick-rapid").setAttribute("aria-pressed", String(app.state.minkw >= 50));
  $("quick-free").setAttribute("aria-pressed", String(app.state.free));
  $("quick-working").setAttribute("aria-pressed", String(app.state.working));
  // The out of service count on an open charger's details switches the same filter.
  for (const button of document.querySelectorAll('#detail-body [data-filter="working"]')) {
    button.setAttribute("aria-pressed", String(app.state.working));
  }
}

// Networks without a box yet (the data is still loading) keep their place in the filters.
function formToState() {
  const form = $("filters");
  const query = new URLSearchParams();
  query.set("minkw", $("minkw").value);
  const plugs = [...form.querySelectorAll('input[name="plug"]:checked')].map((b) => b.value);
  if (plugs.length) query.set("plug", plugs.join(","));
  const boxes = new Set([...form.querySelectorAll('input[name="op"]')].map((b) => b.value));
  const ops = [
    ...[...form.querySelectorAll('input[name="op"]:checked')].map((b) => b.value),
    ...app.state.ops.filter((op) => !boxes.has(op)),
  ];
  if (ops.length) query.set("op", ops.join(","));
  if ($("free").checked) query.set("free", "1");
  if ($("maxp").value.trim() !== "") query.set("maxp", $("maxp").value.trim());
  if (!$("unknown").checked) query.set("unknown", "0");
  if ($("working").checked) query.set("ok", "1");
  if (app.state.view === "list") query.set("view", "list");
  return parse(query.toString());
}

function stateChanged() {
  app.savedOnly = false;
  showActiveFilters();
  writeAddress();
  saveIfRemembered();
  applyFilters();
}

// Data

function applyFilters() {
  app.filtered = app.features.filter((f) => matches(f.properties, app.state));
  const source = app.map?.getSource("chargers");
  if (source) source.setData({ type: "FeatureCollection", features: app.filtered });
  renderList();
}

function buildNetworks() {
  const fieldset = $("networks");
  const ops = [...new Set(app.features.map((f) => f.properties.op))].sort((a, b) =>
    (app.operators.get(a) ?? a).localeCompare(app.operators.get(b) ?? b),
  );
  for (const op of ops) {
    fieldset.append(
      h("label", {}, h("input", { type: "checkbox", name: "op", value: op }), ` ${app.operators.get(op) ?? op}`),
    );
  }
}

// A network in a link or saved settings that has no chargers in the data would hide every
// charger while no box is ticked, so it is dropped with a note.
function dropUnknownNetworks() {
  const known = new Set(app.features.map((f) => f.properties.op));
  if (app.state.ops.every((op) => known.has(op))) return;
  app.state.ops = app.state.ops.filter((op) => known.has(op));
  saveIfRemembered();
  notice("A network in your filters has no chargers in the current data, so it was removed from the filters.");
}

// "Your charging plans": the visitor ticks the plans they have, so the details can show
// the cheapest way to pay with them. Saved only with "Remember my settings".
function buildPlanPicker() {
  const fieldset = $("my-plans");
  if (!app.plans.length) {
    // Saved choices are kept: a list that failed to load once must not delete them.
    fieldset.append(h("p", { className: "hint", text: "The list of plans could not be loaded." }));
    return;
  }
  const known = new Set(app.plans.map((plan) => plan.id));
  app.mine = new Set([...app.mine].filter((id) => known.has(id)));
  const providers = [...new Set(app.plans.map((plan) => plan.provider))].sort((a, b) => a.localeCompare(b));
  for (const provider of providers) {
    const group = h("fieldset", { className: "plan-group" }, h("legend", { text: provider }));
    for (const plan of app.plans.filter((p) => p.provider === provider)) {
      const box = h("input", { type: "checkbox", name: "plan", value: plan.id, checked: app.mine.has(plan.id) });
      box.addEventListener("change", () => {
        if (box.checked) app.mine.add(plan.id);
        else app.mine.delete(plan.id);
        saveIfRemembered();
        redrawDetail();
      });
      group.append(h("label", {}, box, ` ${plan.name}: ${plan.fee_text}; ${plan.price_text}`));
    }
    fieldset.append(group);
  }
}

function buildAttribution(layer) {
  const list = $("attribution");
  for (const statement of layer.attribution ?? []) list.append(h("li", { text: statement }));
  if (layer.licence_note) list.append(h("li", { text: layer.licence_note }));
}

// The list

function distance(a, b) {
  const dx = (a[0] - b[0]) * Math.cos(((a[1] + b[1]) / 2) * (Math.PI / 180));
  const dy = a[1] - b[1];
  return dx * dx + dy * dy;
}

// The area the map last showed. A hidden map (the list view on a small screen) has no
// size, so the list keeps using the area the visitor last looked at.
function mapArea() {
  const container = app.map?.getContainer();
  if (container && container.clientWidth > 0 && container.clientHeight > 0) {
    app.area = { bounds: app.map.getBounds(), centre: app.map.getCenter().toArray() };
  }
  return app.map ? app.area : null;
}

function listSummary(total, shown, inArea) {
  const verb = total === 1 ? "matches" : "match";
  if (total === 0) return inArea ? "No chargers in the map area match your filters." : "No chargers match your filters.";
  const where = inArea
    ? `in the map area that ${verb} your filters, nearest the centre first`
    : `that ${verb} your filters`;
  const more = total > shown ? ` Showing the first ${shown}; zoom in or filter to see others.` : "";
  return `${total} charger location${total === 1 ? "" : "s"} ${where}.${more}`;
}

function renderList() {
  let candidates = app.filtered;
  const area = mapArea();
  if (area) {
    const { bounds, centre } = area;
    candidates = candidates
      .filter((f) => bounds.contains(f.geometry.coordinates))
      .sort((a, b) => distance(a.geometry.coordinates, centre) - distance(b.geometry.coordinates, centre));
  } else {
    candidates = [...candidates].sort((a, b) => (a.properties.name ?? "").localeCompare(b.properties.name ?? ""));
  }
  const shown = candidates.slice(0, LIST_LIMIT);
  $("list-summary").textContent = listSummary(candidates.length, shown.length, Boolean(area));
  const focusedKey = document.activeElement?.closest?.("#list-items")
    ? document.activeElement.dataset.key
    : null;
  const items = shown.map((feature) => {
    const p = feature.properties;
    return h(
      "li",
      {},
      h(
        "button",
        { type: "button", className: "item", "data-key": p.key, onclick: () => openDetail(p.key) },
        h(
          "span",
          { className: "name" },
          h("i", { className: `dot ${p.band}${p.down ? " out" : ""}`, "aria-hidden": "true" }),
          p.name || "Charger location",
        ),
        h("span", { className: "meta", text: `${app.operators.get(p.op) ?? p.op} · up to ${formatKw(p.kw)} · ${plugsSummary(p.plugs)}` }),
        h("span", { className: `meta price-${p.price}`, text: p.pt || "Price unknown" }),
        p.down ? h("span", { className: "meta out-note", text: "Reported out of service at the last daily fetch" }) : null,
      ),
    );
  });
  $("list-items").replaceChildren(...items);
  if (focusedKey) listButton(focusedKey)?.focus();
}

// Details

function listButton(key) {
  return key ? $("list-items").querySelector(`button[data-key="${CSS.escape(key)}"]`) : null;
}

// While the panel is open, what it covers cannot be reached: on a small screen that is the
// whole page behind it, on a wide screen the list it sits over. Without the map, a wide
// screen shows the panel beside the list instead, so the list stays usable.
function coverPage(open) {
  const narrow = !WIDE.matches;
  const besideList = !narrow && document.body.classList.contains("no-map");
  document.body.classList.toggle("detail-open", open);
  $("list").inert = open && !besideList;
  for (const element of [
    document.querySelector(".skip"),
    document.querySelector(".top"),
    $("filters"),
    $("notice"),
    $("map-view"),
    document.querySelector(".bottom"),
  ]) {
    element.inert = open && narrow;
  }
}

function toggleHideOut() {
  app.state = { ...app.state, working: !app.state.working };
  stateToForm();
  stateChanged();
}

function detailOptions() {
  return { ...app.config, plans: app.plans, mine: app.mine, hideOut: app.state.working, onHideOut: toggleHideOut };
}

// Ticking a plan while a charger's details are open (possible on a wide screen) redraws
// them, so "You have this plan" and the cheapest line stay right. Focus stays put.
function redrawDetail() {
  if ($("detail").hidden || !app.detail) return;
  $("detail-body").replaceChildren(...renderDetail(app.detail, detailOptions()));
}

async function openDetail(key, trigger) {
  const request = ++app.detailRequest;
  app.lastTrigger = trigger ?? listButton(key) ?? document.activeElement;
  app.lastKey = key;
  const panel = $("detail");
  const body = $("detail-body");
  body.replaceChildren(h("p", { role: "status", text: "Loading details…" }));
  panel.hidden = false;
  coverPage(true);
  $("close-detail").focus();
  app.detail = null;
  let content;
  let loaded = null;
  try {
    loaded = await loadJson(detailUrl(key));
    content = renderDetail(loaded, detailOptions());
  } catch {
    loaded = null;
    content = [h("h2", { id: "detail-heading", tabindex: "-1", text: "Details could not be loaded" })];
  }
  // A slower answer for a charger opened earlier, or for a closed panel, is dropped.
  if (request !== app.detailRequest || panel.hidden) return;
  app.detail = loaded;
  body.replaceChildren(...content);
  $("detail-heading")?.focus();
}

// Focus goes back to what opened the panel. If the list was redrawn meanwhile, it goes to
// the same charger's new button, or else to the list.
function closeDetail() {
  $("detail").hidden = true;
  coverPage(false);
  const target = document.contains(app.lastTrigger) ? app.lastTrigger : listButton(app.lastKey);
  (target ?? $("list")).focus();
}

// Views

function setView(view, { focus = false } = {}) {
  app.state.view = view;
  document.body.dataset.view = view;
  $("show-map").setAttribute("aria-pressed", String(view === "map"));
  $("show-list").setAttribute("aria-pressed", String(view === "list"));
  if (view === "map") app.map?.resize();
  startPendingMap();
  if (focus && view === "list") $("list").focus();
}

// A map started inside a hidden container has no size and opens at the wrong place, so on
// a small screen that opens in the list view it starts when it is first shown: after
// pressing Map, or when the screen becomes wide enough to show both.
function mapVisible() {
  const container = $("map");
  return container.clientWidth > 0 && container.clientHeight > 0;
}

function startPendingMap() {
  if (app.mapPending && mapVisible()) {
    app.mapPending = false;
    startMap();
  }
}

// The map

// Map requests may only go to this site and the basemap host in config.json. Anything
// else (for example a source a future style adds) is sent to an address on this site that
// does not exist, so it fails here instead of reaching another host.
function requestGuard(origins) {
  const allowed = new Set([window.location.origin, ...origins]);
  return (url) => {
    try {
      if (allowed.has(new URL(url, window.location.href).origin)) return { url };
    } catch {
      // not a URL
    }
    return { url: new URL("blocked-outside-request", window.location.href).href };
  };
}

async function startMap() {
  let maplibre;
  try {
    maplibre = await import("../../vendor/maplibre-gl/maplibre-gl.mjs");
  } catch {
    return mapUnavailable(MAP_FAILED);
  }
  let styleLoaded = false;
  try {
    app.map = new maplibre.Map({
      container: "map",
      style: mapStyle(),
      bounds: [
        [-8.2, 49.9],
        [1.8, 58.7],
      ],
      maxBounds: app.config.maxBounds,
      hash: true,
      transformRequest: requestGuard(app.config.origins ?? []),
      attributionControl: {
        compact: false,
        customAttribution: "Charger data: the operators credited under Data sources and credits",
      },
      locale: {
        "Map.Title": "Map of public EV chargers. Use the list for keyboard access.",
        "GeolocateControl.FindMyLocation": "Find my location",
        "GeolocateControl.LocationNotAvailable": "Your location is not available",
      },
      fadeDuration: reducedMotion ? 0 : 300,
    });
  } catch {
    return mapUnavailable(MAP_FAILED);
  }
  app.map.addControl(new maplibre.NavigationControl({ showCompass: false }), "top-right");
  addLocateControl(maplibre);
  app.map.on("style.load", () => {
    styleLoaded = true;
    addChargerLayers();
  });
  // Errors are logged. Before the style has loaded (the basemap host is down or blocked)
  // the chargers could never be drawn, so the list takes over; later errors, such as one
  // missing tile, leave the map as it is.
  app.map.on("error", (event) => {
    console.error("Map error:", event?.error?.message ?? event);
    if (!styleLoaded || /Worker failed|WebGL/i.test(String(event?.error?.message ?? ""))) {
      mapUnavailable(styleLoaded ? MAP_FAILED : STYLE_FAILED);
    }
  });
  // Handlers named by layer stay in place when a new style (light or dark) replaces the
  // layers, so they are added once.
  app.map.on("click", "clusters", async (event) => {
    const cluster = event.features[0];
    const zoom = await app.map.getSource("chargers").getClusterExpansionZoom(cluster.properties.cluster_id);
    app.map.easeTo({ center: cluster.geometry.coordinates, zoom, duration: reducedMotion ? 0 : 500 });
  });
  app.map.on("click", "points", (event) => openDetail(event.features[0].properties.key, app.map.getCanvas()));
  for (const layer of ["clusters", "points"]) {
    app.map.on("mouseenter", layer, () => (app.map.getCanvas().style.cursor = "pointer"));
    app.map.on("mouseleave", layer, () => (app.map.getCanvas().style.cursor = ""));
  }
  app.map.on("load", renderList);
  app.map.on("moveend", renderList);
}

function mapStyle() {
  return effectiveTheme() === "dark" ? (app.config.darkStyle ?? app.config.style) : app.config.style;
}

// Points are coloured by their fastest connector and sized a little larger the faster
// it is, so the colour is not the only cue. The letter shows the price. A location whose
// every connector was reported out of service is faded.
function addChargerLayers() {
  if (app.map.getSource("chargers")) return;
  app.map.addSource("chargers", {
    type: "geojson",
    data: { type: "FeatureCollection", features: app.filtered },
    cluster: true,
    clusterRadius: 50,
    clusterMaxZoom: 13,
  });
  const band = (values) => ["match", ["get", "band"], ...Object.entries(values).flat(), values.unknown];
  const faded = (normal) => ["case", ["get", "down"], 0.45, normal];
  app.map.addLayer({
    id: "clusters",
    type: "circle",
    source: "chargers",
    filter: ["has", "point_count"],
    paint: {
      "circle-color": "#24323f",
      "circle-radius": ["step", ["get", "point_count"], 16, 25, 20, 100, 26],
      "circle-stroke-width": 2,
      "circle-stroke-color": "#ffffff",
    },
  });
  app.map.addLayer({
    id: "points",
    type: "circle",
    source: "chargers",
    filter: ["!", ["has", "point_count"]],
    paint: {
      "circle-color": band(SPEED_COLOURS),
      "circle-radius": band(SPEED_RADIUS),
      "circle-opacity": faded(1),
      "circle-stroke-width": 2,
      "circle-stroke-color": "#ffffff",
      "circle-stroke-opacity": faded(1),
    },
  });
  app.map.addLayer({
    id: "cluster-count",
    type: "symbol",
    source: "chargers",
    filter: ["has", "point_count"],
    layout: { "text-field": ["get", "point_count_abbreviated"], "text-font": FONT, "text-size": 13, "text-allow-overlap": true },
    paint: { "text-color": "#ffffff" },
  });
  app.map.addLayer({
    id: "point-labels",
    type: "symbol",
    source: "chargers",
    filter: ["!", ["has", "point_count"]],
    layout: {
      "text-field": ["match", ["get", "price"], "free", "F", "priced", "£", "?"],
      "text-font": FONT,
      "text-size": 12,
      "text-allow-overlap": true,
    },
    paint: { "text-color": "#ffffff", "text-opacity": faded(1) },
  });
  renderList();
}

// "Find my location" uses MapLibre's own control, which asks the browser for one
// position and moves the map there. The position stays in the browser: only the map
// files for that area are fetched, as for any other area.
function addLocateControl(maplibre) {
  if (!("geolocation" in navigator) || !window.isSecureContext) return;
  const locate = new maplibre.GeolocateControl({
    positionOptions: { enableHighAccuracy: false, timeout: 15000, maximumAge: 60000 },
    fitBoundsOptions: { maxZoom: 12, ...(reducedMotion ? { animate: false } : {}) },
    trackUserLocation: false,
    showAccuracyCircle: true,
  });
  locate.on("error", (error) => {
    notice(
      error?.code === 1
        ? "Your browser did not allow the map to use your location. You can change this in your browser's settings."
        : "Your location could not be found just now. You can move the map by hand instead.",
    );
  });
  locate.on("geolocate", () => notice(""));
  app.map.addControl(locate, "top-right");
}

function mapUnavailable(message) {
  if (document.body.classList.contains("no-map")) return;
  try {
    app.map?.remove();
  } catch {
    // the map may not have finished starting
  }
  app.map = null;
  app.area = null;
  app.mapPending = false;
  document.body.classList.add("no-map");
  if (!$("detail").hidden) coverPage(true);
  $("show-map").disabled = true;
  notice(message);
  setView("list");
  renderList();
}

// Light and dark

function effectiveTheme() {
  return app.theme ?? (PREFERS_DARK.matches ? "dark" : "light");
}

// The page follows the device's setting (app.css) until the visitor presses the button.
function applyTheme() {
  const theme = effectiveTheme();
  document.documentElement.dataset.theme = theme;
  $("toggle-theme").setAttribute("aria-pressed", String(theme === "dark"));
  if (app.map && app.config.darkStyle) app.map.setStyle(mapStyle(), { diff: false });
}

// Settings

function setUpSettings() {
  const remember = $("remember");
  const message = $("settings-message");
  remember.checked = settings.isRemembered();
  if (!storage) {
    remember.disabled = true;
    message.textContent = "This browser does not allow saving settings.";
  }
  remember.addEventListener("change", () => {
    if (remember.checked) {
      if (settings.save(app.state, app.theme, [...app.mine])) {
        message.textContent = "Your settings are saved on this device: filters, ticked charging plans and light or dark mode if you picked one.";
      } else {
        remember.checked = false;
        message.textContent = "Your browser did not allow saving settings.";
      }
    } else {
      settings.forget();
      message.textContent = "The settings saved on this device have been deleted.";
    }
  });
  $("forget").addEventListener("click", () => {
    settings.forget();
    remember.checked = false;
    message.textContent = "The settings saved on this device have been deleted.";
  });
  // "Forget my settings" in another tab must not be undone by this one saving again.
  window.addEventListener("storage", () => {
    remember.checked = settings.isRemembered();
  });
}

// The map height depends on the header's, which wraps on narrow screens. It is measured
// into its own variable: the header's minimum height must not grow with it, or a header
// that wrapped once (a phone turned sideways and back) would never shrink again.
function trackHeaderHeight() {
  const header = document.querySelector(".top");
  const update = () => document.documentElement.style.setProperty("--header-measured", `${header.offsetHeight}px`);
  update();
  if ("ResizeObserver" in window) new ResizeObserver(update).observe(header);
}

// Start

function wireUp() {
  $("filters").addEventListener("change", (event) => {
    if (event.target.id === "remember") return; // handled in setUpSettings
    if (event.target.name === "plan") return; // handled in buildPlanPicker
    app.state = formToState();
    stateChanged();
  });
  $("filters").addEventListener("submit", (event) => event.preventDefault());
  $("toggle-theme").addEventListener("click", () => {
    app.theme = effectiveTheme() === "dark" ? "light" : "dark";
    applyTheme();
    saveIfRemembered();
  });
  PREFERS_DARK.addEventListener("change", () => {
    if (!app.theme) applyTheme();
  });
  const quick = {
    "quick-rapid": (state) => ({ ...state, minkw: state.minkw >= 50 ? 0 : 50 }),
    "quick-free": (state) => ({ ...state, free: !state.free }),
    "quick-working": (state) => ({ ...state, working: !state.working }),
  };
  for (const [id, change] of Object.entries(quick)) {
    $(id).addEventListener("click", () => {
      app.state = change(app.state);
      stateToForm();
      stateChanged();
    });
  }
  $("done").addEventListener("click", () => {
    $("toggle-filters").setAttribute("aria-expanded", "false");
    $("filters").hidden = true;
    $("toggle-filters").focus();
  });
  $("reset").addEventListener("click", () => {
    app.state = { ...defaults(), view: app.state.view };
    stateToForm();
    stateChanged();
  });
  $("toggle-filters").addEventListener("click", (event) => {
    const open = event.currentTarget.getAttribute("aria-expanded") !== "true";
    event.currentTarget.setAttribute("aria-expanded", String(open));
    $("filters").hidden = !open;
    if (open) $("filters-heading").focus?.();
  });
  $("show-map").addEventListener("click", () => {
    setView("map");
    writeAddress();
  });
  $("show-list").addEventListener("click", () => {
    setView("list", { focus: true });
    writeAddress();
  });
  // The skip link opens the list view first, so it also works on small screens where the
  // list is hidden behind the map. It leaves the address alone because the map keeps its
  // position there.
  document.querySelector(".skip").addEventListener("click", (event) => {
    event.preventDefault();
    if (!$("detail").hidden) closeDetail();
    if (!WIDE.matches && app.state.view !== "list") {
      setView("list");
      writeAddress();
    }
    $("list").focus();
  });
  $("close-detail").addEventListener("click", closeDetail);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !$("detail").hidden) closeDetail();
  });
  WIDE.addEventListener("change", () => {
    startPendingMap();
    if (!$("detail").hidden) coverPage(true);
  });
}

async function start() {
  if (hasFilterParams()) app.state = parse(window.location.search);
  else if (settings.isRemembered()) {
    app.state = settings.load() ?? defaults();
    app.savedOnly = true;
  }
  if (settings.isRemembered()) {
    app.theme = settings.theme();
    app.mine = new Set(settings.plans());
  }
  applyTheme();
  $("legend").open = WIDE.matches;
  trackHeaderHeight();
  wireUp();
  setUpSettings();
  setView(app.state.view);
  stateToForm();
  try {
    app.config = await loadJson("assets/config.json");
    const layer = await loadJson("data/locations.geojson");
    app.features = layer.features ?? [];
    for (const { properties } of app.features) {
      properties.band = speedBand(properties.kw);
      properties.down = allOut(properties);
    }
    try {
      const manifest = await loadJson("data/manifest.json");
      for (const [id, entry] of Object.entries(manifest.operators ?? {})) app.operators.set(id, entry.name);
    } catch {
      // operator names fall back to their ids
    }
    try {
      app.plans = (await loadJson("data/plans.json")).plans ?? [];
    } catch {
      app.plans = []; // the map works without the plan list
    }
    buildNetworks();
    buildPlanPicker();
    buildAttribution(layer);
  } catch {
    const failed = "The charger data could not be loaded. Please try again later.";
    $("list-summary").textContent = failed;
    notice(failed);
    return;
  }
  dropUnknownNetworks();
  stateToForm();
  writeAddress();
  applyFilters();
  if (mapVisible()) await startMap();
  else app.mapPending = true;
}

start();
