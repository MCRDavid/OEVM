// The details panel for one location, built from data/loc/<shard>/<key>.json.
//
// The panel says each thing once, in the order a driver needs it: where the charger is,
// whether its charge points are free, the cheapest price, then each kind of charge point
// with its price once and one line per charge point. What fewer people need (every
// tariff, other ways to pay, where the data comes from, reference numbers) opens when
// asked for. Nothing is left out of the data: the detail file is unchanged.

import { h, safeLink } from "./dom.js";
import { STATUS_LABELS, formatDateTime, formatKw, formatShortDateTime, plugName } from "./format.js";
import { STATUS_GROUPS, asOfText, chips, countByGroup, groupOf, summaryText } from "./live.js";
import { subscriptionCalculator } from "./calculator.js";
import {
  cheaperFor,
  cheaperParts,
  cheapest,
  lowestWithVat,
  needsSubscription,
  payNowHint,
  payNowStart,
  plansFor,
  withheldFor,
  withheldParts,
} from "./plans.js";
import { cardAsPlan, cardTextFor, ownOffers } from "./cards.js";
import { rateSummary } from "./rates.js";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];
// UNSTATED_KIND in pipeline/pricing.py: a tariff whose feed does not say how it is paid for.
export const UNSTATED_KIND = "How to pay is not stated";

export function detailUrl(key) {
  if (!/^[0-9a-f]{16}$/.test(key)) throw new Error("not a location key");
  return `data/loc/${key.slice(0, 2)}/${key}.json`;
}

function osmLink(latitude, longitude) {
  const url = new URL("https://www.openstreetmap.org/");
  url.searchParams.set("mlat", String(latitude));
  url.searchParams.set("mlon", String(longitude));
  url.hash = `map=18/${latitude}/${longitude}`;
  return url.href;
}

function address(location) {
  const a = location.address ?? {};
  return [a.street, a.city, a.postal_code].filter(Boolean).join(", ") || "Address not given";
}

function openingHours(hours) {
  if (!hours) return h("p", { text: "Opening hours not given." });
  if (hours.twenty_four_seven) return h("p", { text: "Open 24 hours." });
  return h(
    "ul",
    { className: "hours", "aria-label": "Opening hours" },
    (hours.regular_hours ?? []).map((r) =>
      h("li", { text: `${WEEKDAYS[r.weekday - 1] ?? "Day " + r.weekday}: ${r.period_begin} to ${r.period_end}` }),
    ),
  );
}

function priceFor(prices, evse, connector) {
  return prices.find((p) => p.evse_uid === evse.uid && p.connector_id === connector.id);
}

// A copy the operator sent says nothing about now, so no status is shown (ADR 0029). The
// short note says it is a copy and when it was made; the full note is under "More about
// this data".
export function sentCopyText(detail) {
  const name = detail.location?.operator?.name ?? "the operator";
  return `A copy ${name} sent, made ${formatDateTime(detail.fetched_at)} and not updated since. Charge point status is not shown.`;
}

// How many charge points are free, in use, out of service or unknown, coloured, and when
// the operator's feed was read: at the daily fetch, or at a status refresh since
// (detail.status_read_at, set by withLiveStatuses in live.js; ADR 0032).
// Given onHideOut, the out of service count is a button that switches the map's "Hide out of service"
// filter (ADR 0012) on or off, as the owner chose on 10 October 2026.
export function statusSection(detail, { hideOut = false, onHideOut = null } = {}) {
  const counts = countByGroup(detail.location?.evses);
  if (!counts.total || detail.sent_copy) return [];
  const all = chips(counts);
  const filterButton = onHideOut && all.some((chip) => chip.group === "out");
  const chip = ({ group, className, symbol, text }) => {
    const parts = [h("span", { "aria-hidden": "true", text: `${symbol} ` }), text];
    if (!(filterButton && group === "out")) return h("span", { className }, ...parts);
    return h(
      "button",
      {
        type: "button",
        className,
        "data-filter": "working",
        // The name says what pressing it does, and still contains the visible words.
        "aria-label": `Hide out of service: ${text}`,
        "aria-pressed": String(Boolean(hideOut)),
        "aria-describedby": "status-filter-hint",
        onClick: onHideOut,
      },
      ...parts,
    );
  };
  return [
    h("h3", { className: "visually-hidden", text: "Charge point status" }),
    // The counts in words, for screen readers; the chips below say the same.
    h("p", { className: "visually-hidden status-summary", text: summaryText(counts) }),
    h("p", { className: "status-chips" }, all.map(chip)),
    h("p", { className: "hint", text: `${asOfText(detail.status_read_at ?? detail.fetched_at)}.` }),
    filterButton
      ? h("p", {
          className: "hint",
          id: "status-filter-hint",
          text: "Press \"reported out of service\" to hide or show such chargers on the map and in the list.",
        })
      : null,
  ].filter(Boolean);
}

// OCPI 2.2.1 parking restrictions, worded for drivers (ADR 0023).
const PARKING = {
  ev_only: "electric vehicles only",
  plugged: "only while plugged in and charging",
  disabled: "Blue Badge holders only",
  customers: "customers only",
  motorcycles: "electric motorcycles and scooters only",
  // Not an OCPI value: read so only by the owner's decision in an operator file.
  taxis_only: "taxis only",
};

export function parkingRules(evse) {
  const rules = (evse.parking_restrictions ?? []).map((r) => PARKING[r]).filter(Boolean);
  return rules.length ? rules.join("; ") : null;
}

// OCPI 2.2.1 parking types, worded for drivers (ADR 0030). Shown as the operator's
// statement, because some feeds give one type for every site.
const PARKING_TYPES = {
  along_motorway: "motorway services or rest area",
  parking_garage: "multi-storey car park",
  parking_lot: "car park",
  on_driveway: "driveway",
  on_street: "on the street",
  underground_garage: "underground car park",
};

export function parkingTypeName(location) {
  return PARKING_TYPES[location.parking_type] ?? null;
}

// OCPI 2.2.1 capabilities that say the charge point has a payment terminal, worded for
// drivers (ADR 0030). Shown only as the operator's statement, and only when present: no
// capability listed is not taken to mean no card payment.
const PAYMENT = {
  contactless_card_support: "contactless",
  credit_card_payable: "credit card",
  debit_card_payable: "debit card",
  chip_card_support: "chip card",
  ped_terminal: "PIN pad",
};

export function paymentWays(evse) {
  const ways = Object.keys(PAYMENT).filter((c) => (evse.capabilities ?? []).includes(c));
  return ways.length ? ways.map((c) => PAYMENT[c]).join(", ") : null;
}

// The parking type, card payment and floor level as the operator's feed gives them, in one
// line that says they are the operator's statement (ADR 0030). The floor level is as
// published (OCPI floor_level), and not given for operators whose values the owner
// decided are not levels. null when the feed gives none of them.
export function operatorSays({ parkingType = null, payment = null, floor = null }) {
  const parts = [parkingType, payment ? `card payment (${payment})` : null, floor ? `floor level ${floor}` : null];
  const said = parts.filter(Boolean);
  return said.length ? `The operator says: ${said.join("; ")}.` : null;
}

// A charge point's name: the label the operator says is on it (OCPI physical_reference),
// else its EVSE ID, else its place in the operator's list.
export function chargePointName(evse, index) {
  return evse.physical_reference || evse.evse_id || `Charge point ${index + 1}`;
}

// The operator's own notes (OCPI directions), such as parking rules or car park hours,
// shown as text exactly as published (ADR 0030). A note that every charge point here has
// is shown once, with the site's own.
export function siteNotes(location) {
  const evses = location.evses ?? [];
  const first = evses[0]?.directions;
  const shared = first && evses.every((evse) => evse.directions === first) ? first : null;
  return [...new Set([location.directions, shared].filter(Boolean))];
}

function notesSection(notes) {
  if (!notes.length) return [];
  return [
    h("h3", { text: "Operator's notes" }),
    ...notes.map((note) => h("p", { className: "notes", text: note })),
    h("p", { className: "hint", text: "As published, and may be out of date." }),
  ];
}

// What every charge point here has in common, said once with the site, or null where
// they differ or the feed gives nothing.
function sharedBy(evses, read) {
  const values = new Set(evses.map(read));
  return values.size === 1 ? [...values][0] : null;
}

// What one charge point offers: its connectors, fastest first, each with its power and
// price, and what the operator says about parking, payment, floor and access there.
// `shared` holds what is already said once for the whole site.
function offerOf(evse, prices, shownNotes, shared) {
  const connectors = (evse.connectors ?? [])
    .map((connector) => {
      const price = priceFor(prices, evse, connector);
      return {
        plug: plugName(connector.standard),
        kw: formatKw(connector.max_kw),
        power: Number.isFinite(connector.max_kw) ? connector.max_kw : -1,
        // Power this project worked out from a voltage other than the one published, by
        // the owner's decision in the operator file (line_to_line_voltage, ADR 0031).
        kwNote: connector.max_kw_note ?? null,
        price: price ? price.text : "Price unknown",
        reason: price?.reason ?? null,
      };
    })
    .sort((a, b) => b.power - a.power || a.plug.localeCompare(b.plug));
  return {
    connectors,
    parking: shared.parking ? null : parkingRules(evse),
    payment: shared.payment ? null : paymentWays(evse),
    floor: shared.floor ? null : evse.floor_level || null,
    note: evse.directions && !shownNotes.includes(evse.directions) ? evse.directions : null,
  };
}

// Names in the order people expect: letters A to Z whatever their case, and numbers in
// number order, so "2" comes before "10" and "01-2" before "02-1".
const byName = new Intl.Collator("en-GB", { numeric: true, sensitivity: "base" });

// Charge points by their names as shown, then by EVSE ID, then in the operator's order.
function pointOrder(a, b) {
  return (
    byName.compare(chargePointName(a.evse, a.index), chargePointName(b.evse, b.index)) ||
    byName.compare(a.evse.evse_id ?? "", b.evse.evse_id ?? "") ||
    a.index - b.index
  );
}

// Charge points (OCPI EVSEs) that offer the same thing, kept together, so the connectors
// and the price are said once and each charge point then has one line with its own name
// and status. A charge point charges one vehicle at a time, whichever of its connectors
// is used. Charge points are in order of their names (owner, 16 November 2026), and so
// are the groups, by the first charge point in each.
export function chargePointGroups(evses, prices, shownNotes = [], shared = {}) {
  const groups = new Map();
  (evses ?? []).forEach((evse, index) => {
    const offer = offerOf(evse, prices ?? [], shownNotes, shared);
    const key = JSON.stringify(offer);
    if (!groups.has(key)) groups.set(key, { offer, points: [] });
    groups.get(key).points.push({ evse, index });
  });
  const sorted = [...groups.values()];
  for (const group of sorted) group.points.sort(pointOrder);
  return sorted.sort((a, b) => pointOrder(a.points[0], b.points[0]));
}

// One line for a charge point: its name, its status in its group's colour with the group's
// symbol, so colour is never the only cue, and when the operator reported it.
// Where two charge points in one box share a name, each also shows its EVSE ID, so they
// can be told apart.
function pointRow({ evse, index }, detail, repeated) {
  const label = chargePointName(evse, index);
  const id = repeated.has(label) && evse.evse_id && evse.evse_id !== label ? ` (${evse.evse_id})` : "";
  const name = h("span", { className: "charge-point-name", text: `${label}${id}` });
  if (detail.sent_copy) return h("li", {}, name);
  const known = Object.hasOwn(STATUS_LABELS, evse.status) ? evse.status : "unknown";
  const group = groupOf(known);
  const when = formatShortDateTime(evse.status_at, detail.status_read_at ?? detail.fetched_at);
  return h(
    "li",
    {},
    name,
    h(
      "span",
      { className: `status status-${group.replace("_", "-")}` },
      h("span", { "aria-hidden": "true", text: `${STATUS_GROUPS[group].symbol} ` }),
      STATUS_LABELS[known],
    ),
    known === "unknown" ? null : h("span", { className: "hint", text: `reported ${when ?? "date not given"}` }),
  );
}

function groupItem({ offer, points }, detail) {
  const names = points.map(({ evse, index }) => chargePointName(evse, index));
  const repeated = new Set(names.filter((name, i) => names.indexOf(name) !== i));
  const [first] = offer.connectors;
  const onePrice = offer.connectors.every((c) => c.price === first.price && c.reason === first.reason);
  const priceLine = (c) =>
    h("p", { className: "price" }, c.price, c.reason ? h("span", { className: "hint", text: ` ${c.reason}` }) : null);
  const says = operatorSays({ payment: offer.payment, floor: offer.floor });
  const each = points.length > 1 ? " on each charge point" : "";
  return h(
    "li",
    { className: "charge-point-group" },
    offer.connectors.length
      ? offer.connectors.flatMap((c) => [
          h("p", { className: "plug" }, h("strong", { text: c.plug }), ` · ${c.kw}`),
          c.kwNote ? h("p", { className: "hint", text: c.kwNote }) : null,
          onePrice ? null : priceLine(c),
        ])
      : h("p", { text: "No connectors listed by the operator." }),
    onePrice && first ? priceLine(first) : null,
    offer.connectors.length > 1
      ? h("p", { className: "hint", text: `${offer.connectors.length} connectors${each}, one vehicle at a time.` })
      : null,
    offer.parking ? h("p", { className: "parking", text: `Parking: ${offer.parking}.` }) : null,
    says ? h("p", { className: "hint says", text: says }) : null,
    offer.note ? h("p", { className: "notes", text: `Operator's note: ${offer.note}` }) : null,
    h(
      "ul",
      { className: "charge-points", "aria-label": `Charge points with ${offer.connectors.map((c) => c.plug).join(" and ") || "no connectors listed"}` },
      points.map((point) => pointRow(point, detail, repeated)),
    ),
  );
}

// The operator's own references for the location, each charge point and each renamed
// tariff, to quote when reporting a fault or a mistake. Last under "More about this data".
function referenceNote(detail) {
  const location = detail.location;
  const site = location.id.split(":").slice(3).join(":");
  const network = location.operator?.name ?? "the operator";
  const renamed = (detail.tariff_options ?? []).filter((option) => option.original_name);
  return h(
    "div",
    { className: "references" },
    h("h4", { text: "Reference numbers" }),
    h(
      "ul",
      { className: "hint", "aria-label": "Reference numbers" },
      h("li", { text: `Site: ${site} in ${network}'s feed (on this map: ${location.id}).` }),
      (location.evses ?? [])
        .map((evse, index) => ({ evse, index }))
        .sort(pointOrder)
        .map(({ evse, index }) => {
          const name = chargePointName(evse, index);
          const parts = [evse.evse_id && evse.evse_id !== name ? `EVSE ID ${evse.evse_id}` : null, `uid ${evse.uid}`];
          return h("li", { text: `${name}: ${parts.filter(Boolean).join(", ")}.` });
        }),
      renamed.map((option) => h("li", { text: `Tariff "${option.name}": the operator's name for it is ${option.original_name}.` })),
    ),
  );
}

// Every tariff the site's connectors list, so people can compare them, opened when asked
// for. Shown only when there is more than one: with a single tariff the charge points
// already say it all. Every price is worded by the pipeline (pipeline/pricing.py), which
// also puts them cheapest first.
export function tariffSection(detail) {
  const options = detail.tariff_options ?? [];
  if (options.length < 2) return [];
  const total = (detail.location?.evses ?? []).reduce((n, e) => n + (e.connectors?.length ?? 0), 0);
  const bases = new Set(options.filter((o) => o.state === "priced").map((o) => Boolean(o.includes_vat)));
  const items = options.map((option) =>
    h(
      "li",
      {},
      h("p", {}, h("strong", { text: option.name || option.kind })),
      option.name ? h("p", { className: "hint", text: option.kind }) : null,
      h("p", { className: "price", text: option.text }),
      option.reason ? h("p", { className: "hint", text: option.reason }) : null,
      option.published_by ? h("p", { className: "hint", text: `Published in ${option.published_by}'s tariff data.` }) : null,
      option.connectors < total
        ? h("p", { className: "hint", text: `Listed for ${option.connectors} of ${total} connectors.` })
        : null,
    ),
  );
  return [
    h(
      "details",
      { className: "more" },
      h("summary", { text: `All ${options.length} tariffs listed here` }),
      h("p", {
        className: "hint",
        text:
          bases.size > 1
            ? "Cheapest first, by price per kWh. Prices with VAT not stated come after those including VAT."
            : "Cheapest first, by price per kWh.",
      }),
      h("ul", { className: "tariffs", "aria-label": "Tariffs listed here" }, items),
    ),
  ];
}

const CHECKED = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "short", year: "numeric", timeZone: "UTC" });

function checkedDate(iso) {
  const when = new Date(`${iso}T00:00:00Z`);
  return Number.isNaN(when.getTime()) ? "date not given" : CHECKED.format(when);
}

function planItem(plan, mine) {
  return h(
    "li",
    {},
    h("p", {}, h("strong", { text: plan.name }), ` · ${plan.provider}`),
    mine.has(plan.id) ? h("p", { className: "mine", text: "You have this plan" }) : null,
    h("p", { className: "price", text: `${plan.price_text} · ${plan.fee_text}` }),
    h("p", { className: "hint", text: plan.pay_by }),
    plan.fee_note ? h("p", { className: "hint", text: plan.fee_note }) : null,
    plan.conditions ? h("p", { className: "hint", text: plan.conditions }) : null,
    plan.needs_testing ? h("p", { className: "hint", text: `Needs testing: ${plan.needs_testing}` }) : null,
    h("p", { className: "hint" }, safeLink(plan.source_url, "Provider's page"), `, checked ${checkedDate(plan.checked)}.`),
    plan.attribution ? h("p", { className: "hint", text: plan.attribution }) : null,
  );
}

// The plan that gives the lowest published energy price here, when one beats every tariff
// listed here; null when a listed tariff is as cheap or no plan gives a fixed price.
function bestPlan(detail, plans) {
  const best = cheapest(detail.tariff_options, plans);
  return best?.kind === "plan" ? best.item : null;
}

function planLine(plan, label) {
  return h("p", {
    className: "cheapest",
    text: `${label}: ${plan.price_text}, ${plan.name} from ${plan.provider} (${plan.fee_text.toLowerCase()}).`,
  });
}

// The currents ("ac", "dc") of this location's connectors, from the feed's power_type.
function currentsHere(location) {
  const currents = new Set();
  for (const evse of location?.evses ?? []) {
    for (const connector of evse.connectors ?? []) {
      const type = connector.power_type ?? "";
      if (type === "dc") currents.add("dc");
      else if (type.startsWith("ac_")) currents.add("ac");
    }
  }
  return [...currents];
}

// The subscription calculator for this location. "What you pay now" starts from the
// lowest price the visitor has here: a published price including VAT, a ticked plan with
// no monthly fee, or their own rate or card with no monthly fee for this network; they
// can change any figure.
function calculator(detail, plans, mine, rate) {
  const start = payNowStart({
    tariffOptions: detail.tariff_options,
    ticked: plans.filter((plan) => mine.has(plan.id)),
    rate,
    currents: currentsHere(detail.location),
  });
  return subscriptionCalculator({
    plans,
    summary: "Is a subscription worth it here?",
    payNow: start?.ppk ?? null,
    nowHint: payNowHint(start),
  });
}

function linked(parts) {
  return parts.map((part) => (typeof part === "string" ? part : safeLink(part.url, part.text)));
}

// Where the operator's own terms keep its memberships or subscriptions off the map.
function withheldNote(entry) {
  return h("p", { className: "hint withheld" }, ...linked(withheldParts(entry)));
}

// Where paying the operator directly is cheaper than paying at the charger, said under the
// cheapest price without the price itself (ADR 0034). It takes the place of the note above.
export function cheaperSection(detail, withheld = []) {
  const operatorId = detail.location?.provenance?.source_id;
  return withheldFor(operatorId, withheld).flatMap((entry) => {
    const items = cheaperFor(entry, detail.location);
    if (!items.length) return [];
    return [
      h(
        "div",
        { className: "cheaper-direct" },
        ...items.map((item) => h("p", {}, h("strong", { text: item.headline }), ` ${item.text}`)),
        h("p", { className: "hint" }, ...linked(cheaperParts(entry, items))),
      ),
    ];
  });
}

// The visitor's own rates for this network (rates.js, ADR 0035) and their own cards that
// work on it (cards.js), said to be theirs, with buttons to change them. op is this
// network's id, for each card's figures here. Where paying the operator directly is
// said to be cheaper (ADR 0034) and the visitor has typed in nothing for this network, a
// button offers to type in a rate.
export function ownRateSection(rate, { cards = [], op = null, cheaper = false, onEditRate = null, onEditCards = null } = {}) {
  if (rate || cards.length) {
    return [
      h(
        "div",
        { className: "own-rate" },
        rate
          ? h("p", {}, h("strong", { text: "Your own rates for this network: " }), `${rateSummary(rate)}${rate.note ? ` (${rate.note})` : ""}.`)
          : null,
        ...cards.map((card) => {
          const here = cardTextFor(card, op) || "no price typed in for this network";
          return h("p", {}, h("strong", { text: `Your card ${card.name}: ` }), `${here}${card.note ? ` (${card.note})` : ""}.`);
        }),
        h("p", { className: "hint", text: "Typed in by you and kept in this browser. This site has not checked them." }),
        rate && onEditRate ? h("button", { type: "button", className: "own-rate-edit", onClick: onEditRate, text: "Change your rates" }) : null,
        cards.length && onEditCards
          ? h("button", { type: "button", className: "own-rate-edit", onClick: onEditCards, text: "Change your cards" })
          : null,
      ),
    ];
  }
  if (!cheaper || !onEditRate) return [];
  return [
    h(
      "div",
      { className: "own-rate" },
      h("button", { type: "button", className: "own-rate-edit", onClick: onEditRate, text: "Type in a rate you found" }),
      h("p", { className: "hint", text: "It stays in this browser and is never sent anywhere." }),
    ),
  ];
}

// Plans from providers' own pages that cover this location's network, opened when asked
// for, with the calculator. A plan that beats every tariff listed here is said in one
// line above them. Where the operator's own plans cannot be shown because of its terms,
// a note says so. rate is the visitor's own figures for this network with no monthly fee,
// if any: their own rate (ADR 0035) or their offers from ownOffers in cards.js. ownPlans
// are their own cards with a monthly fee that work here, as plans (cardAsPlan), which
// the calculator offers too, after the listed plans.
export function plansSection(detail, allPlans, mine = new Set(), withheld = [], rate = null, ownPlans = []) {
  const operatorId = detail.location?.provenance?.source_id;
  const plans = plansFor(operatorId, allPlans);
  // An operator said to be cheaper to pay directly has that note under the cheapest price.
  const held = withheldFor(operatorId, withheld)
    .filter((entry) => !cheaperFor(entry, detail.location).length)
    .map(withheldNote);
  if (!plans.length) return [...held, ownPlans.length ? calculator(detail, ownPlans, mine, rate) : null].filter(Boolean);
  const free = plans.filter((plan) => !needsSubscription(plan));
  const paid = plans.filter(needsSubscription);
  const yours = bestPlan(
    detail,
    plans.filter((plan) => mine.has(plan.id)),
  );
  const any = bestPlan(detail, plans);
  const list = (label, items) =>
    h("ul", { className: "tariffs plans", "aria-label": label }, items.map((p) => planItem(p, mine)));
  return [
    yours ? planLine(yours, "With your plans") : null,
    any && any !== yours ? planLine(any, "With a listed plan") : null,
    h(
      "details",
      { className: "more" },
      h("summary", { text: `Other ways to pay here (${plans.length})` }),
      h("p", {
        className: "hint",
        text: "Copied by hand from each provider's own page on the date shown, cheapest first. Check with the provider before signing up.",
      }),
      ...(free.length
        ? [h("h4", { text: `No subscription needed (${free.length})` }), list("No subscription needed", free)]
        : []),
      ...(paid.length
        ? [h("h4", { text: `With a paid subscription (${paid.length})` }), list("With a paid subscription", paid)]
        : []),
      calculator(detail, [...plans, ...ownPlans], mine, rate),
    ),
    ...held,
  ].filter(Boolean);
}

// The price in the label above this location's point on the map, and next to it in the
// list (labels.js, ADR 0026), and how it is paid for. label is what priceLabel returned
// for this location; filtered says whether the visitor's filters leave out some
// connectors. How it is paid for is given only when every listed tariff that gives that
// price agrees on it and the feed states it.
export function mapLabelLine(detail, label, filtered = false) {
  if (!label) return null;
  let source;
  if (label.rate) {
    const own = label.rate;
    const note = own.note ? ` (${own.note})` : "";
    const cur = own.cur.toUpperCase();
    if (!own.card) source = ` per kWh with your own ${cur} rate for this network${note}, typed in by you.`;
    else if (own.pct != null) source = ` per kWh with your card ${own.card}${note}: ${own.pct}% off the published price, as you typed in.`;
    else source = ` per kWh with your card ${own.card}${note}: its ${cur} price, typed in by you.`;
  } else if (label.plan) {
    source = ` per kWh with your plan ${label.plan.name} from ${label.plan.provider} (${label.plan.fee_text.toLowerCase()}).`;
  } else if (label.low === null) {
    source = " on at least one connector, confirmed by the operator's tariff.";
  } else {
    const options = (detail.tariff_options ?? []).filter(
      (o) => o.state === "priced" && o.ppk_low === label.low && Boolean(o.includes_vat) === label.lvat,
    );
    const kind = options.length > 0 && options.every((o) => o.kind === options[0].kind) ? options[0].kind : UNSTATED_KIND;
    source = kind === UNSTATED_KIND ? " per kWh." : ` per kWh: ${kind[0].toLowerCase()}${kind.slice(1)}.`;
  }
  // A confirmed free tariff has no other charges, so the note about them is left off.
  const notes = [
    label.low !== null && label.lvat === false ? "VAT is not stated, so it may be higher." : null,
    label.low === null ? null : "Any other charges are not included.",
  ].filter(Boolean);
  return h(
    "p",
    { className: "map-label" },
    filtered ? "Cheapest for your filters: " : "Cheapest here: ",
    h("span", { className: `price-tag${label.plan || label.rate ? " with-plan" : ""}`, text: label.text }),
    `${source} `,
    notes.length ? h("span", { className: "hint", text: notes.join(" ") }) : null,
  );
}

// Where the data comes from, in full, and the reference numbers: opened when asked for.
// The attribution statements themselves stay in view above it.
function aboutSection(detail, { hasNotes }) {
  const provenance = detail.location.provenance ?? {};
  const sources = detail.tariff_sources ?? [];
  const licence = detail.licence_url ? safeLink(detail.licence_url, detail.licence) : detail.licence;
  return h(
    "details",
    { className: "more about" },
    h("summary", { text: "More about this data" }),
    ...(detail.sent_copy
      ? [
          h("p", { className: "sent-copy", text: detail.sent_copy.note }),
          h(
            "p",
            {},
            "Read from ",
            safeLink(detail.sent_copy.files_url, "the files the operator sent"),
            `, made ${formatDateTime(detail.fetched_at)}. Licence: `,
            licence,
            ".",
          ),
        ]
      : [
          h("p", {}, `Fetched ${formatDateTime(detail.fetched_at)} from `, safeLink(provenance.source_url, "the operator's feed"), ". Licence: ", licence, "."),
          detail.status_read_at
            ? h("p", {
                id: "status-read",
                text: `Charge point statuses were read from the operator's feed again ${formatDateTime(detail.status_read_at)}; everything else is as fetched above.`,
              })
            : null,
        ]),
    ...sources.flatMap((source) => [
      h("p", { className: "related", text: source.note }),
      h(
        "p",
        {},
        `Tariffs marked as published in ${source.name}'s tariff data were fetched ${formatDateTime(source.fetched_at)} from `,
        safeLink(source.source_url, `${source.name}'s tariff feed`),
        ". Licence: ",
        source.licence_url ? safeLink(source.licence_url, source.licence) : source.licence,
        ".",
      ),
    ]),
    hasNotes ? h("p", { text: "Prices on this page come from tariff data, not from the operator's notes." }) : null,
    referenceNote(detail),
  );
}

export function renderDetail(
  detail,
  {
    repository,
    plans = [],
    mine = new Set(),
    withheld = [],
    hideOut = false,
    onHideOut = null,
    privateNote = null,
    label = null,
    filtered = false,
    rate = null,
    onEditRate = null,
    cards = [],
    onEditCards = null,
  },
) {
  const location = detail.location;
  const evses = location.evses ?? [];
  const notes = siteNotes(location);
  // What every charge point here shares is said once, with the site.
  const shared = {
    parking: sharedBy(evses, parkingRules),
    payment: sharedBy(evses, paymentWays),
    floor: sharedBy(evses, (evse) => evse.floor_level || null),
  };
  const says = operatorSays({ parkingType: parkingTypeName(location), payment: shared.payment, floor: shared.floor });
  const groups = chargePointGroups(evses, detail.prices, notes, shared);
  const { latitude, longitude } = location.coordinates;
  const report = new URL(`${repository}/issues/new`);
  report.searchParams.set("template", "correction.yml");
  report.searchParams.set("where", location.id);
  const sources = detail.tariff_sources ?? [];
  const cheaper = cheaperSection(detail, withheld);
  // The visitor's own figures here: their own rate for this network and their own cards
  // that work on it. Cards with a monthly fee go in the calculator rather than being
  // where it starts.
  const op = location.provenance?.source_id ?? null;
  const own = ownOffers(op, rate ? new Map([[op, rate]]) : null, cards, { withFee: false });
  const currents = currentsHere(location);
  const published = lowestWithVat(detail.tariff_options);
  const ownPlans = cards
    .map((card) => cardAsPlan(card, { op, cur: currents.includes("dc") ? "dc" : "ac", published }))
    .filter(Boolean);
  return [
    h("h2", { id: "detail-heading", tabindex: "-1", text: location.name || "Charger location" }),
    h("p", { className: "operator", text: location.operator?.name ?? "Operator not given" }),
    h("p", { text: address(location) }),
    openingHours(location.opening_hours),
    shared.parking ? h("p", { className: "parking", text: `Parking: ${shared.parking}.` }) : null,
    says ? h("p", { className: "hint says", text: says }) : null,
    privateNote ? h("p", { className: "hint private-note", text: privateNote }) : null,
    ...(detail.coordinates_corrected?.note
      ? [h("p", { className: "hint corrected", text: detail.coordinates_corrected.note })]
      : []),
    detail.sent_copy ? h("p", { className: "hint copy-note", text: sentCopyText(detail) }) : null,
    ...statusSection(detail, { hideOut, onHideOut }),
    // Kept even when empty, so the line can follow the filters while the panel is open.
    h("div", { id: "detail-label" }, mapLabelLine(detail, label, filtered)),
    ...cheaper,
    ...ownRateSection(rate, { cards, op, cheaper: cheaper.length > 0, onEditRate, onEditCards }),
    ...notesSection(notes),
    h("h3", { text: evses.length ? `Charge points (${evses.length})` : "Charge points" }),
    groups.length
      ? h("ul", { className: "charge-point-groups", "aria-label": "Charge points" }, groups.map((group) => groupItem(group, detail)))
      : h("p", { text: "No charge points listed." }),
    ...sources.map((source) =>
      h("p", { className: "hint related-note", text: `Prices here use ${source.name}'s tariff data: see "More about this data".` }),
    ),
    h("p", {
      className: "hint",
      text: detail.sent_copy
        ? "Prices are as in the copy the operator sent, and may have changed. Always check at the charger."
        : "Prices and statuses are as the operator published them, and may have changed. Always check at the charger.",
    }),
    ...tariffSection(detail),
    ...plansSection(detail, plans, mine, withheld, own, ownPlans),
    h(
      "ul",
      { className: "detail-links" },
      h("li", {}, safeLink(osmLink(latitude, longitude), "View on OpenStreetMap")),
      h("li", {}, h("a", { href: `geo:${latitude},${longitude}` }, "Open in a maps app (Android and some other devices)")),
      h("li", {}, safeLink(report.href, "Report a mistake")),
    ),
    h("p", { className: "attribution", text: [detail.attribution, ...sources.map((source) => source.attribution)].join(" ") }),
    aboutSection(detail, { hasNotes: notes.length > 0 }),
  ].filter(Boolean);
}
