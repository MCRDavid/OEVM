import assert from "node:assert/strict";
import { test } from "node:test";

import { floorLevelText, parkingTypeText, paymentText, siteNotes } from "../../site/assets/js/detail.js";

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

test("card payment is worded from the payment capabilities only, in a fixed order", () => {
  assert.equal(
    paymentText({ capabilities: ["rfid_reader", "credit_card_payable", "contactless_card_support", "debit_card_payable"] }),
    "Card payment here, the operator says: contactless, credit card, debit card.",
  );
  assert.equal(paymentText({ capabilities: ["ped_terminal", "chip_card_support"] }), "Card payment here, the operator says: chip card, PIN pad.");
  // Nothing is said when no payment capability is listed, rather than "no card payment".
  assert.equal(paymentText({ capabilities: ["remote_start_stop_capable", "rfid_reader"] }), null);
  assert.equal(paymentText({}), null);
});

test("the parking type is worded as the operator's statement, and left out when unknown", () => {
  assert.equal(parkingTypeText({ parking_type: "along_motorway" }), "Parking type, the operator says: motorway services or rest area.");
  assert.equal(parkingTypeText({ parking_type: "on_street" }), "Parking type, the operator says: on the street.");
  assert.equal(parkingTypeText({ parking_type: null }), null);
  assert.equal(parkingTypeText({}), null);
});

test("a floor level is shown as the operator published it, and only when given", () => {
  assert.equal(floorLevelText({ floor_level: "-2" }), "Floor level, the operator says: -2.");
  assert.equal(floorLevelText({ floor_level: "T2" }), "Floor level, the operator says: T2.");
  assert.equal(floorLevelText({ floor_level: null }), null);
  assert.equal(floorLevelText({}), null);
});
