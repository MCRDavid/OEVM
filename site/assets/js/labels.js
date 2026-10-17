// The price label drawn above each point on the map, and next to each charger in the list
// (ADR 0026): the cheapest price per kWh the visitor can pay there. Labels are worded by
// the pipeline (pipeline/pricing.py); this file only picks one.
//
// It is the lowest of:
// - each connector's own label: "Free" when the operator confirms it is free, otherwise the
//   lowest price per kWh among every tariff the connector lists, so paying with the
//   operator's app or account counts as well as paying at the charger by card;
// - the fixed price per kWh, including VAT, of a charging plan the visitor ticked under
//   "Your charging plans" that covers this network. Discounts are never turned into
//   prices (ADR 0016), and plans nobody ticked are left out, because many are limited (to
//   taxis, off-peak hours or one council area, for example).
// Only connectors that match the visitor's filters count, so a rapid charger's label is
// never a slow connector's price. Free comes first, then prices including VAT from lowest
// to highest, then prices whose VAT is not stated, which cannot be compared fairly with
// the others, the same order as a site's details (pipeline/tariffs.py).

import { connectorMatches } from "./filters.js";

const FREE = 0;
const WITH_VAT = 1;
const VAT_NOT_STATED = 2;
// Ranks are kept apart in the sort key, which also decides which labels the map shows
// first where they would overlap.
const RANK_STEP = 10000;

function finite(value) {
  return typeof value === "number" && Number.isFinite(value);
}

// For each network, the ticked plan with the lowest fixed price including VAT. Plans that
// give a discount, no price, or a price whose VAT is not stated are skipped.
export function bestPlans(plans, mine) {
  const best = new Map();
  for (const plan of plans ?? []) {
    if (!mine?.has(plan.id) || !finite(plan.ppk) || !plan.label) continue;
    for (const op of plan.operator_ids ?? []) {
      const current = best.get(op);
      if (!current || plan.ppk < current.ppk) best.set(op, plan);
    }
  }
  return best;
}

function candidate(connector) {
  if (!connector.lt) return null;
  if (connector.price === "free") return { rank: FREE, value: 0, text: connector.lt };
  if (!finite(connector.low)) return null;
  return {
    rank: connector.lvat ? WITH_VAT : VAT_NOT_STATED,
    value: connector.low,
    text: connector.lt,
    low: connector.low,
    lvat: Boolean(connector.lvat),
  };
}

function lower(a, b) {
  return a.rank - b.rank || a.value - b.value;
}

// The label for one location, as { text, key, low, lvat, plan }, or null when no price
// can be shown. key orders labels cheapest first; plan is the ticked plan the price comes
// from, if it does. A plan counts only where a connector matches the filters, and on a
// tie the operator's own price is kept, as it needs no plan.
export function priceLabel(props, state, plan = null) {
  let best = null;
  let matched = false;
  for (const connector of props.cons ?? []) {
    if (!connectorMatches(connector, state)) continue;
    matched = true;
    const found = candidate(connector);
    if (found && (!best || lower(found, best) < 0)) best = found;
  }
  if (matched && plan && finite(plan.ppk) && plan.label) {
    const fromPlan = { rank: WITH_VAT, value: plan.ppk, text: plan.label, low: plan.ppk, lvat: true, plan };
    if (!best || lower(fromPlan, best) < 0) best = fromPlan;
  }
  if (!best) return null;
  return {
    text: best.text,
    key: best.rank * RANK_STEP + best.value,
    low: best.low ?? null,
    lvat: best.lvat ?? null,
    plan: best.plan ?? null,
  };
}
