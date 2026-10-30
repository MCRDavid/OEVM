// Filter state: read from and written to the page address, and matched against the
// slim properties in data/locations.geojson. Nothing here touches storage.

import { PLUG_GROUPS, plugGroup } from "./format.js";

export const POWER_STEPS = [0, 7, 11, 22, 50, 100, 150, 300];
export const CURRENTS = ["ac", "dc"];
export const MAX_PRICE_PENCE = 500;

// cur: only connectors the feed marks AC, or only DC (cur in schema/published.py); empty
// for both.
// priv: show locations marked private or restricted, or taxis only at every charge point
// (hidden unless asked for, ADR 0023).
// group: draw nearby chargers as numbered circles on the map. It changes how the map
// looks, not which chargers match, so it is not counted as a filter.
export function defaults() {
  return {
    minkw: 0,
    cur: "",
    plugs: [],
    free: false,
    maxp: null,
    unknown: true,
    working: false,
    priv: false,
    ops: [],
    group: true,
    view: "map",
  };
}

function list(value, allowed) {
  if (!value) return [];
  const items = value.split(",").filter((item) => allowed(item));
  return [...new Set(items)].sort();
}

// Unknown or out-of-range values are ignored, never guessed.
export function parse(search) {
  const params = new URLSearchParams(search);
  const state = defaults();
  const minkw = Number(params.get("minkw"));
  if (POWER_STEPS.includes(minkw)) state.minkw = minkw;
  if (CURRENTS.includes(params.get("cur"))) state.cur = params.get("cur");
  state.plugs = list(params.get("plug"), (p) => Object.hasOwn(PLUG_GROUPS, p));
  state.free = params.get("free") === "1";
  const maxp = params.get("maxp");
  if (maxp !== null && maxp.trim() !== "") {
    const value = Number(maxp);
    if (Number.isFinite(value) && value >= 0 && value <= MAX_PRICE_PENCE) state.maxp = value;
  }
  state.unknown = params.get("unknown") !== "0";
  state.working = params.get("ok") === "1";
  state.priv = params.get("priv") === "1";
  state.group = params.get("group") !== "0";
  state.ops = list(params.get("op"), (op) => /^[a-z0-9_]{1,40}$/.test(op));
  state.view = params.get("view") === "list" ? "list" : "map";
  return state;
}

// Only values that differ from the defaults, in a fixed order, so addresses stay short.
export function serialise(state) {
  const params = new URLSearchParams();
  if (state.minkw) params.set("minkw", String(state.minkw));
  if (state.cur) params.set("cur", state.cur);
  if (state.plugs.length) params.set("plug", [...state.plugs].sort().join(","));
  if (state.free) params.set("free", "1");
  if (state.maxp !== null) params.set("maxp", String(state.maxp));
  if (!state.unknown) params.set("unknown", "0");
  if (state.working) params.set("ok", "1");
  if (state.priv) params.set("priv", "1");
  if (state.ops.length) params.set("op", [...state.ops].sort().join(","));
  if (!state.group) params.set("group", "0");
  if (state.view === "list") params.set("view", "list");
  return params.toString();
}

// The conditions below apply to one connector at a time: a location matches when one of
// its connectors meets all of them, so a fast connector's power is never paired with a
// slow connector's price. Each entry in props.cons is one kind of connector (see
// schema/published.py, ConnectorSummary).
function priceKnown(connector) {
  return connector.price === "free" || (connector.ppk !== null && connector.ppk !== undefined);
}

export function connectorMatches(connector, state) {
  if (state.working && connector.out === true) return false;
  if (state.minkw && !(Number.isFinite(connector.kw) && connector.kw >= state.minkw)) return false;
  if (state.cur && connector.cur !== state.cur) return false;
  if (state.plugs.length && !(connector.std && state.plugs.includes(plugGroup(connector.std)))) return false;
  if (state.free && connector.price !== "free") return false;
  if (!state.unknown && !priceKnown(connector)) return false;
  if (state.maxp !== null && priceKnown(connector)) {
    const ppk = connector.price === "free" ? 0 : Number(connector.ppk);
    if (ppk > state.maxp) return false;
  }
  return true;
}

export function connectorFilters(state) {
  return Boolean(
    state.minkw ||
      state.cur ||
      state.plugs.length ||
      state.free ||
      state.maxp !== null ||
      !state.unknown ||
      state.working,
  );
}

// How many filters differ from the defaults, for the count on the Filters button.
export function activeCount(state) {
  return [
    state.minkw,
    state.cur,
    state.plugs.length,
    state.free,
    state.maxp !== null,
    !state.unknown,
    state.working,
    state.priv,
    state.ops.length,
  ].filter(Boolean).length;
}

// A location with no connectors listed is treated as one connector about which nothing is
// known, so "include unknown prices" keeps it while any other connector condition drops it.
const NOTHING_KNOWN = [{ std: null, kw: null, cur: null, price: "unknown", ppk: null, out: false }];

export function matches(props, state) {
  if ((props.priv || props.taxi) && !state.priv) return false;
  if (state.ops.length && !state.ops.includes(props.op)) return false;
  if (!connectorFilters(state)) return true;
  const cons = props.cons?.length ? props.cons : NOTHING_KNOWN;
  return cons.some((connector) => connectorMatches(connector, state));
}
