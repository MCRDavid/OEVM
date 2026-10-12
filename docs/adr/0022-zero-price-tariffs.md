# 0022: Zero-price tariffs the owner does not show as free

Date: 2026-10-11. Status: accepted.

ScottishPower Recharge's tariff response of 11 October 2026 holds a tariff described as
"Harbour test" whose energy, flat and time prices are all zero, with no minimum charge. The
2 connectors at its Glengarry location name it. Under ADR 0002 a tariff like that is
`free_confirmed`, so the map would show those connectors as "Free".

The description suggests the tariff may not be the price drivers pay there. On 11 October
2026 the repository owner chose, on a decision card, to show those connectors as "Price
unknown".

## Decisions

- **Opt-in per operator, by the owner only.** `zero_price_tariffs` in the operator file
  records the date, the basis, evidence and the tariffs it covers. Without it, a tariff
  whose prices are all zero shows as free, as before.
- **Only by exact id.** Each tariff is named by its OCPI id exactly as the feed sends it.
  Names and descriptions are never matched, so no other tariff is caught by a similar
  description. Only the operator's own tariffs are matched, never one priced from a
  related operator (ADR 0020).
- **Only while every price is zero.** The decision applies only while the tariff is
  `free_confirmed` as published. If the operator gives it a price, that price is shown.
- **The data is not changed.** The tariff is published unchanged in the location's detail
  file, with its `price_state` as the operator's prices give it. Only the wording changes:
  pipeline/pricing.py shows "Price unknown" with the reason, the connector gets no
  indicative price per kWh, and the site's tariff list shows that tariff as unknown.
- **Visible.** The transparency page shows the decision, and the operator file records the
  finding and how it is handled.

## Consequences

- The 2 connectors at Glengarry show "Price unknown" while the tariff's prices are all
  zero, and are not counted as free by the map's free filter.
- The feed health page and the run report still measure the feed as published, so they
  count those connectors as free.
- The operator file holds the tariff's id, which looks like a key to the key scans; the
  scans allow that exact id as a record id the operator publishes in its open data.
