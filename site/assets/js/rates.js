// A visitor's own rates (ADR 0035): the price per kWh, including VAT, that the visitor
// found they can pay a network, for example in its app, typed in under "Your own rates",
// for its AC chargers, its DC chargers or both, as the two are often priced differently.
// They are the visitor's own figures: this site does not check them, never sends or
// publishes them, and saves them on the device only with "Remember my settings".

// Whole pence only, as no charger charges fractions of a penny (ADR 0003), and never 0p,
// which would read as free: only an operator's confirmed free tariff is called free.
export const MIN_PENCE = 1;
export const MAX_PENCE = 300;
export const NOTE_LENGTH = 40;
export const CURRENTS = ["ac", "dc"];

// A rate in whole pence, from a number or from what was typed; null for anything else.
export function ratePence(value) {
  const number = typeof value === "string" ? (value.trim() === "" ? Number.NaN : Number(value)) : value;
  return Number.isInteger(number) && number >= MIN_PENCE && number <= MAX_PENCE ? number : null;
}

// The rates by network id, keeping only well-formed entries with at least one rate: each
// is { op, ac, dc, note }, with null for a rate not given and "" for no note. A later
// entry for the same network replaces an earlier one.
export function cleanRates(list) {
  const rates = new Map();
  if (!Array.isArray(list)) return rates;
  for (const entry of list) {
    if (!entry || typeof entry.op !== "string" || !entry.op) continue;
    const ac = ratePence(entry.ac);
    const dc = ratePence(entry.dc);
    if (ac === null && dc === null) {
      rates.delete(entry.op);
      continue;
    }
    const note = typeof entry.note === "string" ? entry.note.trim().slice(0, NOTE_LENGTH) : "";
    rates.set(entry.op, { op: entry.op, ac, dc, note });
  }
  return rates;
}

// The rates as saved in settings: only the parts that were given.
export function rateList(rates) {
  return [...(rates?.values() ?? [])].map(({ op, ac, dc, note }) => ({
    op,
    ...(ac === null ? {} : { ac }),
    ...(dc === null ? {} : { dc }),
    ...(note ? { note } : {}),
  }));
}

// "AC 55p and DC 48p per kWh", "DC 48p per kWh".
export function rateSummary(rate) {
  const parts = CURRENTS.filter((cur) => rate?.[cur] != null).map((cur) => `${cur.toUpperCase()} ${rate[cur]}p`);
  return parts.length ? `${parts.join(" and ")} per kWh` : "";
}
