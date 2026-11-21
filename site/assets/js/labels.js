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
//   taxis, off-peak hours or one council area, for example);
// - the visitor's own rate for this network (rates.js, ADR 0035), typed in under "Your own
//   rates", and what each of their own cards that works on this network charges there
//   (cards.js), typed in under "Your own cards": AC figures for AC connectors and DC
//   figures for DC connectors, from the feed's power_type. A connector whose feed gives
//   no power_type gets neither. A card's percentage off is taken off the connector's own
//   published price including VAT, and gives nothing where there is none.
// Only connectors that match the visitor's filters count, so a rapid charger's label is
// never a slow connector's price, and no price above the visitor's maximum price per kWh
// is shown (a price whose VAT is not stated could only be higher with VAT). Free comes
// first, then the lowest figure, whether or not its VAT is stated: the pipeline adds VAT
// only where the owner decided so for an operator (vat_not_stated), and a higher price
// including VAT could be the dearer one. On a tie, a price including VAT comes before one
// whose VAT is not stated, and a price that applies all the time before one that applies
// only in some cases.

import { bestOffer } from "./cards.js";
import { connectorMatches } from "./filters.js";

function finite(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function fromPlan(plan) {
  const lvar = Boolean(plan.only_at_some_times);
  return { free: false, value: plan.ppk, text: plan.label, lvat: true, lvar, plan };
}

// For each network, the ticked plan with the lowest fixed price including VAT, and on a
// tie one that applies all the time. Plans that give a discount, no price, or a price
// whose VAT is not stated are skipped.
export function bestPlans(plans, mine) {
  const best = new Map();
  for (const plan of plans ?? []) {
    if (!mine?.has(plan.id) || !finite(plan.ppk) || !plan.label) continue;
    for (const op of plan.operator_ids ?? []) {
      const current = best.get(op);
      if (!current || lower(fromPlan(plan), fromPlan(current)) < 0) best.set(op, plan);
    }
  }
  return best;
}

// The visitor's own price for one connector, by whether it is AC or DC. own is either
// their own rate for the network ({ ac, dc, note } in pence) or their offers for it from
// ownOffers in cards.js ({ ac, dc } as lists).
function fromRate(own, connector) {
  const cur = connector.cur;
  if (cur !== "ac" && cur !== "dc") return null;
  const list = Array.isArray(own[cur])
    ? own[cur]
    : finite(own[cur])
      ? [{ pence: own[cur], card: null, note: own.note ?? "" }]
      : [];
  const published = connector.price === "priced" && connector.lvat && finite(connector.low) ? connector.low : null;
  const best = bestOffer(list, cur, published);
  if (!best) return null;
  // A percentage off a price that applies only in some cases applies only in those too.
  const lvar = best.pct !== null && Boolean(connector.lvar);
  return { free: false, value: best.value, text: `${best.value}p`, lvat: true, lvar, rate: { op: own.op, ...best } };
}

function underLimit(found, state) {
  return found.free || state.maxp == null || found.value <= state.maxp;
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
// only in some cases.
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

// The label for one location, as { text, key, low, lvat, plan, rate }, or null when no
// price can be shown. key orders labels cheapest first; plan is the ticked plan the price
// comes from, if it does, and rate the visitor's own figure, if it does: { op, value,
// cur ("ac" or "dc"), card (the card's name, or null for their own rate for the
// network), note, pct (the percentage off, or null for a price typed in) }. A plan or rate counts only where a connector matches the filters, and only when
// it comes first in the order above: on a full tie the operator's own price is kept, as
// it needs nothing more, and then a ticked plan's.
export function priceLabel(props, state, plan = null, rate = null) {
  let best = null;
  let matched = false;
  const own = [];
  const consider = (found) => {
    if (found && underLimit(found, state) && (!best || lower(found, best) < 0)) best = found;
  };
  for (const connector of props.cons ?? []) {
    if (!connectorMatches(connector, state)) continue;
    matched = true;
    consider(candidate(connector));
    if (rate) own.push(fromRate(rate, connector));
  }
  if (matched && plan && finite(plan.ppk) && plan.label) consider(fromPlan(plan));
  own.forEach(consider);
  if (!best) return null;
  return {
    text: best.text,
    key: sortKey(best),
    low: best.free ? null : best.value,
    lvat: best.free ? null : best.lvat,
    plan: best.plan ?? null,
    rate: best.rate ?? null,
  };
}
