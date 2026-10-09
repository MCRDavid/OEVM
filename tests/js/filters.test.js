import assert from "node:assert/strict";
import { test } from "node:test";

import { activeCount, defaults, matches, parse, serialise } from "../../site/assets/js/filters.js";

const CCS = "IEC_62196_T2_COMBO";
const TYPE2 = "IEC_62196_T2";

// One location, as in data/locations.geojson: each kind of connector is listed once.
const point = (cons, overrides = {}) => ({ op: "jolt", cons, ...overrides });
const connector = (overrides = {}) => ({ std: CCS, kw: 50, price: "priced", ppk: 79, ...overrides });

test("an empty address gives the defaults", () => {
  assert.deepEqual(parse(""), defaults());
  assert.equal(serialise(defaults()), "");
});

test("addresses round-trip in a fixed order", () => {
  const query = "minkw=50&plug=ccs%2Cchademo&free=1&maxp=45.5&unknown=0&op=chargy%2Cjolt&view=list";
  assert.equal(serialise(parse(query)), query);
  assert.equal(serialise(parse("op=jolt,chargy&plug=chademo,ccs,ccs")), "plug=ccs%2Cchademo&op=chargy%2Cjolt");
});

test("bad values are ignored, not guessed", () => {
  const state = parse("minkw=51&plug=type2,usb&free=yes&maxp=-1&op=Jolt,<script>,ok_1&view=grid");
  assert.equal(state.minkw, 0);
  assert.deepEqual(state.plugs, ["type2"]);
  assert.equal(state.free, false);
  assert.equal(state.maxp, null);
  assert.deepEqual(state.ops, ["ok_1"]);
  assert.equal(state.view, "map");
  assert.equal(parse("maxp=501").maxp, null);
  assert.equal(parse("maxp=abc").maxp, null);
  assert.equal(parse("maxp=").maxp, null);
  assert.equal(parse("maxp=0").maxp, 0);
});

test("a location with no connectors counts as one about which nothing is known", () => {
  assert.equal(matches(point([]), defaults()), true);
  assert.equal(matches(point([]), { ...defaults(), minkw: 7 }), false);
  assert.equal(matches(point([]), { ...defaults(), maxp: 50 }), true, "unknown prices are included");
  assert.equal(matches(point([]), { ...defaults(), maxp: 50, unknown: false }), false);
  assert.equal(matches(point([]), { ...defaults(), plugs: ["other"] }), false);
  assert.equal(matches(point([]), { ...defaults(), free: true }), false);
});

test("minimum power needs a known power", () => {
  const state = { ...defaults(), minkw: 50 };
  assert.equal(matches(point([connector({ kw: 50 })]), state), true);
  assert.equal(matches(point([connector({ kw: 22 })]), state), false);
  assert.equal(matches(point([connector({ kw: null })]), state), false);
});

test("connector filter matches any ticked group", () => {
  const state = { ...defaults(), plugs: ["chademo", "type2"] };
  assert.equal(matches(point([connector({ std: TYPE2 })]), state), true);
  assert.equal(matches(point([connector({ std: CCS })]), state), false);
  assert.equal(matches(point([connector({ std: "DOMESTIC_G" })]), { ...defaults(), plugs: ["other"] }), true);
});

test("network filter", () => {
  assert.equal(matches(point([connector()]), { ...defaults(), ops: ["jolt"] }), true);
  assert.equal(matches(point([connector()]), { ...defaults(), ops: ["chargy"] }), false);
});

test("free only keeps locations with a confirmed free connector", () => {
  const state = { ...defaults(), free: true };
  assert.equal(matches(point([connector({ price: "free", ppk: null })]), state), true);
  assert.equal(matches(point([connector({ price: "priced", ppk: 0 })]), state), false);
  assert.equal(matches(point([connector({ price: "unknown", ppk: null })]), state), false);
});

test("maximum price applies only to known prices", () => {
  const state = { ...defaults(), maxp: 50 };
  assert.equal(matches(point([connector({ ppk: 79 })]), state), false);
  assert.equal(matches(point([connector({ ppk: 50 })]), state), true);
  assert.equal(matches(point([connector({ price: "free", ppk: null })]), state), true);
  assert.equal(matches(point([connector({ price: "unknown", ppk: null })]), state), true);
  assert.equal(matches(point([connector({ price: "unknown", ppk: null })]), { ...state, unknown: false }), false);
  assert.equal(matches(point([connector({ price: "priced", ppk: null })]), { ...defaults(), unknown: false }), false);
});

test("one connector must meet every condition: a slow cheap one never lends its price to a fast one", () => {
  // Like a site in the recorded fixtures: 50 kW connectors at 82.8p, a 7 kW one at 57.6p.
  const site = point([
    connector({ std: CCS, kw: 50, ppk: 82.8 }),
    connector({ std: "CHADEMO", kw: 50, ppk: 82.8 }),
    connector({ std: TYPE2, kw: 7, ppk: 57.6 }),
  ]);
  assert.equal(matches(site, { ...defaults(), minkw: 50, maxp: 60 }), false);
  assert.equal(matches(site, { ...defaults(), minkw: 50, maxp: 85 }), true);
  assert.equal(matches(site, { ...defaults(), minkw: 7, maxp: 60 }), true);
  assert.equal(matches(site, { ...defaults(), plugs: ["ccs"], maxp: 60 }), false);
  const mixed = point([connector({ std: TYPE2, kw: 7, price: "free", ppk: null }), connector({ kw: 150 })]);
  assert.equal(matches(mixed, { ...defaults(), free: true, minkw: 50 }), false);
  assert.equal(matches(mixed, { ...defaults(), free: true, minkw: 7 }), true);
});

test("hiding out-of-service chargers keeps those with a working or unreported connector", () => {
  const state = { ...defaults(), working: true };
  assert.equal(serialise(state), "ok=1");
  assert.equal(parse("ok=1").working, true);
  assert.equal(parse("ok=yes").working, false);
  assert.equal(matches(point([connector({ out: true })]), state), false);
  assert.equal(matches(point([connector({ out: false })]), state), true);
  assert.equal(matches(point([connector({ out: true }), connector({ kw: 7, out: false })]), state), true);
  assert.equal(matches(point([]), state), true, "no status reported is not the same as out of service");
  assert.equal(matches(point([connector({ out: true })]), defaults()), true, "off by default");
});

test("power and working apply to the same connector", () => {
  const state = { ...defaults(), working: true, minkw: 50 };
  const cons = [connector({ kw: 150, out: true }), connector({ kw: 7, out: false })];
  assert.equal(matches(point(cons), state), false);
});

test("the Filters button counts each filter that differs from the defaults", () => {
  assert.equal(activeCount(defaults()), 0);
  assert.equal(activeCount(parse("minkw=50&plug=ccs,type2&ok=1&op=jolt")), 4);
  assert.equal(activeCount(parse("free=1&maxp=0&unknown=0")), 3);
});
