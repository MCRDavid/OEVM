import assert from "node:assert/strict";
import { test } from "node:test";

import { chargePointGroups, operatorSays, parkingRules, parkingTypeName, paymentWays, siteNotes } from "../../site/assets/js/detail.js";
import { formatShortDateTime } from "../../site/assets/js/format.js";

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
    paymentWays({ capabilities: ["rfid_reader", "credit_card_payable", "contactless_card_support", "debit_card_payable"] }),
    "contactless, credit card, debit card",
  );
  assert.equal(paymentWays({ capabilities: ["ped_terminal", "chip_card_support"] }), "chip card, PIN pad");
  // Nothing is said when no payment capability is listed, rather than "no card payment".
  assert.equal(paymentWays({ capabilities: ["remote_start_stop_capable", "rfid_reader"] }), null);
  assert.equal(paymentWays({}), null);
});

test("the parking type is worded for drivers, and left out when unknown", () => {
  assert.equal(parkingTypeName({ parking_type: "along_motorway" }), "motorway services or rest area");
  assert.equal(parkingTypeName({ parking_type: "on_street" }), "on the street");
  assert.equal(parkingTypeName({ parking_type: null }), null);
  assert.equal(parkingTypeName({}), null);
});

test("parking rules are worded for drivers, and a value that is not one is left out", () => {
  assert.equal(parkingRules({ parking_restrictions: ["plugged", "customers"] }), "only while plugged in and charging; customers only");
  assert.equal(parkingRules({ parking_restrictions: ["something_else"] }), null);
  assert.equal(parkingRules({}), null);
});

test("what the operator says is one line, said to be the operator's statement", () => {
  assert.equal(
    operatorSays({ parkingType: "car park", payment: "contactless, credit card", floor: "-2" }),
    "The operator says: car park; card payment (contactless, credit card); floor level -2.",
  );
  // A floor level is shown exactly as published.
  assert.equal(operatorSays({ floor: "T2" }), "The operator says: floor level T2.");
  assert.equal(operatorSays({}), null);
});

const connector = (id, standard, kw) => ({ id, standard, max_kw: kw });
const point = (uid, connectors, more = {}) => ({ uid, physical_reference: uid, connectors, ...more });
const price = (uid, id, text, reason = null) => ({ evse_uid: uid, connector_id: id, text, reason });

test("charge points that offer the same are one group, in the operator's order", () => {
  const evses = [
    point("A", [connector("1", "IEC_62196_T2", 7.4)]),
    point("B", [connector("1", "IEC_62196_T2_COMBO", 50)]),
    point("C", [connector("1", "IEC_62196_T2", 7.4)]),
  ];
  const prices = [price("A", "1", "65p per kWh including VAT"), price("B", "1", "89p per kWh including VAT"), price("C", "1", "65p per kWh including VAT")];
  const groups = chargePointGroups(evses, prices);
  assert.deepEqual(
    groups.map((g) => g.points.map((p) => p.evse.uid)),
    [["A", "C"], ["B"]],
  );
  assert.deepEqual(groups[0].offer.connectors, [
    { plug: "Type 2", kw: "7.4 kW", power: 7.4, kwNote: null, price: "65p per kWh including VAT", reason: null },
  ]);
});

test("a different price, connector, parking rule, payment, floor or note keeps charge points apart", () => {
  const t2 = () => [connector("1", "IEC_62196_T2", 22)];
  const same = (more = {}) => point(String(Math.random()), t2(), more);
  const prices = (evses, text = "50p per kWh including VAT") => evses.map((e) => price(e.uid, "1", text));
  for (const other of [
    { parking_restrictions: ["customers"] },
    { capabilities: ["credit_card_payable"] },
    { floor_level: "2" },
    { directions: "By the barrier" },
  ]) {
    const evses = [same(), same(other)];
    assert.equal(chargePointGroups(evses, prices(evses)).length, 2, JSON.stringify(other));
  }
  const evses = [same(), same()];
  const pricesApart = [price(evses[0].uid, "1", "50p per kWh including VAT"), price(evses[1].uid, "1", "Price unknown", "No tariff is listed.")];
  assert.equal(chargePointGroups(evses, pricesApart).length, 2);
  // A connector with no price found shows "Price unknown".
  assert.equal(chargePointGroups([same()], [])[0].offer.connectors[0].price, "Price unknown");
});

test("what every charge point shares, or a note shown with the site, is not repeated in each group", () => {
  const evses = [
    point("A", [connector("1", "IEC_62196_T2", 7)], { parking_restrictions: ["customers"], capabilities: ["credit_card_payable"], directions: "In the car park" }),
    point("B", [connector("1", "IEC_62196_T2", 7)], { parking_restrictions: ["customers"], capabilities: ["credit_card_payable"], directions: "In the car park" }),
  ];
  const [group] = chargePointGroups(evses, [], ["In the car park"], { parking: "customers only", payment: "credit card" });
  assert.deepEqual([group.offer.parking, group.offer.payment, group.offer.note], [null, null, null]);
  assert.equal(group.points.length, 2);
});

test("connectors are listed fastest first, and power worked out by this project keeps its note", () => {
  const evses = [
    point("A", [
      { ...connector("3", "IEC_62196_T2", 43.5), max_kw_note: "Worked out by this project at 230 V." },
      connector("1", "IEC_62196_T2_COMBO", 50),
      connector("2", "CHADEMO", 50),
    ]),
  ];
  const [group] = chargePointGroups(evses, []);
  assert.deepEqual(
    group.offer.connectors.map((c) => [c.plug, c.kwNote]),
    [
      ["CCS (Combo 2)", null],
      ["CHAdeMO", null],
      ["Type 2", "Worked out by this project at 230 V."],
    ],
  );
});

test("a charge point's status time is short, in UK time, with the year only when it differs", () => {
  assert.equal(formatShortDateTime("2026-11-14T17:12:00Z", "2026-11-14T23:31:00Z"), "14 Nov, 17:12");
  assert.equal(formatShortDateTime("2026-07-28T12:18:00Z", "2026-11-14T23:31:00Z"), "28 Jul, 13:18");
  assert.equal(formatShortDateTime("2025-12-31T23:30:00Z", "2026-11-14T23:31:00Z"), "31 Dec 2025, 23:30");
  assert.equal(formatShortDateTime(null, "2026-11-14T23:31:00Z"), null);
  assert.equal(formatShortDateTime("soon", "2026-11-14T23:31:00Z"), null);
});
