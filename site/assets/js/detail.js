// The details panel for one location, built from data/loc/<shard>/<key>.json.

import { h, safeLink } from "./dom.js";
import { STATUS_LABELS, formatDateTime, formatKw, plugName } from "./format.js";

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

function connectorItem(evse, connector, price) {
  const status = STATUS_LABELS[evse.status] ?? STATUS_LABELS.unknown;
  const when = evse.status === "unknown" ? "" : `, reported ${formatDateTime(evse.status_at)}`;
  return h(
    "li",
    {},
    h("p", { className: "plug" }, h("strong", { text: plugName(connector.standard) }), ` · ${formatKw(connector.max_kw)}`),
    h("p", { text: `${status}${when}` }),
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
      h("p", {}, h("strong", { text: option.name || "Tariff with no description" })),
      h("p", { className: "hint", text: option.kind }),
      h("p", { className: "price", text: option.text }),
      option.varies ? h("p", { text: option.varies }) : null,
      option.reason ? h("p", { className: "hint", text: option.reason }) : null,
      option.connectors < total
        ? h("p", { className: "hint", text: `Listed for ${option.connectors} of ${total} connectors.` })
        : null,
    ),
  );
  return [
    h("h3", { text: `Tariffs listed here (${options.length})` }),
    detail.tariff_comparison ? h("p", { text: detail.tariff_comparison }) : null,
    h("ul", { className: "tariffs", "aria-label": "Tariffs listed here" }, items),
  ].filter(Boolean);
}

export function renderDetail(detail, { repository }) {
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
    h("h3", { text: "Connectors" }),
    items.length ? h("ul", { className: "connectors" }, items) : h("p", { text: "No charge points listed." }),
    ...tariffSection(detail),
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
