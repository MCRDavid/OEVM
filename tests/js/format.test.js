import assert from "node:assert/strict";
import { test } from "node:test";

import {
  allOut,
  formatDateTime,
  formatKw,
  plugGroup,
  plugName,
  plugsSummary,
  powerBand,
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

test("power bands keep AC and DC apart", () => {
  const ac = (kw) => ({ std: "IEC_62196_T2", kw, cur: "ac" });
  const dc = (kw) => ({ std: "IEC_62196_T2_COMBO", kw, cur: "dc" });
  const band = (...cons) => powerBand(cons);
  assert.equal(band(ac(2.76)), "ac");
  assert.equal(band(ac(5.99)), "ac");
  assert.equal(band(ac(6)), "ac7");
  assert.equal(band(ac(7.4)), "ac7");
  assert.equal(band(ac(10.99)), "ac7");
  assert.equal(band(ac(11)), "ac11");
  assert.equal(band(ac(22), ac(43)), "ac11");
  assert.equal(band(dc(25)), "dc");
  assert.equal(band(dc(49.9)), "dc");
  assert.equal(band(dc(50)), "dc50");
  assert.equal(band(dc(100)), "dc100");
  assert.equal(band(dc(149.9)), "dc100");
  assert.equal(band(dc(150)), "dc150");
  assert.equal(band(dc(400)), "dc150");
});

test("a DC connector sets the colour even when an AC one is faster", () => {
  const cons = [
    { std: "IEC_62196_T2", kw: 43, cur: "ac" },
    { std: "CHADEMO", kw: 25, cur: "dc" },
  ];
  assert.equal(powerBand(cons), "dc");
});

test("AC or DC is never guessed from the plug", () => {
  assert.equal(powerBand([]), "unknown");
  assert.equal(powerBand(undefined), "unknown");
  assert.equal(powerBand([{ std: "IEC_62196_T2_COMBO", kw: 50, cur: null }]), "unknown");
  assert.equal(powerBand([{ std: "IEC_62196_T2_COMBO", kw: 50 }]), "unknown");
  assert.equal(powerBand([{ std: "IEC_62196_T2", kw: null, cur: "ac" }]), "unknown");
  // A connector with no type does not hide one that has it.
  assert.equal(powerBand([{ std: "CHADEMO", kw: 50, cur: null }, { std: "IEC_62196_T2", kw: 7, cur: "ac" }]), "ac7");
});

test("a location is shown as out of service only when every connector was reported so", () => {
  assert.equal(allOut({ cons: [] }), false);
  assert.equal(allOut({ cons: [{ out: true }, { out: false }] }), false);
  assert.equal(allOut({ cons: [{ out: true }, { out: true }] }), true);
  assert.equal(allOut({}), false);
});
