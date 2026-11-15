# 0035: Visitors' own rates, kept on their device

Date: 2026-11-15. Status: proposed; the repository owner asked for it on 15 November 2026.

Under ADR 0034 a site's details say where paying an operator directly, for example in its
app, is cheaper than the price the map shows, without the price, because the operator's
terms keep its prices off the map. A driver who has found that price still sees the
higher one on the map. On 15 November 2026 the repository owner asked for the idea noted
in ADR 0034 under "Later": visitors type in the rates they found, so the map can use
them without this project publishing them. The owner added that AC and DC need their own
rates, as some networks, evyve for one, price them differently.

## Decisions (the owner, 15 November 2026)

- **"Your own rates", in the filters panel under "Your charging plans".** The visitor
  picks a network on the map and types in a price per kWh including VAT for its AC
  chargers, its DC chargers or both, with an optional note for themselves (up to 40
  characters, such as how they pay). Whole pence only, from 1p to 300p: no charger
  charges fractions of a penny (ADR 0003), and 0p is refused because it would read as
  free, which only an operator's confirmed free tariff is called.
- **The visitor's figures, never this project's.** They are used only in the page. This
  site does not check them, and never sends them anywhere, publishes them or puts them in
  the page address. Everything else on the map still comes from the feeds.
- **Kept on the device only after opting in.** Like ticked plans, own rates last only for
  the visit unless the visitor turns on "Remember my settings on this device", and
  "Forget my settings" deletes them with everything else (docs/PRIVACY_AND_COOKIES.md,
  rule 4).

## How it works

- `site/assets/js/rates.js` checks and words rates. Settings (`settings.js`) save them as
  `rates` in the `oevm.settings.v1` entry: a list of `{op, ac, dc, note}` holding only
  the parts given. An entry that is not whole pence from 1p to 300p is dropped when read.
- **Map and list labels** (ADR 0026) take the lowest of the connector prices, a ticked
  plan and the visitor's own rate: the AC rate for each AC connector and the DC rate for
  each DC connector that matches the filters, from the feed's `power_type`. A connector
  whose feed gives no `power_type` gets neither. Free still comes first, a rate above the
  visitor's maximum price is not shown, and on a full tie the operator's own price is
  kept, then a ticked plan's. A label from an own rate is drawn like one from a ticked
  plan (amber, with a thicker edge), and the list says "with your own rate".
- **A site's details** say "Cheapest here: 48p per kWh with your own DC rate for this
  network, typed in by you." when the label comes from it, and under the cheapest price,
  "Your own rates for this network", the rates and note, that they were typed in by the
  visitor and have not been checked, and a "Change your rates" button that opens them in
  the filters panel. Where ADR 0034 says paying the operator directly is cheaper and the
  visitor has no rate for it yet, a "Type in a rate you found" button does the same.
- Rates are kept per network, as on the map, not per roaming provider: a visitor who pays
  through a roaming app types its rate in for each network they use with it.

## Not done

- Times and days: a rate applies all the time. A visitor whose rate differs at weekends
  can note it and change it when they charge.
- Sharing rates between devices or visitors: not planned, as nothing leaves the device.
