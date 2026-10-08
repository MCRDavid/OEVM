import assert from "node:assert/strict";
import { test } from "node:test";

import { formatDateTime, formatKw, plugGroup, plugName, plugsSummary, priceSummary } from "../../site/assets/js/format.js";

test("Free is shown only for a confirmed free location", () => {
  assert.equal(priceSummary({ price: "free", ppk: 0 }), "Free (confirmed)");
  assert.equal(priceSummary({ price: "priced", ppk: 0 }), "0p per kWh, including VAT");
  assert.equal(priceSummary({ price: "unknown", ppk: null }), "Price unknown");
  assert.equal(priceSummary({ price: "priced", ppk: null }), "Priced: see details");
});

test("pence per kWh keep one decimal place at most", () => {
  assert.equal(priceSummary({ price: "priced", ppk: 79 }), "79p per kWh, including VAT");
  assert.equal(priceSummary({ price: "priced", ppk: 49.25 }), "49.3p per kWh, including VAT");
});

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
