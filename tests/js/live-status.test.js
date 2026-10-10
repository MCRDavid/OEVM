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
  liveUrl,
  summaryText,
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

test("Worker addresses are built only from an operator id and a location key", () => {
  assert.equal(liveUrl("https://live.example.workers.dev/", "chargy", "1111111111111111"), "https://live.example.workers.dev/live/chargy/1111111111111111");
  assert.equal(liveUrl("https://x.example", "../admin", "1111111111111111"), null);
  assert.equal(liveUrl("https://x.example", "chargy", "not-a-key"), null);
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
