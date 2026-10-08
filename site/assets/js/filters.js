// Filter state: read from and written to the page address, and matched against the
// slim properties in data/locations.geojson. Nothing here touches storage.

import { PLUG_GROUPS, plugGroup } from "./format.js";

export const POWER_STEPS = [0, 7, 22, 50, 150];
export const MAX_PRICE_PENCE = 500;

export function defaults() {
  return { minkw: 0, plugs: [], free: false, maxp: null, unknown: true, ops: [], view: "map" };
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
  state.plugs = list(params.get("plug"), (p) => Object.hasOwn(PLUG_GROUPS, p));
  state.free = params.get("free") === "1";
  const maxp = params.get("maxp");
  if (maxp !== null && maxp.trim() !== "") {
    const value = Number(maxp);
    if (Number.isFinite(value) && value >= 0 && value <= MAX_PRICE_PENCE) state.maxp = value;
  }
  state.unknown = params.get("unknown") !== "0";
  state.ops = list(params.get("op"), (op) => /^[a-z0-9_]{1,40}$/.test(op));
  state.view = params.get("view") === "list" ? "list" : "map";
  return state;
}

// Only values that differ from the defaults, in a fixed order, so addresses stay short.
export function serialise(state) {
  const params = new URLSearchParams();
  if (state.minkw) params.set("minkw", String(state.minkw));
  if (state.plugs.length) params.set("plug", [...state.plugs].sort().join(","));
  if (state.free) params.set("free", "1");
  if (state.maxp !== null) params.set("maxp", String(state.maxp));
  if (!state.unknown) params.set("unknown", "0");
  if (state.ops.length) params.set("op", [...state.ops].sort().join(","));
  if (state.view === "list") params.set("view", "list");
  return params.toString();
}

function priceKnown(props) {
  return props.price === "free" || (props.ppk !== null && props.ppk !== undefined);
}

export function matches(props, state) {
  if (state.minkw && !(Number.isFinite(props.kw) && props.kw >= state.minkw)) return false;
  if (state.plugs.length) {
    const groups = new Set((props.plugs ?? []).map(plugGroup));
    if (!state.plugs.some((plug) => groups.has(plug))) return false;
  }
  if (state.ops.length && !state.ops.includes(props.op)) return false;
  if (state.free && props.price !== "free") return false;
  if (!state.unknown && !priceKnown(props)) return false;
  if (state.maxp !== null && priceKnown(props)) {
    const ppk = props.price === "free" ? 0 : Number(props.ppk);
    if (ppk > state.maxp) return false;
  }
  return true;
}
