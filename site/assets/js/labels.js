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
// never a slow connector's price. Free comes first, then the lowest figure, whether or not
// its VAT is stated: VAT is never added, and a higher price including VAT could be the
// dearer one. On a tie, a price including VAT comes before one whose VAT is not stated,
// and a price that applies all the time before one that applies only at some times.

import { connectorMatches } from "./filters.js";

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
  if (connector.price === "free") return { free: true, value: 0, text: connector.lt };
  if (!finite(connector.low)) return null;
  return {
    free: false,
    value: connector.low,
    text: connector.lt,
    lvat: Boolean(connector.lvat),
    lvar: Boolean(connector.lvar),
  };
}

// Negative when a is the better label: free, then lower, then including VAT, then not
// only at some times.
function lower(a, b) {
  return (
    Number(b.free) - Number(a.free) ||
    a.value - b.value ||
    Number(b.lvat) - Number(a.lvat) ||
    Number(a.lvar) - Number(b.lvar)
  );
}

// The map draws labels with a lower key first, where they would overlap. Prices are in
// tenths of a penny, so the tie breaks fit between them.
function sortKey(best) {
  if (best.free) return 0;
  return 1 + Math.round(best.value * 10) * 4 + (best.lvat ? 0 : 2) + (best.lvar ? 1 : 0);
}

// The label for one location, as { text, key, low, lvat, plan }, or null when no price
// can be shown. key orders labels cheapest first; plan is the ticked plan the price comes
// from, if it does. A plan counts only where a connector matches the filters, and only
// when it is lower: on a tie the operator's own price is kept, as it needs no plan.
export function priceLabel(props, state, plan = null) {
  let best = null;
  let matched = false;
  for (const connector of props.cons ?? []) {
    if (!connectorMatches(connector, state)) continue;
    matched = true;
    const found = candidate(connector);
    if (found && (!best || lower(found, best) < 0)) best = found;
  }
  const planCounts = matched && plan && finite(plan.ppk) && plan.label;
  if (planCounts && (!best || (!best.free && plan.ppk < best.value))) {
    best = {
      free: false,
      value: plan.ppk,
      text: plan.label,
      lvat: true,
      lvar: Boolean(plan.only_at_some_times),
      plan,
    };
  }
  if (!best) return null;
  return {
    text: best.text,
    key: sortKey(best),
    low: best.free ? null : best.value,
    lvat: best.free ? null : best.lvat,
    plan: best.plan ?? null,
  };
}
