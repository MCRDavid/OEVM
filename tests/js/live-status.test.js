import assert from "node:assert/strict";
import { test } from "node:test";

import { STATUS_LABELS } from "../../site/assets/js/format.js";
import {
  GROUP_ORDER,
  STATUS_GROUPS,
  asOfText,
  chips,
  countByGroup,
  groupOf,
  liveEntry,
  liveUrl,
  summaryText,
  withLiveStatuses,
} from "../../site/assets/js/live.js";

const evses = (...statuses) => statuses.map((status, i) => ({ uid: `e${i}`, status }));

test("every status the map knows is in exactly one group", () => {
  const grouped = GROUP_ORDER.flatMap((g) => STATUS_GROUPS[g].statuses).sort();
  assert.deepEqual(grouped, Object.keys(STATUS_LABELS).sort());
});

test("statuses fall in the agreed groups", () => {
  assert.equal(groupOf("available"), "available");
  assert.equal(groupOf("charging"), "in_use");
  assert.equal(groupOf("reserved"), "in_use");
  for (const s of ["out_of_order", "inoperative", "planned", "removed"]) assert.equal(groupOf(s), "out");
  assert.equal(groupOf("blocked"), "other");
  assert.equal(groupOf("unknown"), "other");
  assert.equal(groupOf("working"), "other"); // free or in use not stated: never available
  assert.equal(groupOf("WORKING"), "other"); // anything unexpected is never shown as available
  assert.equal(groupOf(undefined), "other");
});

test("charge points are counted by group", () => {
  assert.deepEqual(countByGroup(evses("available", "available", "charging", "out_of_order", "unknown")), {
    available: 2,
    in_use: 1,
    out: 1,
    other: 1,
    unknown: 1,
    working: 0,
    total: 5,
  });
  assert.deepEqual(countByGroup(evses("blocked", "WORKING")), {
    available: 0,
    in_use: 0,
    out: 0,
    other: 2,
    unknown: 1, // a status the map does not know counts as unknown; blocked does not
    working: 0,
    total: 2,
  });
  assert.deepEqual(countByGroup(undefined), { available: 0, in_use: 0, out: 0, other: 0, unknown: 0, working: 0, total: 0 });
});

test("the summary line counts available charge points", () => {
  assert.equal(summaryText(countByGroup(evses("available", "charging", "charging", "removed"))), "1 of 4 charge points available");
  assert.equal(summaryText(countByGroup(evses("available"))), "1 of 1 charge point available");
  assert.equal(summaryText(countByGroup(evses("unknown", "unknown"))), "Status unknown for 2 charge points");
  assert.equal(summaryText(countByGroup(evses("unknown", "blocked"))), "0 of 2 charge points available");
  assert.equal(summaryText(countByGroup(evses("blocked"))), "0 of 1 charge point available");
  assert.equal(summaryText(countByGroup([])), "No charge points listed by the operator");
});

test("chips leave out empty groups and carry text and a symbol as well as colour", () => {
  assert.deepEqual(chips(countByGroup(evses("available", "out_of_order", "out_of_order"))), [
    { group: "available", className: "status-chip status-available", symbol: "●", text: "1 available" },
    { group: "out", className: "status-chip status-out", symbol: "✕", text: "2 reported out of service" },
  ]);
  assert.equal(chips(countByGroup(evses("charging")))[0].className, "status-chip status-in-use");
  const other = (...statuses) => chips(countByGroup(evses(...statuses))).map((c) => c.text);
  assert.deepEqual(other("unknown"), ["1 status unknown"]);
  assert.deepEqual(other("blocked", "blocked"), ["2 blocked"]);
  assert.deepEqual(other("blocked", "unknown"), ["2 blocked or status unknown"]);
  assert.deepEqual(other("working", "unknown"), ["1 working (free or in use, not stated)", "1 status unknown"]);
});

test("the time is worded as when the feed was read, never as live", () => {
  const text = asOfText("2026-10-09T13:05:00Z");
  assert.match(text, /^Status from the operator's feed, read 9 Oct 2026, 14:05 BST$/);
  assert.doesNotMatch(text, /live|now/i);
  assert.equal(asOfText(null), "Status from the operator's feed, read date not given");
});

test("a status file is on this site, named by the first two characters of a location key", () => {
  assert.equal(liveUrl("1f11111111111111"), "data/live/1f.json");
  assert.equal(liveUrl("../admin"), null);
  assert.equal(liveUrl("https://x.example/1111111111111111"), null);
  assert.equal(liveUrl(undefined), null);
});

const KEY = "1f11111111111111";
const READ = "2026-11-12T17:30:00Z";
const detailOf = (evses, more = {}) => ({
  location: { name: "Car park", provenance: { source_id: "chargy" }, evses },
  fetched_at: "2026-11-12T04:17:00Z",
  sent_copy: null,
  ...more,
});
const listed = [
  { uid: "A", status: "available", status_at: "2026-11-12T03:00:00Z", connectors: [{ id: "1" }] },
  { uid: "B", status: "charging", status_at: "2026-11-12T04:00:00Z", connectors: [{ id: "2" }] },
];
const entryOf = (evses, more = {}) => ({ operator: "chargy", fetched_at: READ, evses, ...more });

test("a location's entry is read only from a status file of the known shape", () => {
  const entry = entryOf([]);
  assert.equal(liveEntry({ schema_version: 1, locations: { [KEY]: entry } }, KEY), entry);
  assert.equal(liveEntry({ schema_version: 1, locations: {} }, KEY), null);
  assert.equal(liveEntry({ schema_version: 2, locations: { [KEY]: entry } }, KEY), null);
  assert.equal(liveEntry({ schema_version: 1, locations: { [KEY]: { evses: [] } } }, KEY), null);
  assert.equal(liveEntry({ schema_version: 1, locations: { [KEY]: { fetched_at: READ } } }, KEY), null);
  assert.equal(liveEntry({ schema_version: 1, locations: {} }, "toString"), null);
  assert.equal(liveEntry(null, KEY), null);
  assert.equal(liveEntry("<html>", KEY), null);
});

test("a later refresh replaces statuses and their times, and nothing else", () => {
  const detail = detailOf(listed);
  const fresh = withLiveStatuses(
    detail,
    entryOf([
      { uid: "B", status: "available", status_at: "2026-11-12T17:10:00Z" },
      { uid: "A", status: "out_of_order", status_at: "2026-11-12T16:00:00Z" },
    ]),
  );
  assert.deepEqual(fresh.location.evses, [
    { uid: "A", status: "out_of_order", status_at: "2026-11-12T16:00:00Z", connectors: [{ id: "1" }] },
    { uid: "B", status: "available", status_at: "2026-11-12T17:10:00Z", connectors: [{ id: "2" }] },
  ]);
  assert.equal(fresh.status_read_at, READ);
  assert.equal(fresh.fetched_at, detail.fetched_at);
  assert.equal(fresh.location.name, "Car park");
  // The detail file itself is not changed.
  assert.equal(detail.location.evses[0].status, "available");
  assert.equal(detail.status_read_at, undefined);
  assert.equal(summaryText(countByGroup(fresh.location.evses)), "1 of 2 charge points available");
});

test("a refresh that is not newer, or not this operator's, changes nothing", () => {
  const detail = detailOf(listed);
  const evses = [{ uid: "A", status: "charging", status_at: READ }];
  assert.equal(withLiveStatuses(detail, null), detail);
  assert.equal(withLiveStatuses(detail, entryOf(evses, { fetched_at: detail.fetched_at })), detail);
  assert.equal(withLiveStatuses(detail, entryOf(evses, { fetched_at: "2026-11-11T17:30:00Z" })), detail);
  assert.equal(withLiveStatuses(detail, entryOf(evses, { fetched_at: "soon" })), detail);
  assert.equal(withLiveStatuses(detail, entryOf(evses, { operator: "jolt" })), detail);
  assert.equal(withLiveStatuses(null, entryOf(evses)), null);
  // A copy an operator sent never gets a status (ADR 0029).
  const copy = detailOf(listed, { sent_copy: { files_url: "https://example.org/" } });
  assert.equal(withLiveStatuses(copy, entryOf(evses)), copy);
});

test("a charge point the refresh did not list is unknown, never an older status under a newer time", () => {
  const fresh = withLiveStatuses(detailOf(listed), entryOf([{ uid: "B", status: "available", status_at: READ }, { uid: "C", status: "available", status_at: READ }]));
  assert.deepEqual(
    fresh.location.evses.map((e) => [e.uid, e.status, e.status_at]),
    [
      ["A", "unknown", null],
      ["B", "available", READ],
    ],
  );
  const none = withLiveStatuses(detailOf(listed), entryOf([{ status: "available" }, null, "x"]));
  assert.deepEqual(none.location.evses.map((e) => e.status), ["unknown", "unknown"]);
  assert.equal(summaryText(countByGroup(none.location.evses)), "Status unknown for 2 charge points");
});

test("two charge points with the same uid are matched by position, or not at all", () => {
  const twins = [
    { uid: "A", status: "available", status_at: "2026-11-12T03:00:00Z" },
    { uid: "A", status: "charging", status_at: "2026-11-12T03:00:00Z" },
    { uid: "B", status: "charging", status_at: "2026-11-12T03:00:00Z" },
  ];
  const sameOrder = withLiveStatuses(
    detailOf(twins),
    entryOf([
      { uid: "A", status: "charging", status_at: READ },
      { uid: "A", status: "out_of_order", status_at: READ },
      { uid: "B", status: "available", status_at: READ },
    ]),
  );
  assert.deepEqual(sameOrder.location.evses.map((e) => e.status), ["charging", "out_of_order", "available"]);
  const reordered = withLiveStatuses(
    detailOf(twins),
    entryOf([
      { uid: "B", status: "available", status_at: READ },
      { uid: "A", status: "charging", status_at: READ },
      { uid: "A", status: "out_of_order", status_at: READ },
    ]),
  );
  assert.deepEqual(reordered.location.evses.map((e) => e.status), ["unknown", "unknown", "available"]);
});

test("a status the map does not know is never shown as available", () => {
  const fresh = withLiveStatuses(detailOf(listed), entryOf([{ uid: "A", status: "FREE", status_at: READ }, { uid: "B", status: 7, status_at: READ }]));
  assert.deepEqual(fresh.location.evses.map((e) => e.status), ["FREE", "unknown"]);
  assert.equal(countByGroup(fresh.location.evses).available, 0);
  assert.equal(groupOf("FREE"), "other");
});

test("charge points a feed reports only as working are never counted as available", () => {
  const counts = countByGroup(evses("working", "working", "working"));
  assert.equal(counts.available, 0);
  assert.equal(counts.working, 3);
  assert.equal(summaryText(counts), "3 of 3 charge points working (free or in use, not stated)");
  assert.equal(summaryText(countByGroup(evses("working", "unknown"))), "1 of 2 charge points working (free or in use, not stated)");
  assert.equal(summaryText(countByGroup(evses("working", "out_of_order"))), "1 of 2 charge points working (free or in use, not stated)");
  assert.equal(summaryText(countByGroup(evses("working", "available"))), "1 of 2 charge points available");
  assert.deepEqual(chips(countByGroup(evses("working", "working", "out_of_order", "unknown"))), [
    { group: "out", className: "status-chip status-out", symbol: "✕", text: "1 reported out of service" },
    { group: "other", className: "status-chip status-other", symbol: "?", text: "2 working (free or in use, not stated)" },
    { group: "other", className: "status-chip status-other", symbol: "?", text: "1 status unknown" },
  ]);
});
