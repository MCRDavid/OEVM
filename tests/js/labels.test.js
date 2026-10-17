import assert from "node:assert/strict";
import { test } from "node:test";

import { defaults } from "../../site/assets/js/filters.js";
import { bestPlans, priceLabel } from "../../site/assets/js/labels.js";

const CCS = "IEC_62196_T2_COMBO";
const TYPE2 = "IEC_62196_T2";

// Kinds of connector as in data/locations.geojson, with their labels from pipeline/pricing.py.
const rapid = { std: CCS, kw: 50, price: "priced", ppk: 92.4, out: false, low: 82.8, lvat: true, lt: "82.8p" };
const slow = { std: TYPE2, kw: 7, price: "priced", ppk: 57.6, out: false, low: 57.6, lvat: true, lt: "57.6p" };
const free = { std: TYPE2, kw: 7, price: "free", ppk: null, out: false, low: null, lvat: null, lt: "Free" };
const noVat = {
  std: TYPE2,
  kw: 5,
  price: "priced",
  ppk: null,
  out: false,
  low: 32.5,
  lvat: false,
  lvar: true,
  lt: "from 32.5p excl. VAT",
};
const unknown = { std: CCS, kw: 50, price: "unknown", ppk: null, out: false, low: null, lvat: null, lt: null };
const site = (...cons) => ({ op: "geniepoint", cons });
const plan = (id, ppk, label = ppk === null ? null : `${ppk}p`) => ({ id, ppk, label, operator_ids: ["geniepoint"] });

test("the label is the lowest price per kWh among the connectors", () => {
  const label = priceLabel(site(rapid, slow), defaults());
  assert.equal(label.text, "57.6p");
  assert.equal(label.low, 57.6);
  assert.equal(label.lvat, true);
  assert.equal(label.plan, null);
});

test("only connectors that match the filters count", () => {
  const label = priceLabel(site(rapid, slow), { ...defaults(), minkw: 50 });
  assert.equal(label.text, "82.8p");
  assert.equal(priceLabel(site(slow), { ...defaults(), plugs: ["ccs"] }), null);
});

test("free comes first, and only from a connector confirmed free", () => {
  assert.equal(priceLabel(site(rapid, free), defaults()).text, "Free");
  assert.equal(priceLabel(site(rapid, free), defaults()).low, null);
  // A label of "Free" anywhere else is never trusted: the price state decides.
  const notFree = { ...unknown, lt: "Free" };
  assert.equal(priceLabel(site(notFree), defaults()), null);
});

test("the lowest figure wins whether or not its VAT is stated, and VAT is never added", () => {
  // 32.5p plus any VAT is still below 82.8p, so the price including VAT is not the cheapest.
  assert.equal(priceLabel(site(noVat, rapid), defaults()).text, "from 32.5p excl. VAT");
  assert.equal(priceLabel(site(noVat), defaults()).text, "from 32.5p excl. VAT");
  // A price including VAT that is not higher wins.
  const vat30 = { ...rapid, low: 30, lt: "30p" };
  const noVat30 = { ...noVat, low: 30, lvar: false, lt: "30p excl. VAT" };
  assert.equal(priceLabel(site(noVat30, vat30), defaults()).text, "30p");
  assert.equal(priceLabel(site(vat30, noVat30), defaults()).text, "30p");
});

test("on a tie, a price that applies all the time comes before one only at some times", () => {
  const some = { ...rapid, std: "CHADEMO", low: 30, lvar: true, lt: "from 30p" };
  const always = { ...slow, low: 30, lvar: false, lt: "30p" };
  assert.equal(priceLabel(site(some, always), defaults()).text, "30p");
  assert.equal(priceLabel(site(always, some), defaults()).text, "30p");
});

test("the sort key puts free first, then lower prices, then the tie breaks", () => {
  const key = (...cons) => priceLabel(site(...cons), defaults()).key;
  const vat30 = { ...rapid, low: 30, lt: "30p" };
  const vat30some = { ...vat30, lvar: true, lt: "from 30p" };
  const noVat30 = { ...noVat, low: 30, lvar: false, lt: "30p excl. VAT" };
  const vat30point1 = { ...rapid, low: 30.1, lt: "30.1p" };
  assert.ok(key(free) < key(vat30));
  assert.ok(key(vat30) < key(vat30some));
  assert.ok(key(vat30some) < key(noVat30));
  assert.ok(key(noVat30) < key(vat30point1));
  assert.ok(key(noVat) < key(slow));
});

test("no price, no label", () => {
  assert.equal(priceLabel(site(unknown), defaults()), null);
  assert.equal(priceLabel(site(), defaults()), null);
  assert.equal(priceLabel({ op: "jolt" }, defaults()), null);
});

test("a ticked plan with a lower fixed price gives the label, and says so", () => {
  const cheap = plan("p.cheap", 39);
  const label = priceLabel(site(rapid), defaults(), cheap);
  assert.equal(label.text, "39p");
  assert.equal(label.plan, cheap);
  // A dearer plan, or one at the same price, leaves the operator's own price.
  assert.equal(priceLabel(site(rapid), defaults(), plan("p.dear", 90)).plan, null);
  assert.equal(priceLabel(site(rapid), defaults(), plan("p.same", 82.8)).plan, null);
  // Free still comes first.
  assert.equal(priceLabel(site(free), defaults(), cheap).text, "Free");
  // A plan dearer than a price whose VAT is not stated leaves that price; a lower one wins.
  assert.equal(priceLabel(site(noVat), defaults(), plan("p.vat", 45)).text, "from 32.5p excl. VAT");
  assert.equal(priceLabel(site(noVat), defaults(), plan("p.vat", 30)).text, "30p");
  // A plan that applies only at some times keeps its "from", worded by the pipeline.
  const offPeak = { ...plan("p.night", 39, "from 39p"), only_at_some_times: true };
  assert.equal(priceLabel(site(rapid), defaults(), offPeak).text, "from 39p");
});

test("a plan needs a connector that matches the filters", () => {
  assert.equal(priceLabel(site(slow), { ...defaults(), minkw: 50 }, plan("p.cheap", 39)), null);
  assert.equal(priceLabel(site(), defaults(), plan("p.cheap", 39)), null);
});

test("only ticked plans with a fixed price including VAT count, the lowest per network", () => {
  const plans = [
    plan("a.dear", 60),
    plan("b.cheap", 45),
    plan("c.discount", null),
    { ...plan("d.elsewhere", 10), operator_ids: ["jolt"] },
    plan("e.unticked", 20),
  ];
  const best = bestPlans(plans, new Set(["a.dear", "b.cheap", "c.discount", "d.elsewhere"]));
  assert.equal(best.get("geniepoint").id, "b.cheap");
  assert.equal(best.get("jolt").id, "d.elsewhere");
  assert.equal(bestPlans(plans, new Set()).size, 0);
  assert.equal(bestPlans(undefined, new Set(["a.dear"])).size, 0);
});
