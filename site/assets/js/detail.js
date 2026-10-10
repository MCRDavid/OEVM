// The details panel for one location, built from data/loc/<shard>/<key>.json.

import { h, safeLink } from "./dom.js";
import { STATUS_LABELS, formatDateTime, formatKw, plugName } from "./format.js";
import { STATUS_GROUPS, asOfText, chips, countByGroup, groupOf, summaryText } from "./live.js";
import { breakEven, breakEvenText, cheapest, discounted, needsSubscription, plansFor } from "./plans.js";

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

function connectorItem(evse, connector, price) {
  return h(
    "li",
    {},
    h("p", { className: "plug" }, h("strong", { text: plugName(connector.standard) }), ` · ${formatKw(connector.max_kw)}`),
    statusLine(evse),
    h(
      "p",
      { className: "price" },
      price ? price.text : "Price unknown",
      price?.reason ? h("span", { className: "hint", text: ` ${price.reason}` }) : null,
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
      : `the operator's ${best.item.name ? `"${best.item.name}" ` : ""}tariff, ${best.item.text}`;
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

// Plans from providers' own pages that cover this location's network, the cheapest
// published energy price here, and the calculator.
export function plansSection(detail, allPlans, mine = new Set()) {
  const operatorId = detail.location?.provenance?.source_id;
  const plans = plansFor(operatorId, allPlans);
  if (!plans.length) return [];
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

export function renderDetail(detail, { repository, plans = [], mine = new Set(), hideOut = false, onHideOut = null }) {
  const location = detail.location;
  const items = [];
  for (const evse of location.evses ?? []) {
    if (!evse.connectors?.length) {
      items.push(h("li", { text: `Charge point ${evse.uid}: no connectors listed by the operator.` }));
    }
    for (const connector of evse.connectors ?? []) {
      items.push(connectorItem(evse, connector, priceFor(detail.prices ?? [], evse, connector)));
    }
  }
  const { latitude, longitude } = location.coordinates;
  const report = new URL(`${repository}/issues/new`);
  report.searchParams.set("template", "correction.yml");
  report.searchParams.set("where", location.id);
  const provenance = location.provenance ?? {};
  return [
    h("h2", { id: "detail-heading", tabindex: "-1", text: location.name || "Charger location" }),
    h("p", { className: "operator", text: location.operator?.name ?? "Operator not given" }),
    h("p", { text: address(location) }),
    ...(detail.coordinates_corrected?.note
      ? [h("p", { className: "hint corrected", text: detail.coordinates_corrected.note })]
      : []),
    openingHours(location.opening_hours),
    ...statusSection(detail, { hideOut, onHideOut }),
    h("h3", { text: "Connectors" }),
    items.length ? h("ul", { className: "connectors" }, items) : h("p", { text: "No charge points listed." }),
    ...tariffSection(detail),
    ...plansSection(detail, plans, mine),
    h(
      "p",
      { className: "hint" },
      "Status and prices are as the operator published them when last fetched, and may have changed. Always check at the charger.",
    ),
    h("h3", { text: "Where this comes from" }),
    h("p", { text: detail.attribution }),
    h(
      "p",
      {},
      `Fetched ${formatDateTime(detail.fetched_at)} from `,
      safeLink(provenance.source_url, "the operator's feed"),
      ". Licence: ",
      detail.licence_url ? safeLink(detail.licence_url, detail.licence) : detail.licence,
      ".",
    ),
    h(
      "ul",
      { className: "detail-links" },
      h("li", {}, safeLink(osmLink(latitude, longitude), "View this place on OpenStreetMap")),
      h("li", {}, h("a", { href: `geo:${latitude},${longitude}` }, "Open in a maps app (Android and some other devices)")),
      h("li", {}, safeLink(report.href, "Report a mistake about this charger")),
    ),
  ];
}
