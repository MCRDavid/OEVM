import assert from "node:assert/strict";
import { test } from "node:test";

import {
  allOut,
  formatDateTime,
  formatKw,
  plugGroup,
  plugName,
  plugsSummary,
  speedBand,
} from "../../site/assets/js/format.js";

test("power is never guessed", () => {
  assert.equal(formatKw(null), "Power unknown");
  assert.equal(formatKw(undefined), "Power unknown");
  assert.equal(formatKw(Number.NaN), "Power unknown");
  assert.equal(formatKw(22), "22 kW");
  assert.equal(formatKw(7.36), "7.4 kW");
});

test("dates show in UK time with the zone", () => {
  assert.equal(formatDateTime("2026-10-08T07:19:00Z"), "8 Oct 2026, 08:19 BST");
  assert.equal(formatDateTime("2026-12-01T09:00:00Z"), "1 Dec 2026, 09:00 GMT");
  assert.equal(formatDateTime(null), "date not given");
  assert.equal(formatDateTime("not a date"), "date not given");
});

test("connector names and groups", () => {
  assert.equal(plugName("IEC_62196_T2_COMBO"), "CCS (Combo 2)");
  assert.equal(plugName("NEMA_5_20"), "NEMA 5 20");
  assert.equal(plugGroup("IEC_62196_T1_COMBO"), "ccs");
  assert.equal(plugGroup("DOMESTIC_G"), "other");
  assert.equal(plugsSummary(["CHADEMO", "IEC_62196_T2", "IEC_62196_T2_COMBO"]), "CHAdeMO, Type 2, CCS");
  assert.equal(plugsSummary([]), "Connector unknown");
});

test("speed bands follow the fastest connector", () => {
  assert.equal(speedBand(null), "unknown");
  assert.equal(speedBand(5.06), "slow");
  assert.equal(speedBand(7.99), "slow");
  assert.equal(speedBand(8), "fast");
  assert.equal(speedBand(49.9), "fast");
  assert.equal(speedBand(50), "rapid");
  assert.equal(speedBand(150), "ultra");
  assert.equal(speedBand(400), "ultra");
});

test("a location is shown as out of service only when every connector was reported so", () => {
  assert.equal(allOut({ cons: [] }), false);
  assert.equal(allOut({ cons: [{ out: true }, { out: false }] }), false);
  assert.equal(allOut({ cons: [{ out: true }, { out: true }] }), true);
  assert.equal(allOut({}), false);
});
