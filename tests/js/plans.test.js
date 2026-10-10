import assert from "node:assert/strict";
import { test } from "node:test";

import {
  breakEven,
  breakEvenText,
  cheapest,
  discounted,
  needsSubscription,
  penceText,
  plansFor,
  poundsText,
} from "../../site/assets/js/plans.js";

const PLANS = [
  { id: "a.discount", operator_ids: ["jolt"], ppk: null, discount_percent: 20, monthly_fee: 0 },
  { id: "b.cheap", operator_ids: ["jolt"], ppk: 39, monthly_fee: 4.99 },
  { id: "c.dear", operator_ids: ["jolt", "chargy"], ppk: 55, monthly_fee: 0 },
  { id: "d.elsewhere", operator_ids: ["chargy"], ppk: 10, monthly_fee: 0 },
  { id: "e.bigger", operator_ids: ["jolt"], ppk: null, discount_percent: 40, monthly_fee: 9.99 },
  { id: "f.unpriced", operator_ids: ["jolt"], ppk: null, discount_percent: null, monthly_fee: null },
  { id: "g.cheap_free", operator_ids: ["jolt"], ppk: 39, monthly_fee: 0 },
];

test("plans for an operator: fixed prices cheapest first, then discounts largest first", () => {
  assert.deepEqual(
    plansFor("jolt", PLANS).map((p) => p.id),
    ["g.cheap_free", "b.cheap", "c.dear", "e.bigger", "a.discount", "f.unpriced"],
  );
  assert.deepEqual(plansFor("nobody", PLANS), []);
  assert.deepEqual(plansFor("jolt", undefined), []);
});

test("a plan with a monthly fee, or an unpublished one, needs a paid subscription", () => {
  const paid = PLANS.filter(needsSubscription).map((p) => p.id);
  assert.deepEqual(paid, ["b.cheap", "e.bigger", "f.unpriced"]);
});

test("the cheapest way to pay compares only prices that include VAT", () => {
  const tariffs = [
    { state: "priced", includes_vat: true, ppk_low: 49.2 },
    { state: "priced", includes_vat: false, ppk_low: 20 },
    { state: "unknown", includes_vat: null, ppk_low: null },
  ];
  assert.equal(cheapest(tariffs, []).item.ppk_low, 49.2);
  assert.equal(cheapest(tariffs, [PLANS[1]]).item.id, "b.cheap");
  assert.equal(cheapest(tariffs, [PLANS[0]]).kind, "tariff");
  assert.equal(cheapest([], [PLANS[0]]), null);
});

test("break-even: fee divided by the saving per kWh", () => {
  const result = breakEven({ fee: 8.99, payNow: 55, withPlan: 39, kwh: 100 });
  assert.equal(result.saving, 16);
  assert.ok(Math.abs(result.breakEven - 56.1875) < 1e-9);
  assert.ok(Math.abs(result.net - 7.01) < 1e-9);
  assert.match(breakEvenText(result), /pays for itself once you charge 57 kWh a month/);
  assert.match(breakEvenText(result), /save about £7\.01 a month after the fee/);
});

test("a plan that is not cheaper never pays for itself, and a loss is said plainly", () => {
  const never = breakEven({ fee: 5, payNow: 40, withPlan: 45 });
  assert.equal(never.breakEven, null);
  assert.match(breakEvenText(never), /never pays for itself/);
  const loss = breakEven({ fee: 10, payNow: 50, withPlan: 40, kwh: 20 });
  assert.match(breakEvenText(loss), /pay about £8\.00 a month more/);
});

test("missing or negative inputs give no answer rather than a guess", () => {
  assert.equal(breakEven({ fee: Number.NaN, payNow: 50, withPlan: 40 }), null);
  assert.equal(breakEven({ fee: 5, payNow: -1, withPlan: 40 }), null);
  assert.equal(breakEven({ fee: 5, payNow: 50, withPlan: 40, kwh: -3 }), null);
  assert.match(breakEvenText(null), /Enter the monthly fee/);
});

test("discounts and money wording", () => {
  assert.equal(discounted(80, 25), 60);
  assert.equal(discounted(80, 0), null);
  assert.equal(discounted(80, 100), null);
  assert.equal(poundsText(1.005), "£1.01");
  assert.equal(poundsText(12), "£12.00");
  assert.equal(poundsText(-0.5), "minus £0.50");
  assert.equal(penceText(49.25), "49.3p");
  assert.equal(penceText(16), "16p");
});
