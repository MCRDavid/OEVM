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
  assert.equal(groupOf("WORKING"), "other"); // anything unexpected is never shown as available
  assert.equal(groupOf(undefined), "other");
});

test("charge points are counted by group", () => {
  assert.deepEqual(countByGroup(evses("available", "available", "charging", "out_of_order", "unknown")), {
    available: 2,
    in_use: 1,
    out: 1,
    other: 1,
    total: 5,
  });
  assert.deepEqual(countByGroup(undefined), { available: 0, in_use: 0, out: 0, other: 0, total: 0 });
});

test("the summary line counts available charge points", () => {
  assert.equal(summaryText(countByGroup(evses("available", "charging", "charging", "removed"))), "1 of 4 charge points available");
  assert.equal(summaryText(countByGroup(evses("available"))), "1 of 1 charge point available");
  assert.equal(summaryText(countByGroup(evses("unknown", "blocked"))), "Status unknown for 2 charge points");
  assert.equal(summaryText(countByGroup([])), "No charge points listed by the operator");
});

test("chips leave out empty groups and carry text and a symbol as well as colour", () => {
  assert.deepEqual(chips(countByGroup(evses("available", "out_of_order", "out_of_order"))), [
    { group: "available", className: "status-chip status-available", symbol: "●", text: "1 available" },
    { group: "out", className: "status-chip status-out", symbol: "✕", text: "2 reported out of service" },
  ]);
  assert.equal(chips(countByGroup(evses("charging")))[0].className, "status-chip status-in-use");
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
