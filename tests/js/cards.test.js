import assert from "node:assert/strict";
import { test } from "node:test";

import {
  MAX_CARDS,
  MAX_PERCENT,
  NAME_LENGTH,
  bestOffer,
  cardAsPlan,
  cardFigure,
  cardList,
  cardSummary,
  cardsFor,
  cleanCards,
  feePounds,
  feeText,
  figuresText,
  knownCards,
  lessPercent,
  newCardId,
  ownOffers,
  percentOff,
} from "../../site/assets/js/cards.js";
import { cleanRates } from "../../site/assets/js/rates.js";

test("a monthly fee is pounds and whole pence from 0 to 100, or nothing", () => {
  assert.equal(feePounds("7.99"), 7.99);
  assert.equal(feePounds(" 0 "), 0);
  assert.equal(feePounds(2), 2);
  assert.equal(feePounds("100"), 100);
  for (const bad of ["", "  ", "-1", "100.01", "7.999", "abc", null, undefined, Number.NaN]) {
    assert.equal(feePounds(bad), null, String(bad));
  }
});

test("a percentage off is above 0 and up to 90, to a tenth at most", () => {
  assert.equal(percentOff("10"), 10);
  assert.equal(percentOff(" 7.5 "), 7.5);
  assert.equal(percentOff(MAX_PERCENT), MAX_PERCENT);
  for (const bad of ["", "0", "-5", "90.1", "100", "7.55", "abc", null, undefined]) {
    assert.equal(percentOff(bad), null, String(bad));
  }
});

test("cards keep a name, their networks, at least one figure and a short note", () => {
  const cards = cleanCards([
    { id: "card1", name: "  My card  ", ops: ["ionity", "ionity", "fastned", "", 3], dc: "59", fee: "7.99" },
    { id: "card2", name: "x".repeat(NAME_LENGTH + 5), ops: ["pod"], pct: "10", note: "  app  " },
    // Figures for one network only are enough, and figures for a network not ticked are dropped.
    { id: "card3", name: "Per network", ops: ["pod"], nets: { pod: { ac: 40, pct: "x" }, jolt: { dc: 50 } } },
    { id: "card4", name: "No networks", ops: [], dc: 50 },
    { id: "card5", name: "No figure", ops: ["pod"], ac: "", dc: "0", nets: { pod: { pct: 0 } } },
    { id: "card6", name: "", ops: ["pod"], dc: 50 },
    { id: "", name: "No id", ops: ["pod"], dc: 50 },
    "card7",
  ]);
  assert.deepEqual([...cards.keys()], ["card1", "card2", "card3"]);
  assert.deepEqual(cards.get("card1"), {
    id: "card1",
    name: "My card",
    ops: ["ionity", "fastned"],
    ac: null,
    dc: 59,
    pct: null,
    fee: 7.99,
    note: "",
    nets: {},
  });
  assert.equal(cards.get("card2").name, "x".repeat(NAME_LENGTH));
  assert.equal(cards.get("card2").note, "app");
  assert.equal(cards.get("card2").pct, 10);
  assert.equal(cards.get("card2").fee, null);
  assert.deepEqual(cards.get("card3").nets, { pod: { ac: 40, dc: null, pct: null } });
  // A card with nothing left removes an earlier one with the same id.
  assert.equal(cleanCards([{ id: "a", name: "A", ops: ["pod"], dc: 50 }, { id: "a", name: "A", ops: [] }]).size, 0);
  assert.equal(cleanCards(null).size, 0);
  const many = Array.from({ length: MAX_CARDS + 3 }, (_, i) => ({ id: `c${i}`, name: `C${i}`, ops: ["pod"], dc: 50 }));
  assert.equal(cleanCards(many).size, MAX_CARDS);
});

test("cards are saved with only the parts given, and get new ids that are not taken", () => {
  const cards = cleanCards([
    { id: "card1", name: "A", ops: ["pod"], dc: 50 },
    { id: "card3", name: "B", ops: ["ionity", "pod"], ac: 40, pct: 10, fee: 0, note: "work", nets: { pod: { dc: 45 } } },
  ]);
  assert.deepEqual(cardList(cards), [
    { id: "card1", name: "A", ops: ["pod"], dc: 50 },
    { id: "card3", name: "B", ops: ["ionity", "pod"], ac: 40, pct: 10, fee: 0, note: "work", nets: { pod: { dc: 45 } } },
  ]);
  // What is saved reads back the same.
  assert.deepEqual(cleanCards(cardList(cards)), cards);
  assert.deepEqual(cardList(null), []);
  assert.equal(newCardId(cards), "card4");
  assert.equal(newCardId(cleanCards([{ id: "card2", name: "A", ops: ["pod"], dc: 50 }])), "card3");
  assert.equal(newCardId(new Map()), "card1");
});

test("cards are summed up for people, with their monthly fee", () => {
  assert.equal(feeText(null), "");
  assert.equal(feeText(0), "No monthly fee");
  assert.equal(feeText(7.99), "£7.99 a month");
  assert.equal(feeText(2), "£2.00 a month");
  assert.equal(cardSummary({ ac: 45, dc: 59, pct: null, fee: 7.99 }), "AC 45p and DC 59p per kWh, £7.99 a month");
  assert.equal(cardSummary({ ac: null, dc: 59, pct: 10, fee: null }), "DC 59p per kWh, otherwise 10% off the price shown");
  assert.equal(figuresText({ ac: null, dc: null, pct: 15 }), "15% off the price shown");
  assert.equal(cardSummary(null), "");
});

test("a card's figure for a network comes from that network first, then every network", () => {
  const [card] = cleanCards([
    { id: "card1", name: "A", ops: ["ionity", "pod", "jolt"], dc: 59, pct: 10, nets: { pod: { ac: 40 }, jolt: { pct: 20 } } },
  ]).values();
  assert.deepEqual(cardFigure(card, "ionity", "dc"), { pence: 59 });
  assert.deepEqual(cardFigure(card, "ionity", "ac"), { pct: 10 });
  assert.deepEqual(cardFigure(card, "pod", "ac"), { pence: 40 });
  assert.deepEqual(cardFigure(card, "pod", "dc"), { pence: 59 });
  assert.deepEqual(cardFigure(card, "jolt", "dc"), { pct: 20 });
  const [plain] = cleanCards([{ id: "c", name: "C", ops: ["pod"], dc: 50 }]).values();
  assert.equal(cardFigure(plain, "pod", "ac"), null);
});

test("a percentage off a price including VAT is taken to the whole penny, half pennies up", () => {
  assert.equal(lessPercent(79, 10), 71); // 71.1p
  assert.equal(lessPercent(45, 10), 41); // 40.5p
  assert.equal(lessPercent(85, 15), 72); // 72.25p
  assert.equal(lessPercent(null, 10), null);
  assert.equal(lessPercent(79, null), null);
});

test("own offers for a network list its own rate first, then each card that works there", () => {
  const rates = cleanRates([{ op: "ionity", ac: 50, dc: 69, note: "app" }]);
  const cards = cleanCards([
    { id: "card1", name: "Card A", ops: ["ionity", "fastned"], dc: 59 },
    { id: "card2", name: "Card B", ops: ["ionity"], pct: 15, fee: 4.99, note: "work" },
    { id: "card3", name: "Card C", ops: ["pod"], ac: 30 },
  ]);
  assert.deepEqual(
    cardsFor("ionity", cards).map((card) => card.id),
    ["card1", "card2"],
  );
  const offers = ownOffers("ionity", rates, cards);
  assert.deepEqual(offers.ac, [
    { pence: 50, card: null, note: "app" },
    { pct: 15, card: "Card B", note: "work" },
  ]);
  assert.deepEqual(offers.dc, [
    { pence: 69, card: null, note: "app" },
    { pence: 59, card: "Card A", note: "" },
    { pct: 15, card: "Card B", note: "work" },
  ]);
  // Cards with a monthly fee can be left out, for where the calculator starts.
  assert.equal(ownOffers("ionity", rates, cards, { withFee: false }).dc.length, 2);
  assert.equal(ownOffers("jolt", rates, cards), null);
  assert.equal(ownOffers("ionity", null, null), null);
  // The best offer: a percentage off counts only where a published price is given.
  assert.deepEqual(bestOffer(offers.dc, "dc"), { value: 59, cur: "dc", card: "Card A", note: "", pct: null });
  assert.deepEqual(bestOffer(offers.dc, "dc", 65), { value: 55, cur: "dc", card: "Card B", note: "work", pct: 15 });
  // On a tie the earlier offer, so the network's own rate, is kept.
  assert.equal(bestOffer([{ pence: 59, card: null }, { pence: 59, card: "Card A" }], "dc").card, null);
  assert.equal(bestOffer([], "dc"), null);
});

test("a card with a monthly fee can be weighed up in the calculator like a plan", () => {
  const [card] = cleanCards([
    { id: "card1", name: "Card A", ops: ["ionity", "pod"], ac: 45, dc: 59, fee: 7.99, nets: { pod: { pct: 10 } } },
  ]).values();
  assert.deepEqual(cardAsPlan(card), {
    id: "own.card1",
    provider: "your own card",
    name: "Card A",
    monthly_fee: 7.99,
    ppk: 59,
    discount_percent: null,
    price_text: "59p per kWh, typed in by you",
    fee_text: "£7.99 a month",
    own: true,
  });
  assert.equal(cardAsPlan(card, { op: "ionity", cur: "ac" }).ppk, 45);
  // A percentage off is worked out from the published price there, when there is one.
  const pod = cardAsPlan(card, { op: "pod", cur: "dc", published: 79 });
  assert.equal(pod.ppk, 71);
  assert.equal(pod.discount_percent, 10);
  assert.equal(pod.price_text, "10% off, typed in by you");
  assert.equal(cardAsPlan(card, { op: "pod", cur: "dc" }).ppk, null);
  assert.equal(cardAsPlan({ ...card, fee: 0 }), null);
  assert.equal(cardAsPlan({ ...card, fee: null }), null);
  assert.equal(cardAsPlan(null), null);
});

test("known cards list each provider's networks on the map, to start a card from", () => {
  const plansFile = {
    plans: [
      { provider: "Electroverse", operator_ids: ["ionity", "fastned", "gone"] },
      { provider: "Electroverse", operator_ids: ["pod"] },
      { provider: "Lidl Plus", operator_ids: ["lidl"] },
      { provider: "Nowhere", operator_ids: ["gone"] },
    ],
    withheld: [{ provider: "Pod Point", operator_ids: ["pod"] }],
  };
  const onMap = new Set(["ionity", "fastned", "pod"]);
  assert.deepEqual(knownCards(plansFile, onMap), [
    { name: "Electroverse", ops: ["fastned", "ionity", "pod"] },
    { name: "Pod Point", ops: ["pod"] },
  ]);
  assert.equal(knownCards(plansFile).length, 4);
  assert.deepEqual(knownCards(null), []);
});
