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

// A plan needs a paid subscription when it has a monthly fee, or when its fee is not
// published (so it cannot be shown as free to join).
export function needsSubscription(plan) {
  return !finite(plan.monthly_fee) || plan.monthly_fee > 0;
}

// The cheapest energy price at a site among the operator's own tariffs (from its feed,
// including VAT) and the fixed-price plans given. Discounts are skipped: the price they
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

// The calculator's answer in plain words.
export function breakEvenText(result) {
  if (!result) return "Enter the monthly fee and both prices to see the answer.";
  if (result.breakEven === null) {
    return "With these prices the plan never pays for itself: its price per kWh is not lower than what you pay now.";
  }
  let text = `The plan saves ${penceText(result.saving)} per kWh, so it pays for itself once you charge ${kwhText(result.breakEven)} a month here or on the networks it covers.`;
  if (result.net !== null) {
    text +=
      result.net >= 0
        ? ` At the use you entered you would save about ${poundsText(result.net)} a month after the fee.`
        : ` At the use you entered you would pay about ${poundsText(-result.net)} a month more, including the fee.`;
  }
  return `${text} This is a guide only: prices change, and some plans add other charges.`;
}
