// Charging plans (data/plans.json) and the subscription calculator.
//
// Plan fees and prices are worded by the pipeline (pipeline/pricing.py) and shown as
// given. The calculator is the one place this site works out money: it uses the numbers
// the visitor enters or confirms, shows its working, and says it is a guide only.

// Plans that apply to an operator's locations, cheapest first: fixed prices per kWh from
// lowest to highest (the lower monthly fee first on a tie), then discounts from largest to
// smallest (the price they come off is not published, so they cannot be placed among the
// fixed prices), then plans with no price published, each in the file's order otherwise.
export function plansFor(operatorId, plans) {
  const matching = (plans ?? []).filter((plan) => (plan.operator_ids ?? []).includes(operatorId));
  const rank = (plan) => {
    const fee = finite(plan.monthly_fee) ? plan.monthly_fee : Number.POSITIVE_INFINITY;
    if (finite(plan.ppk)) return [0, plan.ppk, fee];
    if (finite(plan.discount_percent)) return [1, -plan.discount_percent, fee];
    return [2, 0, fee];
  };
  return matching
    .map((plan, index) => ({ plan, index, key: rank(plan) }))
    .sort((a, b) => a.key[0] - b.key[0] || a.key[1] - b.key[1] || a.key[2] - b.key[2] || a.index - b.index)
    .map(({ plan }) => plan);
}

// Operators whose own memberships or subscriptions may exist at this operator's
// locations but are not shown, because their terms do not allow them to be republished
// (data/plans.json "withheld", ADR 0016).
export function withheldFor(operatorId, withheld) {
  return (withheld ?? []).filter((entry) => (entry.operator_ids ?? []).includes(operatorId));
}

// Where paying one of those operators directly is cheaper than paying at the charger,
// as its own pages showed when last checked: worded by the pipeline in this project's own
// words, without the price (ADR 0034). An entry marked only_where_dc is for an operator
// whose AC chargers are paid for in its app only, so it is said only where there is a DC
// charger to compare with.
export function cheaperFor(entry, location) {
  const dc = (location?.evses ?? []).some((evse) => (evse.connectors ?? []).some((c) => c.power_type === "dc"));
  return (entry.cheaper ?? []).filter((item) => !item.only_where_dc || dc);
}

const LONG_DATE = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric", timeZone: "UTC" });

// "IONITY's", "ESB ecars'".
function whose(name) {
  return name.endsWith("s") ? `${name}'` : `${name}'s`;
}

// The line after those notes: whose website said so and when it was last checked (the
// oldest check, when there are several), why the prices are not shown, and where to look.
export function cheaperParts(entry, items) {
  const name = whose(entry.provider);
  const dates = items.map((item) => item.checked).filter(Boolean).sort();
  const when = dates.length ? new Date(`${dates[0]}T00:00:00Z`) : null;
  const checked = when && !Number.isNaN(when.getTime()) ? ` when last checked on ${LONG_DATE.format(when)}` : "";
  return [
    `According to ${name} website${checked}. Its `,
    entry.terms_url ? { url: entry.terms_url, text: "website terms" } : "website terms",
    " do not allow its prices to be shown here, so check ",
    { url: items[0]?.source_url ?? entry.website, text: `${name} website` },
    " or app before you charge.",
  ];
}

// What the details say for one of those operators (owner's request, 30 October 2026), as
// parts: text, or { url, text } for a link.
export function withheldParts(entry) {
  const name = entry.provider;
  return [
    `Charging memberships or subscriptions from ${name} may be available here, but ${name}'s `,
    entry.terms_url ? { url: entry.terms_url, text: "website terms" } : "website terms",
    " do not allow them to be republished, so they are not shown. Check ",
    { url: entry.website, text: `${name}'s website` },
    " or app for details.",
  ];
}

// A plan needs a paid subscription when it has a monthly fee, or when its fee is not
// published (so it cannot be shown as free to join).
export function needsSubscription(plan) {
  return !finite(plan.monthly_fee) || plan.monthly_fee > 0;
}

// The cheapest energy price at a site among the tariffs listed there (from the operator's
// feed or, by the owner's decision, a related operator's (ADR 0020), including VAT) and
// the fixed-price plans given. Discounts are skipped: the price they
// are taken off is not published. Returns { kind: "tariff" | "plan", item } or null.
export function cheapest(tariffOptions, plans) {
  const candidates = [];
  for (const option of tariffOptions ?? []) {
    if (option.state === "priced" && option.includes_vat && Number.isFinite(option.ppk_low)) {
      candidates.push({ kind: "tariff", item: option, ppk: option.ppk_low });
    }
  }
  for (const plan of plans ?? []) {
    if (Number.isFinite(plan.ppk)) candidates.push({ kind: "plan", item: plan, ppk: plan.ppk });
  }
  if (!candidates.length) return null;
  const low = Math.min(...candidates.map((c) => c.ppk));
  const { kind, item } = candidates.find((c) => c.ppk === low);
  return { kind, item };
}

function finite(value) {
  return typeof value === "number" && Number.isFinite(value);
}

// When a plan with a monthly fee pays for itself. Prices are in pence per kWh, the fee in
// pounds a month and use in kWh a month. Returns null when an input is missing or
// negative; otherwise { saving, breakEven, net } where saving is pence per kWh,
// breakEven the kWh a month at which the plan pays for itself (null when it never does)
// and net the pounds a month saved (negative for a loss) at the use given, or null.
export function breakEven({ fee, payNow, withPlan, kwh = null }) {
  if (![fee, payNow, withPlan].every(finite) || fee < 0 || payNow < 0 || withPlan < 0) return null;
  if (kwh !== null && (!finite(kwh) || kwh < 0)) return null;
  const saving = payNow - withPlan;
  const breakEvenKwh = saving > 0 ? (fee * 100) / saving : null;
  const net = kwh === null ? null : (kwh * saving) / 100 - fee;
  return { saving, breakEven: breakEvenKwh, net };
}

// The price with a percentage discount, for a discount plan where the visitor enters the
// price it is taken off.
export function discounted(price, percent) {
  if (!finite(price) || !finite(percent) || price < 0 || percent <= 0 || percent >= 100) return null;
  return price * (1 - percent / 100);
}

// Money in the calculator's answer: "£1.20" and "49.2p", rounded half up like the
// pipeline's own wording.
export function poundsText(amount) {
  const pennies = Math.round(Math.abs(amount) * 100 + 1e-9);
  return `${amount < 0 ? "minus " : ""}£${Math.floor(pennies / 100)}.${String(pennies % 100).padStart(2, "0")}`;
}

export function penceText(amount) {
  const tenths = Math.round(amount * 10 + 1e-9) / 10;
  return `${tenths}p`;
}

export function kwhText(kwh) {
  return `${Math.ceil(kwh - 1e-9)} kWh`;
}

// The calculator's answer in plain words. here is false for the calculator under "Your
// charging plans", which is not about one charger.
export function breakEvenText(result, { here = true } = {}) {
  if (!result) return "Enter the monthly fee and both prices to see the answer.";
  if (result.breakEven === null) {
    return "With these prices the plan never pays for itself: its price per kWh is not lower than what you pay now.";
  }
  const where = here ? "here or on the networks it covers" : "on the networks it covers";
  let text = `The plan saves ${penceText(result.saving)} per kWh, so it pays for itself once you charge ${kwhText(result.breakEven)} a month ${where}.`;
  if (result.net !== null) {
    text +=
      result.net >= 0
        ? ` At the use you entered you would save about ${poundsText(result.net)} a month after the fee.`
        : ` At the use you entered you would pay about ${poundsText(-result.net)} a month more, including the fee.`;
  }
  return `${text} This is a guide only: prices change, and some plans add other charges.`;
}

// Where a charger's calculator starts "What you pay now": the lowest of the prices here
// that include VAT, a ticked plan with no monthly fee that gives a fixed price here, and
// the visitor's own rate for this network (rates.js, ADR 0035) for the currents the site
// has ("ac", "dc"). A plan with a fee is left out, as that is what the calculator weighs
// up. On a tie the operator's own price is kept, then a ticked plan's, as on the map.
// Returns { kind: "tariff" | "plan" | "rate", ppk, item } or null; for a rate, item is
// { cur, pence }.
export function payNowStart({ tariffOptions = [], ticked = [], rate = null, currents = [] } = {}) {
  const candidates = [];
  for (const option of tariffOptions ?? []) {
    if (option.state === "priced" && option.includes_vat && finite(option.ppk_low)) {
      candidates.push({ kind: "tariff", ppk: option.ppk_low, item: option });
    }
  }
  for (const plan of ticked ?? []) {
    if (finite(plan.ppk) && plan.monthly_fee === 0) candidates.push({ kind: "plan", ppk: plan.ppk, item: plan });
  }
  for (const cur of ["ac", "dc"]) {
    const pence = rate?.[cur];
    if ((currents ?? []).includes(cur) && finite(pence)) candidates.push({ kind: "rate", ppk: pence, item: { cur, pence } });
  }
  if (!candidates.length) return null;
  const low = Math.min(...candidates.map((c) => c.ppk));
  return candidates.find((c) => c.ppk === low);
}

// The hint under "What you pay now", saying where its starting figure came from.
export function payNowHint(start) {
  if (!start) return "No price including VAT is published here. Enter what you pay.";
  if (start.kind === "plan") {
    return `Starts from your plan ${start.item.name} from ${start.item.provider}, the lowest price you have here.`;
  }
  if (start.kind === "rate") {
    return `Starts from your own ${start.item.cur.toUpperCase()} rate for this network, typed in by you.`;
  }
  return "Starts from the lowest published price here that includes VAT.";
}

// Plans a visitor might weigh up in the calculator: those with a monthly fee.
export function paidPlans(plans) {
  return (plans ?? []).filter((plan) => finite(plan.monthly_fee) && plan.monthly_fee > 0);
}
