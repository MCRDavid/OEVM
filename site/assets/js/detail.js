// The details panel for one location, built from data/loc/<shard>/<key>.json.

import { h, safeLink } from "./dom.js";
import { STATUS_LABELS, formatDateTime, formatKw, plugName } from "./format.js";
import { STATUS_GROUPS, asOfText, chips, countByGroup, groupOf, summaryText } from "./live.js";
import { breakEven, breakEvenText, cheapest, discounted, needsSubscription, plansFor, withheldFor, withheldParts } from "./plans.js";

export const SENT_COPY_STATUS =
  "Not shown: this operator's data is a copy it sent, not a feed, so it cannot say whether a charge point is free now.";

const WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"];

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
  if (!hours) return h("p", { text: "Opening hours: not given by the operator." });
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

// A status in its group's colour, with the group's symbol, so colour is never the only cue.
function statusLine(evse) {
  const known = Object.hasOwn(STATUS_LABELS, evse.status) ? evse.status : "unknown";
  const group = groupOf(known);
  const when = known === "unknown" ? "" : `, reported ${formatDateTime(evse.status_at)}`;
  return h(
    "p",
    { className: `status status-${group.replace("_", "-")}` },
    h("span", { "aria-hidden": "true", text: `${STATUS_GROUPS[group].symbol} ` }),
    `${STATUS_LABELS[known]}${when}`,
  );
}

// How many charge points are free, in use, out of service or unknown, coloured, and when
// the operator's feed was read. Statuses come from the daily fetch for now (ADR 0015).
// Given onHideOut, the out of service count is a button that switches the map's "Hide out of service"
// filter (ADR 0012) on or off, as the owner chose on 10 October 2026.
export function statusSection(detail, { hideOut = false, onHideOut = null } = {}) {
  const counts = countByGroup(detail.location?.evses);
  if (!counts.total) return [];
  // A copy the operator sent says nothing about now, so no status is shown (ADR 0029).
  if (detail.sent_copy) {
    return [
      h("h3", { text: "Charge point status" }),
      h("p", { className: "hint", text: SENT_COPY_STATUS }),
    ];
  }
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
    h("h3", { text: "Charge point status" }),
    h("p", { className: "status-summary", text: summaryText(counts) }),
    h("p", { className: "status-chips" }, all.map(chip)),
    filterButton
      ? h("p", {
          className: "hint",
          id: "status-filter-hint",
          text: "Press the \"reported out of service\" count to hide or show chargers where every charge point was reported out of service, on the map and in the list. It is the same as the \"Hide out of service\" button.",
        })
      : null,
    h("p", { className: "hint", text: `${asOfText(detail.fetched_at)}. It may have changed since.` }),
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

export function parkingTypeText(location) {
  const kind = PARKING_TYPES[location.parking_type];
  return kind ? `Parking type, the operator says: ${kind}.` : null;
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

export function paymentText(evse) {
  const ways = Object.keys(PAYMENT).filter((c) => (evse.capabilities ?? []).includes(c));
  return ways.length ? `Card payment here, the operator says: ${ways.map((c) => PAYMENT[c]).join(", ")}.` : null;
}

// The level the operator says a charge point is on (OCPI floor_level), as published
// (ADR 0030). Not given for operators whose values the owner decided are not levels.
export function floorLevelText(evse) {
  return evse.floor_level ? `Floor level, the operator says: ${evse.floor_level}.` : null;
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
    h("p", {
      className: "hint",
      text: "As the operator published them, and they may be out of date. Prices on this page come from tariff data, not from these notes.",
    }),
  ];
}

function connectorItem(connector, price) {
  return h(
    "li",
    {},
    h("p", { className: "plug" }, h("strong", { text: plugName(connector.standard) }), ` · ${formatKw(connector.max_kw)}`),
    h(
      "p",
      { className: "price" },
      price ? price.text : "Price unknown",
      price?.reason ? h("span", { className: "hint", text: ` ${price.reason}` }) : null,
    ),
  );
}

// One item per charge point (OCPI EVSE), each with its own name, status and connectors, so
// people can see which one is free, in use or out of service. A charge point charges one
// vehicle at a time, whichever of its connectors is used.
function chargePointItem(evse, index, prices, shownNotes) {
  const name = chargePointName(evse, index);
  const connectors = evse.connectors ?? [];
  const parking = (evse.parking_restrictions ?? []).map((r) => PARKING[r]).filter(Boolean);
  const payment = paymentText(evse);
  const floor = floorLevelText(evse);
  return h(
    "li",
    { className: "charge-point" },
    h("p", { className: "charge-point-name" }, h("strong", { text: name })),
    evse.evse_id && evse.evse_id !== name ? h("p", { className: "hint", text: `ID ${evse.evse_id}` }) : null,
    statusLine(evse),
    floor ? h("p", { className: "floor-level", text: floor }) : null,
    parking.length ? h("p", { className: "parking", text: `Parking: ${parking.join("; ")}.` }) : null,
    payment ? h("p", { className: "payment", text: payment }) : null,
    evse.directions && !shownNotes.includes(evse.directions)
      ? h("p", { className: "notes", text: `Operator's note: ${evse.directions}` })
      : null,
    connectors.length > 1
      ? h("p", { className: "hint", text: `${connectors.length} connectors, one vehicle at a time.` })
      : null,
    connectors.length
      ? h(
          "ul",
          { className: "connectors", "aria-label": `Connectors on ${name}` },
          connectors.map((c) => connectorItem(c, priceFor(prices, evse, c))),
        )
      : h("p", { text: "No connectors listed by the operator." }),
  );
}

// A small note at the foot of the details with the operator's own references for the
// location and each charge point, to quote when reporting a fault or a mistake.
function referenceNote(location) {
  const site = location.id.split(":").slice(3).join(":");
  const network = location.operator?.name ?? "the operator";
  return h(
    "div",
    { className: "references" },
    h("h3", { text: "Reference numbers" }),
    h(
      "ul",
      { className: "hint", "aria-label": "Reference numbers" },
      h("li", { text: `Site: ${site} in ${network}'s feed (on this map: ${location.id}).` }),
      (location.evses ?? []).map((evse, index) => {
        const name = chargePointName(evse, index);
        const parts = [evse.evse_id && evse.evse_id !== name ? `EVSE ID ${evse.evse_id}` : null, `uid ${evse.uid}`];
        return h("li", { text: `${name}: ${parts.filter(Boolean).join(", ")}.` });
      }),
    ),
  );
}

// Every tariff the site's connectors list, so people can compare them. Shown only when
// there is more than one: with a single tariff the connector prices already say it all.
// Every price and comparison is worded by the pipeline (pipeline/pricing.py).
export function tariffSection(detail) {
  const options = detail.tariff_options ?? [];
  if (options.length < 2) return [];
  const total = (detail.location?.evses ?? []).reduce((n, e) => n + (e.connectors?.length ?? 0), 0);
  const items = options.map((option) =>
    h(
      "li",
      {},
      h("p", {}, h("strong", { text: option.name || option.kind })),
      option.name ? h("p", { className: "hint", text: option.kind }) : null,
      h("p", { className: "price", text: option.text }),
      option.varies ? h("p", { text: option.varies }) : null,
      option.reason ? h("p", { className: "hint", text: option.reason }) : null,
      option.original_name
        ? h("p", { className: "hint", text: `Operator's name for it: ${option.original_name}` })
        : null,
      option.published_by ? h("p", { className: "hint", text: `Published in ${option.published_by}'s tariff data.` }) : null,
      option.connectors < total
        ? h("p", { className: "hint", text: `Listed for ${option.connectors} of ${total} connectors.` })
        : null,
    ),
  );
  return [
    h("h3", { text: `Tariffs listed here (${options.length})` }),
    h("p", {
      className: "hint",
      text: "Cheapest first, by price per kWh. Prices excluding VAT, or with VAT not stated, come after those including VAT.",
    }),
    detail.tariff_comparison ? h("p", { text: detail.tariff_comparison }) : null,
    h("ul", { className: "tariffs", "aria-label": "Tariffs listed here" }, items),
  ].filter(Boolean);
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
    h("p", { className: "hint", text: plan.pay_by }),
    h("p", { className: "price", text: plan.price_text }),
    h("p", { text: plan.fee_text }),
    plan.fee_note ? h("p", { className: "hint", text: plan.fee_note }) : null,
    plan.conditions ? h("p", { className: "hint", text: plan.conditions }) : null,
    plan.needs_testing ? h("p", { className: "hint", text: `Needs testing: ${plan.needs_testing}` }) : null,
    h("p", { className: "hint" }, safeLink(plan.source_url, "Provider's page"), `, checked ${checkedDate(plan.checked)}.`),
    plan.attribution ? h("p", { className: "hint", text: plan.attribution }) : null,
  );
}

function cheapestLine(detail, plans, label) {
  const best = cheapest(detail.tariff_options, plans);
  if (!best) return null;
  const what =
    best.kind === "plan"
      ? `${best.item.price_text}, with ${best.item.name} from ${best.item.provider} (${best.item.fee_text.toLowerCase()})`
      : `${best.item.published_by ? `${best.item.published_by}'s` : "the operator's"} ${best.item.name ? `"${best.item.name}" ` : ""}tariff, ${best.item.text}`;
  return h("p", { className: "cheapest", text: `${label}: ${what}.` });
}

function number(input) {
  const value = input.value.trim() === "" ? Number.NaN : Number(input.value);
  return Number.isFinite(value) ? value : Number.NaN;
}

// The subscription calculator. It starts from published figures where there are some
// (the plan's fee and fixed price, and the lowest pay-at-the-charger price here that
// includes VAT); the visitor can change any of them.
function calculator(detail, plans) {
  const paid = plans.filter((plan) => Number.isFinite(plan.monthly_fee) && plan.monthly_fee > 0);
  if (!paid.length) return null;
  const now = (detail.tariff_options ?? [])
    .filter((o) => o.state === "priced" && o.includes_vat && Number.isFinite(o.ppk_low))
    .map((o) => o.ppk_low);
  const field = (id, label, attrs = {}) => {
    const input = h("input", { id, type: "number", inputmode: "decimal", min: "0", step: "0.01", ...attrs });
    return [h("label", { for: id, text: label }), input];
  };
  const select = h(
    "select",
    { id: "calc-plan", "aria-describedby": "calc-note" },
    paid.map((plan) => h("option", { value: plan.id, text: `${plan.name} (${plan.provider})` })),
  );
  const [feeLabel, fee] = field("calc-fee", "Monthly fee (pounds)");
  const [nowLabel, payNow] = field("calc-now", "What you pay now (pence per kWh)", {
    step: "0.1",
    "aria-describedby": "calc-now-hint",
  });
  const [baseLabel, base] = field("calc-base", "Price the discount is taken off (pence per kWh)", {
    step: "0.1",
    "aria-describedby": "calc-note",
  });
  const [withLabel, withPlan] = field("calc-with", "Price with the plan (pence per kWh)", { step: "0.1" });
  const [kwhLabel, kwh] = field("calc-kwh", "kWh you charge a month (optional)", { step: "1" });
  const note = h("p", { className: "hint", id: "calc-note" });
  const answer = h("p", { id: "calc-answer", role: "status" });
  const baseRow = h("div", { className: "calc-base" }, baseLabel, base);
  if (now.length) payNow.value = String(Math.min(...now));
  // For a discount plan the price with the plan is worked out from the base price, but
  // only when the base price changes, so a price the visitor types in is kept.
  const update = (event) => {
    const plan = paid.find((p) => p.id === select.value);
    const isDiscount = Number.isFinite(plan.discount_percent);
    baseRow.hidden = !isDiscount;
    if (isDiscount && (!event || event.target === base)) {
      const price = discounted(number(base), plan.discount_percent);
      withPlan.value = price === null ? "" : String(Math.round(price * 10) / 10);
    }
    answer.textContent = breakEvenText(
      breakEven({
        fee: number(fee),
        payNow: number(payNow),
        withPlan: number(withPlan),
        kwh: kwh.value.trim() === "" ? null : number(kwh),
      }),
    );
  };
  const choose = () => {
    const plan = paid.find((p) => p.id === select.value);
    fee.value = String(plan.monthly_fee);
    withPlan.value = Number.isFinite(plan.ppk) ? String(plan.ppk) : "";
    base.value = "";
    note.textContent = Number.isFinite(plan.discount_percent)
      ? `${plan.price_text}. That price is not published openly, so enter it from the provider's app.`
      : Number.isFinite(plan.ppk)
        ? ""
        : "This plan's price per kWh is not published. Enter it if you know it.";
    update();
  };
  select.addEventListener("change", choose);
  for (const input of [fee, payNow, base, withPlan, kwh]) input.addEventListener("input", update);
  const body = h(
    "div",
    { className: "calc" },
    h("label", { for: "calc-plan", text: "Plan" }),
    select,
    note,
    feeLabel,
    fee,
    nowLabel,
    payNow,
    h(
      "p",
      { className: "hint", id: "calc-now-hint", text: now.length ? "Starts from the lowest published price here that includes VAT." : "No price including VAT is published here. Enter what you pay." },
    ),
    baseRow,
    withLabel,
    withPlan,
    kwhLabel,
    kwh,
    answer,
  );
  choose();
  return h("details", { className: "calculator" }, h("summary", { text: "Is a subscription worth it here?" }), body);
}

// Where the operator's own terms keep its memberships or subscriptions off the map.
function withheldNote(entry) {
  const parts = withheldParts(entry).map((part) => (typeof part === "string" ? part : safeLink(part.url, part.text)));
  return h("p", { className: "hint withheld" }, ...parts);
}

// Plans from providers' own pages that cover this location's network, the cheapest
// published energy price here, and the calculator. Where the operator's own plans cannot
// be shown because of its terms, a note says so.
export function plansSection(detail, allPlans, mine = new Set(), withheld = []) {
  const operatorId = detail.location?.provenance?.source_id;
  const plans = plansFor(operatorId, allPlans);
  const held = withheldFor(operatorId, withheld).map(withheldNote);
  if (!plans.length) return held.length ? [h("h3", { text: "Memberships and subscriptions" }), ...held] : [];
  const yours = plans.filter((plan) => mine.has(plan.id));
  const free = plans.filter((plan) => !needsSubscription(plan));
  const paid = plans.filter(needsSubscription);
  const list = (label, items) =>
    h("ul", { className: "tariffs plans", "aria-label": label }, items.map((p) => planItem(p, mine)));
  return [
    h("h3", { text: `Other ways to pay here (${plans.length})` }),
    h("p", {
      className: "hint",
      text: "Plans copied by hand from each provider's own page, on the date shown, cheapest first. Fixed prices per kWh come first, then discounts from largest to smallest: discounts are not turned into prices, because the price they come off is often shown only in the provider's app. Check with the provider before signing up.",
    }),
    ...held,
    yours.length ? cheapestLine(detail, yours, "Lowest published energy price here with your plans") : null,
    cheapestLine(detail, plans, "Lowest published energy price here with any listed plan"),
    ...(free.length
      ? [h("h4", { text: `No subscription needed (${free.length})` }), list("No subscription needed", free)]
      : []),
    ...(paid.length
      ? [
          h("h4", { text: `With a paid subscription (${paid.length})` }),
          h("p", { className: "hint", text: "These prices need a monthly subscription. Its cost is shown with each plan." }),
          list("With a paid subscription", paid),
        ]
      : []),
    calculator(detail, plans),
  ].filter(Boolean);
}

// Where the price in the label above this location's point on the map, and next to it
// in the list, comes from (labels.js, ADR 0026): the tariff or ticked plan that gives it.
// label is what priceLabel returned for this location; filtered says whether the
// visitor's filters leave out some connectors. The tariff is named, and how it is paid
// for given, only when every listed tariff that gives that price agrees on it.
export function mapLabelLine(detail, label, filtered = false) {
  if (!label) return null;
  const fees = "Other charges, such as a fee per session or for staying longer, are not included.";
  let source;
  if (label.plan) {
    source = ` with your plan ${label.plan.name} from ${label.plan.provider} (${label.plan.fee_text.toLowerCase()})`;
  } else if (label.low === null) {
    const which = filtered ? " that matches your filters" : "";
    source = `, as at least one connector here${which} has a tariff the operator confirms is free`;
  } else {
    const which = filtered ? " for the connectors that match your filters" : "";
    const options = (detail.tariff_options ?? []).filter(
      (o) => o.state === "priced" && o.ppk_low === label.low && Boolean(o.includes_vat) === label.lvat,
    );
    // Said only where every listed tariff that gives the price agrees on it.
    const same = (field) => options.length > 0 && options.every((o) => o[field] === options[0][field]);
    let from = "";
    if (same("published_by") && same("kind")) {
      const [option] = options;
      const whose = option.published_by ? `${option.published_by}'s` : "the operator's";
      const name = same("name") && option.name ? ` "${option.name}"` : "";
      const tariffs = options.length > 1 && !name ? "tariffs" : "tariff";
      from = `, from ${whose}${name} ${tariffs}: ${option.kind[0].toLowerCase()}${option.kind.slice(1)}`;
    }
    source = `, the lowest price per kWh listed here${which}${from}`;
  }
  // A confirmed free tariff has no other charges, so the note about them is left off.
  const notes = [
    label.low !== null && label.lvat === false
      ? "The operator does not say whether VAT is added to this price, so it may be higher."
      : null,
    label.low === null ? null : fees,
  ].filter(Boolean);
  return h(
    "p",
    { className: "map-label" },
    "Cheapest here: ",
    h("span", { className: `price-tag${label.plan ? " with-plan" : ""}`, text: label.text }),
    `${source}. `,
    notes.length ? h("span", { className: "hint", text: notes.join(" ") }) : null,
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
  },
) {
  const location = detail.location;
  const evses = location.evses ?? [];
  const notes = siteNotes(location);
  const items = evses.map((evse, index) => chargePointItem(evse, index, detail.prices ?? [], notes));
  const { latitude, longitude } = location.coordinates;
  const report = new URL(`${repository}/issues/new`);
  report.searchParams.set("template", "correction.yml");
  report.searchParams.set("where", location.id);
  const provenance = location.provenance ?? {};
  const sources = detail.tariff_sources ?? [];
  return [
    h("h2", { id: "detail-heading", tabindex: "-1", text: location.name || "Charger location" }),
    h("p", { className: "operator", text: location.operator?.name ?? "Operator not given" }),
    h("p", { text: address(location) }),
    parkingTypeText(location) ? h("p", { className: "parking-type", text: parkingTypeText(location) }) : null,
    privateNote ? h("p", { className: "hint private-note", text: privateNote }) : null,
    ...(detail.coordinates_corrected?.note
      ? [h("p", { className: "hint corrected", text: detail.coordinates_corrected.note })]
      : []),
    detail.sent_copy?.note ? h("p", { className: "hint sent-copy", text: detail.sent_copy.note }) : null,
    openingHours(location.opening_hours),
    ...notesSection(notes),
    // Kept even when empty, so the line can follow the filters while the panel is open.
    h("div", { id: "detail-label" }, mapLabelLine(detail, label, filtered)),
    ...statusSection(detail, { hideOut, onHideOut }),
    h("h3", { text: items.length ? `Charge points (${items.length})` : "Charge points" }),
    items.length
      ? h("ul", { className: "charge-points", "aria-label": "Charge points" }, items)
      : h("p", { text: "No charge points listed." }),
    ...sources.map((source) => h("p", { className: "hint related", text: source.note })),
    ...tariffSection(detail),
    ...plansSection(detail, plans, mine, withheld),
    h(
      "p",
      { className: "hint" },
      detail.sent_copy
        ? "Prices are as in the copy the operator sent, and may have changed. Always check at the charger."
        : sources.length
          ? "Status and prices are as published in the feeds named below when last fetched, and may have changed. Always check at the charger."
          : "Status and prices are as the operator published them when last fetched, and may have changed. Always check at the charger.",
    ),
    h("h3", { text: "Where this comes from" }),
    h("p", { text: detail.attribution }),
    ...(detail.sent_copy
      ? [
          h(
            "p",
            {},
            "Read from ",
            safeLink(detail.sent_copy.files_url, "the files the operator sent"),
            `, made ${formatDateTime(detail.fetched_at)}. Licence: `,
            detail.licence_url ? safeLink(detail.licence_url, detail.licence) : detail.licence,
            ".",
          ),
        ]
      : [
          h(
            "p",
            {},
            `Fetched ${formatDateTime(detail.fetched_at)} from `,
            safeLink(provenance.source_url, "the operator's feed"),
            ". Licence: ",
            detail.licence_url ? safeLink(detail.licence_url, detail.licence) : detail.licence,
            ".",
          ),
        ]),
    ...sources.flatMap((source) => [
      h("p", { text: source.attribution }),
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
    h(
      "ul",
      { className: "detail-links" },
      h("li", {}, safeLink(osmLink(latitude, longitude), "View this place on OpenStreetMap")),
      h("li", {}, h("a", { href: `geo:${latitude},${longitude}` }, "Open in a maps app (Android and some other devices)")),
      h("li", {}, safeLink(report.href, "Report a mistake about this charger")),
    ),
    referenceNote(location),
  ].filter(Boolean);
}
