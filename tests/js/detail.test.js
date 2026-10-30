import assert from "node:assert/strict";
import { test } from "node:test";

import { siteNotes } from "../../site/assets/js/detail.js";

const evse = (directions) => ({ uid: String(Math.random()), directions });

test("the site's own note and a note every charge point shares are shown once", () => {
  assert.deepEqual(siteNotes({ directions: "In the car park", evses: [evse("In the car park"), evse("In the car park")] }), [
    "In the car park",
  ]);
  assert.deepEqual(siteNotes({ directions: null, evses: [evse("Contactless payment available."), evse("Contactless payment available.")] }), [
    "Contactless payment available.",
  ]);
  assert.deepEqual(siteNotes({ directions: "Free parking", evses: [evse("Behind the barrier")] }), [
    "Free parking",
    "Behind the barrier",
  ]);
});

test("notes that differ between charge points stay with each charge point", () => {
  assert.deepEqual(siteNotes({ directions: "Free parking", evses: [evse("Disabled Parking Bay"), evse(null)] }), [
    "Free parking",
  ]);
  assert.deepEqual(siteNotes({ evses: [] }), []);
  assert.deepEqual(siteNotes({ evses: [evse(null), evse(null)] }), []);
});
