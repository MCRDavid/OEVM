# 0016: Charging plans, the cheapest way to pay and the subscription calculator

Date: 2026-10-09. Status: proposed.

The owner asked for every tariff at a site to be listed, with readable names, for prices
behind a subscription to be shown with what the subscription costs, for roaming
providers such as Octopus Electroverse to be included, for visitors to pick the plans
they already have, and for a calculator showing when a paid plan pays for itself.

## Decisions

- **Two sources, chosen by the owner on 9 October 2026:** prices from operators' own open
  data feeds where they exist, plus a list copied by hand from each provider's own
  published pages for subscriptions and roaming plans. Feeds rarely say what a
  subscription costs, and roaming apps such as Electroverse show per-charger prices only
  in the app (its terms: "Electroverse sets the applicable energy and time-based rates,
  which can be found on our Electroverse app").
- **One file per provider in `providers/`,** checked by `schema/provider.py` and
  `uv run python -m pipeline.plans --validate`. Each plan records the provider's page, an
  exact quote and the date it was read, as rate limits do. Values that are not
  published are null, never estimated. Where a provider's own pages disagree, the plan
  carries a `needs_testing` note, which the map shows.
- **Provider terms come first,** as for operators. A file records what the terms say about
  reusing content (`no_restriction_found`, `attribution`, `personal_use_only`,
  `forbidden`, or `not_read` when the terms could not be read) with the clause word for word.
  Plans are listed only for the first two;
  the model refuses plans otherwise. Providers whose terms forbid reuse keep a file so
  the check is recorded. The owner chose on 9 October 2026 to ask them in writing; the
  request, its status per provider and the steps to add a provider that agrees are in
  `providers/README.md`.
- **Discounts are never turned into prices.** "25% off Electroverse's own price" is shown
  as that, because the price it comes off is not published openly. The calculator asks
  the visitor for it.
- **Plan wording comes from `pipeline/pricing.py`** (`plan_fee_text`, `plan_price_text`),
  like every other price. The only money the browser works out is the calculator's
  answer, from numbers the visitor enters or confirms; it shows its working and says it
  is a guide only.
- **"Your charging plans" stay in the browser.** Ticked plans are kept in memory, and
  saved with the other settings only after the visitor turns on "Remember my settings"
  (docs/PRIVACY_AND_COOKIES.md, rule 4). They are never sent anywhere.
- **The cheapest line compares like with like:** energy prices that include VAT, from the
  operator's tariffs and from fixed-price plans. Other charges are not compared.

## Needs testing

- The figures where a provider's own pages disagree (marked in the provider files).
- Which networks each roaming plan covers, where the provider's page does not say.
