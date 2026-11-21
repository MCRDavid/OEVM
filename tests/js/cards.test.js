import assert from "node:assert/strict";
import { test } from "node:test";

import {
  MAX_CARDS,
  NAME_LENGTH,
  cardAsPlan,
  cardList,
  cardSummary,
  cardsFor,
  cleanCards,
  feePounds,
  feeText,
  knownCards,
  newCardId,
  ownRateFor,
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

test("cards keep a name, their networks, at least one price and a short note", () => {
  const cards = cleanCards([
    { id: "card1", name: "  My card  ", ops: ["ionity", "ionity", "fastned", "", 3], dc: "59", fee: "7.99" },
    { id: "card2", name: "x".repeat(NAME_LENGTH + 5), ops: ["pod"], ac: 40, note: "  app  " },
    { id: "card3", name: "No networks", ops: [], dc: 50 },
    { id: "card4", name: "No price", ops: ["pod"], ac: "", dc: "0" },
    { id: "card5", name: "", ops: ["pod"], dc: 50 },
    { id: "", name: "No id", ops: ["pod"], dc: 50 },
    "card6",
  ]);
  assert.deepEqual([...cards.keys()], ["card1", "card2"]);
  assert.deepEqual(cards.get("card1"), {
    id: "card1",
    name: "My card",
    ops: ["ionity", "fastned"],
    ac: null,
    dc: 59,
    fee: 7.99,
    note: "",
  });
  assert.equal(cards.get("card2").name, "x".repeat(NAME_LENGTH));
  assert.equal(cards.get("card2").note, "app");
  assert.equal(cards.get("card2").fee, null);
  // A card with nothing left removes an earlier one with the same id.
  assert.equal(cleanCards([{ id: "a", name: "A", ops: ["pod"], dc: 50 }, { id: "a", name: "A", ops: [] }]).size, 0);
  assert.equal(cleanCards(null).size, 0);
  const many = Array.from({ length: MAX_CARDS + 3 }, (_, i) => ({ id: `c${i}`, name: `C${i}`, ops: ["pod"], dc: 50 }));
  assert.equal(cleanCards(many).size, MAX_CARDS);
});

test("cards are saved with only the parts given, and get new ids that are not taken", () => {
  const cards = cleanCards([
    { id: "card1", name: "A", ops: ["pod"], dc: 50 },
    { id: "card3", name: "B", ops: ["ionity"], ac: 40, dc: 60, fee: 0, note: "work" },
  ]);
  assert.deepEqual(cardList(cards), [
    { id: "card1", name: "A", ops: ["pod"], dc: 50 },
    { id: "card3", name: "B", ops: ["ionity"], ac: 40, dc: 60, fee: 0, note: "work" },
  ]);
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
  assert.equal(cardSummary({ ac: 45, dc: 59, fee: 7.99 }), "AC 45p and DC 59p per kWh, £7.99 a month");
  assert.equal(cardSummary({ ac: null, dc: 59, fee: null }), "DC 59p per kWh");
  assert.equal(cardSummary(null), "");
});

test("the own price for a network is the lowest of its own rate and the cards that work there", () => {
  const rates = cleanRates([{ op: "ionity", ac: 50, dc: 69, note: "app" }]);
  const cards = cleanCards([
    { id: "card1", name: "Card A", ops: ["ionity", "fastned"], dc: 59 },
    { id: "card2", name: "Card B", ops: ["ionity"], dc: 59, ac: 60 },
    { id: "card3", name: "Card C", ops: ["pod"], ac: 30 },
  ]);
  assert.deepEqual(
    cardsFor("ionity", cards).map((card) => card.id),
    ["card1", "card2"],
  );
  // The card added first wins a tie between cards; the network's own rate wins a tie with a card.
  assert.deepEqual(ownRateFor("ionity", rates, cards), {
    op: "ionity",
    ac: 50,
    dc: 59,
    note: "app",
    from: { ac: null, dc: "Card A" },
  });
  assert.deepEqual(ownRateFor("fastned", rates, cards), {
    op: "fastned",
    ac: null,
    dc: 59,
    note: "",
    from: { ac: null, dc: "Card A" },
  });
  const tie = cleanRates([{ op: "fastned", dc: 59 }]);
  assert.deepEqual(ownRateFor("fastned", tie, cards).from, { ac: null, dc: null });
  assert.equal(ownRateFor("jolt", rates, cards), null);
  assert.equal(ownRateFor("ionity", null, null), null);
});

test("a card with a monthly fee can be weighed up in the calculator like a plan", () => {
  const [card] = cleanCards([{ id: "card1", name: "Card A", ops: ["ionity"], ac: 45, dc: 59, fee: 7.99 }]).values();
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
  assert.equal(cardAsPlan(card, { preferDc: false }).ppk, 45);
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
