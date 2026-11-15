import assert from "node:assert/strict";
import { test } from "node:test";

import { MAX_PENCE, NOTE_LENGTH, cleanRates, rateList, ratePence, rateSummary } from "../../site/assets/js/rates.js";

test("a rate is whole pence from 1p, never 0p, which would read as free", () => {
  assert.equal(ratePence("48"), 48);
  assert.equal(ratePence(" 48 "), 48);
  assert.equal(ratePence(69), 69);
  assert.equal(ratePence(String(MAX_PENCE)), MAX_PENCE);
  for (const bad of ["", "  ", "0", "48.5", "-5", "301", "abc", "1e9", null, undefined, Number.NaN, 0.48]) {
    assert.equal(ratePence(bad), null, String(bad));
  }
});

test("rates keep one entry per network with at least one rate, and a short note", () => {
  const rates = cleanRates([
    { op: "evyve", dc: 69 },
    { op: "evyve", ac: "55", dc: "48", note: `  ${"x".repeat(NOTE_LENGTH + 10)}  ` },
    { op: "jolt", ac: "", dc: "" },
    { op: "", ac: 40 },
    "ionity",
  ]);
  assert.deepEqual([...rates.keys()], ["evyve"]);
  assert.deepEqual(rates.get("evyve"), { op: "evyve", ac: 55, dc: 48, note: "x".repeat(NOTE_LENGTH) });
  // An entry with no rate left removes an earlier one for the same network.
  assert.equal(cleanRates([{ op: "evyve", dc: 48 }, { op: "evyve" }]).size, 0);
  assert.equal(cleanRates(null).size, 0);
  assert.equal(cleanRates({ op: "evyve", dc: 48 }).size, 0);
});

test("rates are saved with only the parts given, and summed up for people", () => {
  const rates = cleanRates([{ op: "evyve", dc: 48 }, { op: "pod", ac: 55, dc: 79, note: "Pod app" }]);
  assert.deepEqual(rateList(rates), [
    { op: "evyve", dc: 48 },
    { op: "pod", ac: 55, dc: 79, note: "Pod app" },
  ]);
  assert.deepEqual(rateList(null), []);
  assert.equal(rateSummary(rates.get("evyve")), "DC 48p per kWh");
  assert.equal(rateSummary(rates.get("pod")), "AC 55p and DC 79p per kWh");
  assert.equal(rateSummary(null), "");
});
