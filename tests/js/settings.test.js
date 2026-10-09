import assert from "node:assert/strict";
import { test } from "node:test";

import { defaults } from "../../site/assets/js/filters.js";
import { STORAGE_KEY, createSettings } from "../../site/assets/js/settings.js";

function memoryStorage() {
  const items = new Map();
  return {
    items,
    getItem: (key) => (items.has(key) ? items.get(key) : null),
    setItem: (key, value) => items.set(key, String(value)),
    removeItem: (key) => items.delete(key),
  };
}

const blocked = {
  getItem() {
    throw new Error("blocked");
  },
  setItem() {
    throw new Error("blocked");
  },
  removeItem() {
    throw new Error("blocked");
  },
};

test("nothing is stored until save is called", () => {
  const storage = memoryStorage();
  const settings = createSettings(storage);
  assert.equal(settings.isRemembered(), false);
  assert.equal(settings.load(), null);
  assert.equal(storage.items.size, 0);
});

test("saved filters load back, and forget deletes them", () => {
  const storage = memoryStorage();
  const settings = createSettings(storage);
  const state = { ...defaults(), minkw: 50, ops: ["jolt"], view: "list" };
  assert.equal(settings.save(state), true);
  assert.deepEqual([...storage.items.keys()], [STORAGE_KEY]);
  assert.deepEqual(JSON.parse(storage.items.get(STORAGE_KEY)), { version: 1, filters: "minkw=50&op=jolt&view=list" });
  assert.equal(settings.isRemembered(), true);
  assert.deepEqual(settings.load(), state);
  assert.equal(settings.forget(), true);
  assert.equal(storage.items.size, 0);
});

test("damaged or old saved values are ignored", () => {
  const storage = memoryStorage();
  const settings = createSettings(storage);
  for (const raw of ["{not json", "null", '{"version":2,"filters":""}', '{"version":1,"filters":5}']) {
    storage.setItem(STORAGE_KEY, raw);
    assert.equal(settings.load(), null, raw);
  }
  storage.setItem(STORAGE_KEY, JSON.stringify({ version: 1, filters: "minkw=999&op=<b>" }));
  assert.deepEqual(settings.load(), defaults());
});

test("blocked or missing storage never throws", () => {
  for (const storage of [blocked, null]) {
    const settings = createSettings(storage);
    assert.equal(settings.isRemembered(), false);
    assert.equal(settings.load(), null);
    assert.equal(settings.save(defaults()), false);
    assert.equal(settings.forget(), storage === null);
  }
});

test("a light or dark choice is saved only when given, and forget deletes it", () => {
  const storage = memoryStorage();
  const settings = createSettings(storage);
  assert.equal(settings.theme(), null);
  settings.save(defaults());
  assert.equal(settings.theme(), null, "no choice made, so the page follows the device");
  settings.save(defaults(), "dark");
  assert.equal(settings.theme(), "dark");
  assert.deepEqual(settings.load(), defaults());
  settings.save(defaults(), "purple");
  assert.equal(settings.theme(), null);
  settings.forget();
  assert.equal(settings.theme(), null);
  assert.equal(storage.items.size, 0);
  assert.equal(createSettings(blocked).theme(), null);
});
