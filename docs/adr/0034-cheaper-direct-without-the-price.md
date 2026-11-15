# 0034: Saying where paying an operator directly is cheaper, without the price

Date: 2026-11-15. Status: accepted by the repository owner on 15 November 2026.

On 15 November 2026 the repository owner pointed out that evyve is cheaper to pay through
its own app, especially at weekends, than the price the map shows. evyve's pricing page,
read that day, confirmed it: paying in its free app costs less than paying by contactless,
and less again at weekends and on bank holidays. evyve's open data feed gives one price
per connector, with no tariff type and no day or time restrictions, and at 300 of its 307
DC connectors that price is the contactless price on the page (finding of 15 November
2026 in `operators/evyve.yaml`).

evyve's website terms allow its website to be used for personal, non-commercial use only
and say it must not be copied or published, so under ADR 0016 its plans and prices are
not listed, and its locations' details say only that memberships or subscriptions may be
available. Many operators are in the same position (`providers/README.md`).

## Decisions (the owner, 15 November 2026)

- **Say that it is cheaper, not by how much.** Where an operator's own pages show that
  paying it directly, in its app or on its website, is cheaper than paying at the
  charger, the details of its locations say so, with whether a subscription is needed,
  and point the visitor to its own website or app. No price, figure or comparison amount
  is given, so nothing of the operator's pricing is reproduced.
- **Nothing is quoted from the operator's pages.** What the page said is recorded in this
  project's own words, with the page's address and the date it was checked. A copy of
  the page is kept outside the repository as private evidence, and is never published.
- **Dated and attributed.** The note says what the operator's website said "when last
  checked on" the date, so a visitor can see how old it is and check the page.
- **For every operator where it applies, not only evyve,** each checked by hand on its own
  pages and added to its provider file.

## How it works

- `providers/<id>.yaml` takes a `cheaper_direct` list (`schema/provider.py`). Each entry
  gives how to pay (`pay_by`, words that follow "Cheaper", such as "in the evyve app"),
  what it is cheaper than (`cheaper_than`, such as "paying by contactless"),
  `needs_subscription`, an optional `conditions` sentence in this project's words (such as
  "Lowest at weekends and on bank holidays."), `only_where_dc`, a `feed_check` saying how
  the feed's price compares with the page's price at the charger, and `source` (the page's
  address, what it `said` in this project's words, and the date `checked`).
- The checker refuses an entry with a price in any of its text (pounds, pence or a figure
  per kWh), one with a quote, one whose page is not on the provider's own website, one
  without `own_networks`, and one for a provider whose terms allow reuse: there the plans
  themselves are listed with their prices instead (ADR 0016).
- `data/plans.json` carries each entry, worded by `pipeline/publish.py`, under the
  operator's `withheld` entry. Under "Cheapest here" a site's details then show one line
  for each entry and one closing line, for evyve: "**Cheaper in the evyve app** than paying
  by contactless. No subscription needed. Lowest at weekends and on bank holidays." and
  "According to EVYVE's website when last checked on 15 November 2026. Its website terms do
  not allow its prices to be shown here, so check EVYVE's website or app before you
  charge.", linking to the terms and to the page that was checked. This takes the place of
  the note of ADR 0016 at those locations.
- **Only where the map shows the price at the charger.** An entry is added only after the
  operator's feed has been compared with the page, because "cheaper" is only right where
  the map shows the higher price. evyve's 7 to 22 kW chargers can only be operated in its
  app, so they have no contactless price; `only_where_dc` gives the note only at
  locations with a DC charger, and its other locations keep the note of ADR 0016.
- Map labels and "Cheapest here" are unchanged: they still come from the feed and from
  plans the visitor ticked (ADR 0026).

## The first entries (15 November 2026)

Twelve operators whose terms keep their prices off the map were checked on their own
pages and against their feeds that day:

- **Added:** evyve (its app), IONITY (signing up in its app, and a subscription), bp pulse
  (a subscription; paying as you go in its app costs the same as contactless), Jolt (its
  app gives some free charging each day), Source EV (a free membership, and a paid one;
  DC locations only), ESB Energy (a membership; its feed already gives the pay as you go
  price, and contactless costs a little more, which the note says), ESB ecars (a
  membership) and ubitricity (a Shell Recharge subscription).
- **Not added:** Mer UK (a registered user saves very little, and only at locations on
  its guest tariff, which the note cannot pick out), Arnold Clark Charge (its subscription
  is already listed with its price as an Octopus Electroverse plan) and RAW Charging (no
  comparison published). Allego's UK prices and Shell Recharge's pricing page could not be
  read from the cloud, so they need checking in a browser.

## Amendments to earlier decisions

- ADR 0016: an operator with a `cheaper_direct` entry has that note, under the cheapest
  price, in place of the note that its memberships or subscriptions may be available.
- ADR 0033: the cheaper note is kept in view, under "Cheapest here".

## Later

- The owner's idea for later: visitors type in the rates they found for a provider, kept
  on their own device only after they opt in, as ticked plans are, so the map can use
  them without this project publishing them.
- If an operator adds its app prices to its open data feed (OCPI 2.2.1 can carry an app
  tariff of type REGULAR beside a contactless one of type AD_HOC_PAYMENT, with
  `day_of_week` and `start_time` restrictions), they show from the feed with their days
  and times, and its `cheaper_direct` entry is removed.
