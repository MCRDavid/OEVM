// Charge point status on the details screen (Phase 3, docs/PHASE3_PLAN.md and ADR 0032).
//
// The details screen (detail.js) shows how many charge points are in each group below,
// coloured, with the time the operator's feed was read. The statuses come from the daily
// fetch, in the location's detail file, unless a status refresh read them again since:
// then they come from a status file beside the map files on this site (liveUrl), and the
// time shown is when the refresh read the feed. Colour is never the only cue: every group
// has a text label and a symbol, and the counts are written out.
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
  // "working" is not an OCPI status: in service, but free or in use is not stated. Some
  // operators publish only that, and it is never counted as available.
  other: { label: "Blocked or status unknown", symbol: "?", statuses: ["blocked", "unknown", "working"] },
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
  const counts = { available: 0, in_use: 0, out: 0, other: 0, unknown: 0, working: 0, total: 0 };
  for (const evse of evses ?? []) {
    const group = groupOf(evse?.status);
    counts[group] += 1;
    if (evse?.status === "working") counts.working += 1;
    else if (group === "other" && evse?.status !== "blocked") counts.unknown += 1;
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
  // A feed that says only "working" cannot say how many are free, so do not count them.
  if (counts.working && !counts.available) {
    return `${counts.working} of ${chargePoints(counts.total)} working (free or in use, not stated)`;
  }
  return `${counts.available} of ${chargePoints(counts.total)} available`;
}

// The groups to show as coloured chips, in order, leaving out empty ones. Working charge
// points get their own grey chip, so the words say what the feed said.
export function chips(counts) {
  const out = [];
  for (const group of GROUP_ORDER) {
    const className = `status-chip status-${group.replace("_", "-")}`;
    const { symbol, label } = STATUS_GROUPS[group];
    let n = counts[group];
    if (group === "other" && counts.working) {
      out.push({ group, className, symbol, text: `${counts.working} working (free or in use, not stated)` });
      n -= counts.working;
    }
    if (n <= 0) continue;
    let words = label.toLowerCase();
    // Say "blocked" or "status unknown" alone when only one of them is present.
    if (group === "other") {
      const blocked = n - counts.unknown;
      words = blocked && counts.unknown ? words : blocked ? "blocked" : "status unknown";
    }
    out.push({ group, className, symbol, text: `${n} ${words}` });
  }
  return out;
}

// Neutral, dated wording: when the operator's public feed was read, never "live" or "now".
export function asOfText(fetchedAt) {
  return `Status from the operator's feed, read ${formatDateTime(fetchedAt)}`;
}

// The status file for one location, on this site like the detail files and split the same
// way: by the first two characters of the key (the detail file's name, 16 hex digits).
export function liveUrl(key) {
  if (!/^[0-9a-f]{16}$/.test(key)) return null;
  return `data/live/${key.slice(0, 2)}.json`;
}

// One location's entry in a status file, or null when the file has nothing usable for it.
export function liveEntry(file, key) {
  if (file?.schema_version !== 1 || !file.locations || !Object.hasOwn(file.locations, key)) return null;
  const entry = file.locations[key];
  if (typeof entry?.fetched_at !== "string" || !Array.isArray(entry.evses)) return null;
  return entry;
}

function uidCounts(evses) {
  const counts = new Map();
  for (const evse of evses) counts.set(evse?.uid, (counts.get(evse?.uid) ?? 0) + 1);
  return counts;
}

// A detail file with the statuses of a later refresh laid over it, and status_read_at set
// to when the refresh read the feed. Only statuses and their times change. The detail
// file is returned as it is when the refresh is not newer than it, is for another
// operator, or the operator's data is a copy it sent (ADR 0029). A charge point the
// refresh did not list, or could not tell from another with the same uid, has no status
// at that time, so it shows as unknown rather than keeping an older one under a newer time.
export function withLiveStatuses(detail, entry) {
  const location = detail?.location;
  if (!location || !entry || detail.sent_copy) return detail;
  if (!(Date.parse(entry.fetched_at) > Date.parse(detail.fetched_at))) return detail;
  const operator = location.provenance?.source_id;
  if (operator && entry.operator !== operator) return detail;
  const listed = location.evses ?? [];
  const fresh = entry.evses.filter((evse) => typeof evse?.uid === "string");
  // The same charge points in the same order: match by position, which also tells apart
  // two that a feed gives the same uid.
  const sameOrder = fresh.length === listed.length && listed.every((evse, i) => evse.uid === fresh[i].uid);
  const inDetail = uidCounts(listed);
  const inRefresh = uidCounts(fresh);
  const byUid = new Map(fresh.map((evse) => [evse.uid, evse]));
  const evses = listed.map((evse, i) => {
    const unique = inDetail.get(evse.uid) === 1 && inRefresh.get(evse.uid) === 1;
    const read = sameOrder ? fresh[i] : unique ? byUid.get(evse.uid) : null;
    if (!read || typeof read.status !== "string") return { ...evse, status: "unknown", status_at: null };
    return { ...evse, status: read.status, status_at: read.status_at ?? null };
  });
  return { ...detail, location: { ...location, evses }, status_read_at: entry.fetched_at };
}
