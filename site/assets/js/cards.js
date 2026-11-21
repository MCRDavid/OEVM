// A visitor's own cards (ADR 0035, amended 21 November 2026): a roaming card, app or
// membership the visitor uses, typed in under "Your own cards". Each has a name, the
// networks it works on, its monthly fee if it has one, and what it charges: a price per
// kWh including VAT for AC chargers, DC chargers or both, or a percentage off the price
// the map shows. What a card charges often differs from one network to the next, so a
// card has figures for every network it works on and, where one differs, figures for
// that network alone. Like own rates (rates.js) these are the visitor's own figures: this
// site does not check them, never sends or publishes them, and saves them on the device
// only with "Remember my settings".

import { CURRENTS, NOTE_LENGTH, ratePence } from "./rates.js";

export const NAME_LENGTH = 40;
export const MAX_CARDS = 20;
export const MAX_FEE = 100;
// A discount above 90% would show a price close to nothing, which could read as free.
export const MAX_PERCENT = 90;

function finite(value) {
  return typeof value === "number" && Number.isFinite(value);
}

function blank(value) {
  return value === "" || value === null || value === undefined || (typeof value === "string" && !value.trim());
}

// A monthly fee in pounds and whole pence, from 0 to £100, from a number or from what was
// typed; null for anything else. 0 means no fee.
export function feePounds(value) {
  if (blank(value) || (typeof value !== "number" && typeof value !== "string")) return null;
  const number = Number(typeof value === "string" ? value.trim() : value);
  if (!Number.isFinite(number) || number < 0 || number > MAX_FEE) return null;
  const pennies = Math.round(number * 100);
  return Math.abs(pennies - number * 100) < 1e-6 ? pennies / 100 : null;
}

// A percentage off, above 0 and up to 90, to a tenth at most; null for anything else.
export function percentOff(value) {
  if (blank(value) || (typeof value !== "number" && typeof value !== "string")) return null;
  const number = Number(typeof value === "string" ? value.trim() : value);
  if (!Number.isFinite(number) || number <= 0 || number > MAX_PERCENT) return null;
  const tenths = Math.round(number * 10);
  return Math.abs(tenths - number * 10) < 1e-6 ? tenths / 10 : null;
}

function text(value, length) {
  return typeof value === "string" ? value.trim().slice(0, length) : "";
}

// The figures a card gives, everywhere or on one network: { ac, dc, pct }, null where
// not given.
function figures(entry) {
  return { ac: ratePence(entry?.ac), dc: ratePence(entry?.dc), pct: percentOff(entry?.pct) };
}

function hasFigure(f) {
  return f.ac !== null || f.dc !== null || f.pct !== null;
}

// The cards by id, keeping only well-formed ones: each is { id, name, ops, ac, dc, pct,
// fee, note, nets }, where ac, dc and pct are for every network it works on, and nets
// maps a network id to its own { ac, dc, pct } where those differ. null stands for a
// figure not given and "" for no note. A card needs a name, at least one network and at
// least one figure. A later card with the same id replaces an earlier one, and only the
// first MAX_CARDS are kept.
export function cleanCards(list) {
  const cards = new Map();
  if (!Array.isArray(list)) return cards;
  for (const entry of list) {
    if (!entry || typeof entry.id !== "string" || !entry.id) continue;
    const name = text(entry.name, NAME_LENGTH);
    const ops = Array.isArray(entry.ops) ? [...new Set(entry.ops.filter((op) => typeof op === "string" && op))] : [];
    const all = figures(entry);
    const nets = {};
    for (const op of ops) {
      const own = figures(entry.nets?.[op]);
      if (hasFigure(own)) nets[op] = own;
    }
    if (!name || !ops.length || (!hasFigure(all) && !Object.keys(nets).length)) {
      cards.delete(entry.id);
      continue;
    }
    if (!cards.has(entry.id) && cards.size >= MAX_CARDS) continue;
    cards.set(entry.id, { id: entry.id, name, ops, ...all, fee: feePounds(entry.fee), note: text(entry.note, NOTE_LENGTH), nets });
  }
  return cards;
}

function given(f) {
  return Object.fromEntries(["ac", "dc", "pct"].filter((key) => f[key] !== null).map((key) => [key, f[key]]));
}

// The cards as saved in settings: only the parts that were given.
export function cardList(cards) {
  return [...(cards?.values() ?? [])].map((card) => ({
    id: card.id,
    name: card.name,
    ops: [...card.ops],
    ...given(card),
    ...(card.fee === null ? {} : { fee: card.fee }),
    ...(card.note ? { note: card.note } : {}),
    ...(Object.keys(card.nets).length
      ? { nets: Object.fromEntries(Object.entries(card.nets).map(([op, f]) => [op, given(f)])) }
      : {}),
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

// What a card charges on one network for "ac" or "dc": { pence } or { pct }, or null when
// the visitor gave no figure for it. A figure for that network comes first, then one for
// every network; a price comes before a percentage off at each step.
export function cardFigure(card, op, cur) {
  for (const f of [card?.nets?.[op], card]) {
    if (!f) continue;
    if (f[cur] != null) return { pence: f[cur] };
    if (f.pct != null) return { pct: f.pct };
  }
  return null;
}

// A price including VAT less a percentage, to the whole penny, half pennies up, as every
// price including VAT is shown (ADR 0003).
export function lessPercent(pence, pct) {
  if (!finite(pence) || !finite(pct)) return null;
  const tenths = Math.round(pence * (100 - pct) * 10) / 1000;
  return Math.floor(tenths + 0.5);
}

// The visitor's own figures for this network, for AC and DC chargers: { ac, dc }, each a
// list of { pence } or { pct } with card (the card's name, or null for the network's own
// rate) and note, the network's own rate (rates.js) first and then each card that works
// there in the order added; null when there is none. withFee: false leaves out cards
// with a monthly fee, which the calculator weighs up rather than starting from.
export function ownOffers(op, rates, cards, { withFee = true } = {}) {
  const rate = rates?.get(op) ?? null;
  const covering = cardsFor(op, cards).filter((card) => withFee || !(card.fee > 0));
  const out = { op, ac: [], dc: [] };
  for (const cur of CURRENTS) {
    if (finite(rate?.[cur])) out[cur].push({ pence: rate[cur], card: null, note: rate.note ?? "" });
    for (const card of covering) {
      const figure = cardFigure(card, op, cur);
      if (figure) out[cur].push({ ...figure, card: card.name, note: card.note });
    }
  }
  return out.ac.length || out.dc.length ? out : null;
}

// The lowest of these offers where the published price including VAT is published (or
// null if none is): { value, cur, card, note, pct } with pct null for a price typed in.
// A percentage off counts only where there is a published price to take it off. On a tie
// the earlier offer is kept.
export function bestOffer(list, cur, published = null) {
  let best = null;
  for (const offer of list ?? []) {
    const value = offer.pence != null ? offer.pence : lessPercent(published, offer.pct);
    if (!finite(value) || value <= 0) continue;
    if (!best || value < best.value) best = { value, cur, card: offer.card, note: offer.note ?? "", pct: offer.pct ?? null };
  }
  return best;
}

// "£7.99 a month", "No monthly fee", or "" when no fee was given.
export function feeText(fee) {
  if (fee === null || fee === undefined) return "";
  return fee === 0 ? "No monthly fee" : `£${fee.toFixed(2)} a month`;
}

// "AC 45p and DC 59p per kWh", "10% off the price shown", or both.
export function figuresText(f) {
  const prices = CURRENTS.filter((cur) => f?.[cur] != null).map((cur) => `${cur.toUpperCase()} ${f[cur]}p`);
  const parts = [prices.length ? `${prices.join(" and ")} per kWh` : "", f?.pct != null ? `${f.pct}% off the price shown` : ""];
  return parts.filter(Boolean).join(", otherwise ");
}

// "AC 45p and DC 59p per kWh, £7.99 a month" for a card, with its figures for every
// network it works on; figures for one network are listed by the form and the details.
export function cardSummary(card) {
  return [figuresText(card), feeText(card?.fee)].filter(Boolean).join(", ");
}

// What a card charges on one network, for people: "DC 59p per kWh", "AC 45p and DC 59p
// per kWh", "10% off the price shown" or "AC 45p per kWh, DC 10% off the price shown",
// then its monthly fee; "" when it gives no figure there.
export function cardTextFor(card, op) {
  const ac = cardFigure(card, op, "ac");
  const dc = cardFigure(card, op, "dc");
  let figures;
  if (ac?.pct != null && dc?.pct != null && ac.pct === dc.pct) figures = `${ac.pct}% off the price shown`;
  else if (ac?.pence != null && dc?.pence != null) figures = `AC ${ac.pence}p and DC ${dc.pence}p per kWh`;
  else {
    const one = (cur, f) => (!f ? "" : f.pence != null ? `${cur} ${f.pence}p per kWh` : `${cur} ${f.pct}% off the price shown`);
    figures = [one("AC", ac), one("DC", dc)].filter(Boolean).join(", ");
  }
  return figures ? [figures, feeText(card.fee)].filter(Boolean).join(", ") : "";
}

// A card with a monthly fee as a plan the subscription calculator can offer (calculator.js).
// op, cur and published say where: the network, "ac" or "dc", and the lowest published
// price including VAT there, so a percentage off can be worked out. Without them it
// uses the card's figures for every network, DC first.
export function cardAsPlan(card, { op = null, cur = null, published = null } = {}) {
  if (!card || !(card.fee > 0)) return null;
  const currents = cur ? [cur] : ["dc", "ac"];
  let figure = null;
  for (const c of currents) {
    figure = op ? cardFigure(card, op, c) : card[c] != null ? { pence: card[c] } : card.pct != null ? { pct: card.pct } : null;
    if (figure) break;
  }
  const ppk = figure?.pence ?? (figure?.pct != null ? lessPercent(published, figure.pct) : null);
  return {
    id: `own.${card.id}`,
    provider: "your own card",
    name: card.name,
    monthly_fee: card.fee,
    ppk,
    discount_percent: figure?.pct ?? null,
    price_text: figure?.pence != null ? `${figure.pence}p per kWh, typed in by you` : figure ? `${figure.pct}% off, typed in by you` : "No price typed in",
    fee_text: feeText(card.fee),
    own: true,
  };
}

// The roaming cards and apps this site lists (data/plans.json, providers of kind
// "roaming") with the networks their plans cover, so a visitor can start a card from one
// with its networks ticked: [{ name, ops }] sorted by name, keeping only networks in
// onMap (a Set of ids) when given. Operators' own apps are left out: "Your own rates"
// is for those.
export function knownCards(plansFile, onMap = null) {
  const byName = new Map();
  for (const plan of plansFile?.plans ?? []) {
    if (plan.provider_kind !== "roaming" || typeof plan.provider !== "string" || !plan.provider) continue;
    const set = byName.get(plan.provider) ?? new Set();
    for (const op of plan.operator_ids ?? []) if (!onMap || onMap.has(op)) set.add(op);
    byName.set(plan.provider, set);
  }
  return [...byName]
    .filter(([, ops]) => ops.size)
    .map(([name, ops]) => ({ name, ops: [...ops].sort() }))
    .sort((a, b) => a.name.localeCompare(b.name));
}
