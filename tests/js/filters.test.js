import assert from "node:assert/strict";
import { test } from "node:test";

import { defaults, matches, parse, serialise } from "../../site/assets/js/filters.js";

const point = (overrides = {}) => ({
  op: "jolt",
  kw: 50,
  plugs: ["IEC_62196_T2_COMBO"],
  price: "priced",
  ppk: 79,
  ...overrides,
});

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

test("minimum power needs a known power", () => {
  const state = { ...defaults(), minkw: 50 };
  assert.equal(matches(point({ kw: 50 }), state), true);
  assert.equal(matches(point({ kw: 22 }), state), false);
  assert.equal(matches(point({ kw: null }), state), false);
});

test("connector filter matches any ticked group", () => {
  const state = { ...defaults(), plugs: ["chademo", "type2"] };
  assert.equal(matches(point({ plugs: ["IEC_62196_T2"] }), state), true);
  assert.equal(matches(point({ plugs: ["IEC_62196_T2_COMBO"] }), state), false);
  assert.equal(matches(point({ plugs: ["DOMESTIC_G"] }), { ...defaults(), plugs: ["other"] }), true);
});

test("network filter", () => {
  assert.equal(matches(point(), { ...defaults(), ops: ["jolt"] }), true);
  assert.equal(matches(point(), { ...defaults(), ops: ["chargy"] }), false);
});

test("free only keeps confirmed free locations", () => {
  const state = { ...defaults(), free: true };
  assert.equal(matches(point({ price: "free", ppk: 0 }), state), true);
  assert.equal(matches(point({ price: "priced", ppk: 0 }), state), false);
  assert.equal(matches(point({ price: "unknown", ppk: null }), state), false);
});

test("maximum price applies only to known prices", () => {
  const state = { ...defaults(), maxp: 50 };
  assert.equal(matches(point({ ppk: 79 }), state), false);
  assert.equal(matches(point({ ppk: 50 }), state), true);
  assert.equal(matches(point({ price: "free", ppk: null }), state), true);
  assert.equal(matches(point({ price: "unknown", ppk: null }), state), true);
  assert.equal(matches(point({ price: "unknown", ppk: null }), { ...state, unknown: false }), false);
  assert.equal(matches(point({ price: "priced", ppk: null }), { ...defaults(), unknown: false }), false);
});
