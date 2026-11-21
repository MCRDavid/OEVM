// The subscription calculator: when a plan with a monthly fee pays for itself. It is used
// in a charger's details, starting from the prices there, and under "Your charging
// plans", for every plan with a fee, where the visitor types in what they pay now. The
// sums are in plans.js; this file builds the form.

import { h } from "./dom.js";
import { breakEven, breakEvenText, discounted, paidPlans } from "./plans.js";

function number(input) {
  const value = input.value.trim() === "" ? Number.NaN : Number(input.value);
  return Number.isFinite(value) ? value : Number.NaN;
}

// plans: the plans to offer (those without a monthly fee are left out). prefix keeps the
// ids apart when there are two calculators on the page. payNow is the starting figure for
// "What you pay now" in pence per kWh, or null, and nowHint the line saying where it came
// from. here says whether the calculator is about one charger. Returns null when no plan
// has a monthly fee.
export function subscriptionCalculator({ plans, prefix = "calc", summary, payNow = null, nowHint, here = true }) {
  const paid = paidPlans(plans);
  if (!paid.length) return null;
  const id = (name) => `${prefix}-${name}`;
  const field = (name, label, attrs = {}) => {
    const input = h("input", { id: id(name), type: "number", inputmode: "decimal", min: "0", step: "0.01", ...attrs });
    return [h("label", { for: id(name), text: label }), input];
  };
  const select = h(
    "select",
    { id: id("plan"), "aria-describedby": id("note") },
    paid.map((plan) => h("option", { value: plan.id, text: `${plan.name} (${plan.provider})` })),
  );
  const [feeLabel, fee] = field("fee", "Monthly fee (pounds)");
  const [nowLabel, now] = field("now", "What you pay now (pence per kWh)", {
    step: "0.1",
    "aria-describedby": id("now-hint"),
  });
  const [baseLabel, base] = field("base", "Price the discount is taken off (pence per kWh)", {
    step: "0.1",
    "aria-describedby": id("note"),
  });
  const [withLabel, withPlan] = field("with", "Price with the plan (pence per kWh)", { step: "0.1" });
  const [kwhLabel, kwh] = field("kwh", "kWh you charge a month (optional)", { step: "1" });
  const note = h("p", { className: "hint", id: id("note") });
  const answer = h("p", { id: id("answer"), role: "status" });
  const baseRow = h("div", { className: "calc-base" }, baseLabel, base);
  if (Number.isFinite(payNow)) now.value = String(payNow);
  // For a discount plan the price with the plan is worked out from the base price, but
  // only when the base price changes, so a price the visitor types in is kept.
  const update = (event) => {
    const plan = paid.find((p) => p.id === select.value);
    const isDiscount = Number.isFinite(plan.discount_percent);
    baseRow.hidden = !isDiscount;
    if (isDiscount && (!event || event.target === base)) {
      const price = discounted(number(base), plan.discount_percent);
      withPlan.value = price === null ? "" : String(Math.round(price * 10) / 10);
    }
    answer.textContent = breakEvenText(
      breakEven({
        fee: number(fee),
        payNow: number(now),
        withPlan: number(withPlan),
        kwh: kwh.value.trim() === "" ? null : number(kwh),
      }),
      { here },
    );
  };
  const choose = () => {
    const plan = paid.find((p) => p.id === select.value);
    fee.value = String(plan.monthly_fee);
    withPlan.value = Number.isFinite(plan.ppk) ? String(plan.ppk) : "";
    base.value = "";
    note.textContent = Number.isFinite(plan.discount_percent)
      ? `${plan.price_text}. That price is not published openly, so enter it from the provider's app.`
      : Number.isFinite(plan.ppk)
        ? ""
        : "This plan's price per kWh is not published. Enter it if you know it.";
    update();
  };
  select.addEventListener("change", choose);
  for (const input of [fee, now, base, withPlan, kwh]) input.addEventListener("input", update);
  const body = h(
    "div",
    { className: "calc" },
    h("label", { for: id("plan"), text: "Plan" }),
    select,
    note,
    feeLabel,
    fee,
    nowLabel,
    now,
    h("p", { className: "hint", id: id("now-hint"), text: nowHint }),
    baseRow,
    withLabel,
    withPlan,
    kwhLabel,
    kwh,
    answer,
  );
  choose();
  return h("details", { className: "calculator" }, h("summary", { text: summary }), body);
}
