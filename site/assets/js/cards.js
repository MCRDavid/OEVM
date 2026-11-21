// A visitor's own cards (ADR 0035, amended 21 November 2026): a roaming card, app or
// membership the visitor uses, typed in under "Your own cards" with its name, the networks
// it works on, the price per kWh including VAT it gives there for AC chargers, DC chargers
// or both, and its monthly fee if it has one. Like own rates (rates.js) they are the
// visitor's own figures: this site does not check them, never sends or publishes them,
// and saves them on the device only with "Remember my settings".

import { CURRENTS, NOTE_LENGTH, ratePence } from "./rates.js";

export const NAME_LENGTH = 40;
export const MAX_CARDS = 20;
export const MAX_FEE = 100;

// A monthly fee in pounds and whole pence, from 0 to £100, from a number or from what was
// typed; null for anything else. 0 means no fee.
export function feePounds(value) {
  const text = typeof value === "string" ? value.trim() : value;
  if (text === "" || text === null || text === undefined) return null;
  const number = Number(text);
  if (!Number.isFinite(number) || number < 0 || number > MAX_FEE) return null;
  const pennies = Math.round(number * 100);
  return Math.abs(pennies - number * 100) < 1e-6 ? pennies / 100 : null;
}

function text(value, length) {
  return typeof value === "string" ? value.trim().slice(0, length) : "";
}

// The cards by id, keeping only well-formed ones: each is { id, name, ops, ac, dc, fee,
// note }, with null for a price or fee not given and "" for no note. A card needs a
// name, at least one network and at least one price. A later card with the same id
// replaces an earlier one, and only the first MAX_CARDS are kept.
export function cleanCards(list) {
  const cards = new Map();
  if (!Array.isArray(list)) return cards;
  for (const entry of list) {
    if (!entry || typeof entry.id !== "string" || !entry.id) continue;
    const name = text(entry.name, NAME_LENGTH);
    const ops = Array.isArray(entry.ops) ? [...new Set(entry.ops.filter((op) => typeof op === "string" && op))] : [];
    const ac = ratePence(entry.ac);
    const dc = ratePence(entry.dc);
    if (!name || !ops.length || (ac === null && dc === null)) {
      cards.delete(entry.id);
      continue;
    }
    if (!cards.has(entry.id) && cards.size >= MAX_CARDS) continue;
    cards.set(entry.id, { id: entry.id, name, ops, ac, dc, fee: feePounds(entry.fee), note: text(entry.note, NOTE_LENGTH) });
  }
  return cards;
}

// The cards as saved in settings: only the parts that were given.
export function cardList(cards) {
  return [...(cards?.values() ?? [])].map(({ id, name, ops, ac, dc, fee, note }) => ({
    id,
    name,
    ops: [...ops],
    ...(ac === null ? {} : { ac }),
    ...(dc === null ? {} : { dc }),
    ...(fee === null ? {} : { fee }),
    ...(note ? { note } : {}),
  }));
}

// An id for a new card that none of these uses.
export function newCardId(cards) {
  let n = (cards?.size ?? 0) + 1;
  while (cards?.has(`card${n}`)) n += 1;
  return `card${n}`;
}

// The cards that work on this network, in the order they were added.
export function cardsFor(op, cards) {
  return [...(cards?.values() ?? [])].filter((card) => card.ops.includes(op));
}

// The visitor's own price for this network's AC and DC chargers: for each, the lowest of
// their own rate for the network (rates.js) and the cards that work on it. Returns
// { op, ac, dc, note, from } or null when there is none, where from says for "ac" and
// "dc" which card the price came from (its name), or null when it came from the
// network's own rate. On a tie the network's own rate is kept, then the card added first.
export function ownRateFor(op, rates, cards) {
  const rate = rates?.get(op) ?? null;
  const covering = cardsFor(op, cards);
  if (!rate && !covering.length) return null;
  const out = { op, ac: null, dc: null, note: rate?.note ?? "", from: { ac: null, dc: null } };
  for (const cur of CURRENTS) {
    if (rate?.[cur] != null) out[cur] = rate[cur];
    for (const card of covering) {
      if (card[cur] != null && (out[cur] === null || card[cur] < out[cur])) {
        out[cur] = card[cur];
        out.from[cur] = card.name;
      }
    }
  }
  return out.ac === null && out.dc === null ? null : out;
}

// "£7.99 a month", "No monthly fee", or "" when no fee was given.
export function feeText(fee) {
  if (fee === null || fee === undefined) return "";
  return fee === 0 ? "No monthly fee" : `£${fee.toFixed(2)} a month`;
}

// "AC 45p and DC 59p per kWh, £7.99 a month".
export function cardSummary(card) {
  const prices = CURRENTS.filter((cur) => card?.[cur] != null).map((cur) => `${cur.toUpperCase()} ${card[cur]}p`);
  const parts = [prices.length ? `${prices.join(" and ")} per kWh` : "", feeText(card?.fee)].filter(Boolean);
  return parts.join(", ");
}

// A card with a monthly fee as a plan the subscription calculator can offer (calculator.js),
// priced at its DC rate where it has one (or where dc is preferred), otherwise its AC rate.
export function cardAsPlan(card, { preferDc = true } = {}) {
  if (!card || !(card.fee > 0)) return null;
  const ppk = preferDc ? (card.dc ?? card.ac) : (card.ac ?? card.dc);
  return {
    id: `own.${card.id}`,
    provider: "your own card",
    name: card.name,
    monthly_fee: card.fee,
    ppk,
    discount_percent: null,
    price_text: `${ppk}p per kWh, typed in by you`,
    fee_text: feeText(card.fee),
    own: true,
  };
}

// The networks a known provider's plans or own networks cover, by provider name, from
// data/plans.json, so a visitor can start a card from one: [{ name, ops }] sorted by
// name, keeping only networks in onMap (a Set of ids) when given.
export function knownCards(plansFile, onMap = null) {
  const byName = new Map();
  const add = (name, ops) => {
    if (typeof name !== "string" || !name) return;
    const set = byName.get(name) ?? new Set();
    for (const op of ops ?? []) if (!onMap || onMap.has(op)) set.add(op);
    byName.set(name, set);
  };
  for (const plan of plansFile?.plans ?? []) add(plan.provider, plan.operator_ids);
  for (const entry of plansFile?.withheld ?? []) add(entry.provider, entry.operator_ids);
  return [...byName]
    .filter(([, ops]) => ops.size)
    .map(([name, ops]) => ({ name, ops: [...ops].sort() }))
    .sort((a, b) => a.name.localeCompare(b.name));
}
