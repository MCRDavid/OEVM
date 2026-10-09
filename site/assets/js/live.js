// Live status on the details screen (Phase 3, docs/PHASE3_PLAN.md and ADR 0011).
//
// Groundwork only: nothing imports this file yet, so the map is unchanged. When the live
// Worker (proxy/worker.js) is running, the details screen will ask it for the location's
// statuses and show how many charge points are in each group below, coloured, with the
// time the operator's feed was read. Colour is never the only cue: every group has a
// text label and a symbol, and the counts are written out.
//
// Feed text is never put into the page as HTML; this file returns plain values only.

import { formatDateTime } from "./format.js";

// OCPI 2.2.1 EVSE statuses (as normalised by the pipeline) in four groups. "out" matches
// OUT_OF_SERVICE in pipeline/publish.py, which the "Hide out of service" filter uses
// (ADR 0012); a test checks the two agree.
export const STATUS_GROUPS = {
  available: { label: "Available", symbol: "●", statuses: ["available"] },
  in_use: { label: "In use", symbol: "◐", statuses: ["charging", "reserved"] },
  out: { label: "Reported out of service", symbol: "✕", statuses: ["out_of_order", "inoperative", "planned", "removed"] },
  other: { label: "Blocked or status unknown", symbol: "?", statuses: ["blocked", "unknown"] },
};
export const GROUP_ORDER = ["available", "in_use", "out", "other"];

export function groupOf(status) {
  for (const group of GROUP_ORDER) {
    if (STATUS_GROUPS[group].statuses.includes(status)) return group;
  }
  return "other";
}

// How many charge points (OCPI EVSEs, each charging one vehicle at a time) are in each group.
// "unknown" also counts statuses the map does not know, which groupOf puts in "other".
export function countByGroup(evses) {
  const counts = { available: 0, in_use: 0, out: 0, other: 0, unknown: 0, total: 0 };
  for (const evse of evses ?? []) {
    const group = groupOf(evse?.status);
    counts[group] += 1;
    if (group === "other" && evse?.status !== "blocked") counts.unknown += 1;
    counts.total += 1;
  }
  return counts;
}

function chargePoints(n) {
  return n === 1 ? "1 charge point" : `${n} charge points`;
}

// One line for the top of the details screen, such as "2 of 4 charge points available".
export function summaryText(counts) {
  if (!counts.total) return "No charge points listed by the operator";
  if (counts.unknown === counts.total) return `Status unknown for ${chargePoints(counts.total)}`;
  return `${counts.available} of ${chargePoints(counts.total)} available`;
}

// The groups to show as coloured chips, in order, leaving out empty ones.
export function chips(counts) {
  return GROUP_ORDER.filter((group) => counts[group] > 0).map((group) => ({
    group,
    className: `status-chip status-${group.replace("_", "-")}`,
    symbol: STATUS_GROUPS[group].symbol,
    text: `${counts[group]} ${STATUS_GROUPS[group].label.toLowerCase()}`,
  }));
}

// Neutral, dated wording: when the operator's public feed was read, never "live" or "now".
export function asOfText(fetchedAt) {
  return `Status from the operator's feed, read ${formatDateTime(fetchedAt)}`;
}

// The Worker address for one location. The key is the detail file's name (16 hex digits).
export function liveUrl(base, operator, key) {
  if (!/^[a-z0-9_]+$/.test(operator) || !/^[0-9a-f]{16}$/.test(key)) return null;
  return `${String(base).replace(/\/+$/, "")}/live/${operator}/${key}`;
}
