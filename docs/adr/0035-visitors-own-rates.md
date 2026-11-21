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
- Rates are kept per network, as on the map. A roaming card or app that works on many
  networks is typed in once under "Your own cards" (amendment below).

## Not done

- Times and days: a rate applies all the time. A visitor whose rate differs at weekends
  can note it and change it when they charge.
- Sharing rates between devices or visitors: not planned, as nothing leaves the device.

## Amendment: visitors' own cards (21 November 2026)

On 21 November 2026 the repository owner asked for the same idea for roaming cards and
memberships whose prices this project cannot show: the visitor fills in the blanks,
picks the networks a card covers, and the map uses what it charges there. The owner
added that a card's AC and DC prices may not be the same on every network it covers,
and that some give a percentage off, as the deal a roaming provider has with each
operator is largely unknown. Of the options put to the owner (a card with its own
prices, the same with a percentage off, or rates per network only), this follows the
second.

### Decisions (the owner, 21 November 2026)

- **"Your own cards", in the filters panel under "Your own rates".** The visitor names a
  card (up to 40 characters), ticks the networks it works on and types in what it
  charges on every ticked network: a price per kWh including VAT for AC, DC or both
  (whole pence, 1p to 300p, as for rates), or a percentage off the price the map shows
  (above 0 and up to 90%, to a tenth: more would show a price close to nothing, which
  could read as free). Where a network differs, the visitor adds that network's own
  figures, which are used there instead. A monthly fee (£0 to £100) and a note are
  optional. Up to 20 cards.
- **Starting from a listed roaming card.** The roaming cards and apps this site lists
  (providers of kind `roaming` in `data/plans.json`) can be picked to start from: their
  name is filled in and their networks on the map are ticked, as listed. Their prices are
  not filled in, so a restricted provider's prices are never shown or guessed. Operators'
  own apps are left out, as "Your own rates" is for those.
- **The visitor's figures, never this project's**, kept on the device only after opting
  in, exactly as for own rates above.

### How it works

- `site/assets/js/cards.js` checks and words cards; `cardform.js` is the form. Settings
  save them as `cards` in the `oevm.settings.v1` entry: a list of `{id, name, ops, ac,
  dc, pct, fee, note, nets}` holding only the parts given, where `nets` maps a network id
  to its own `{ac, dc, pct}`. A card with no name, no network or no figure is dropped
  when read.
- **What a card charges on a network**, for AC or DC: that network's own price, then its
  own percentage off, then the card's price for every network, then its percentage off.
- **A percentage off** is taken off each connector's own published price including VAT,
  to the whole penny, half pennies up (ADR 0003). It gives nothing on a connector with no
  published price, or whose VAT is not stated, and never makes a price free. It is the
  visitor's assumption: a roaming app's discount is often off its own price at that
  network rather than the operator's, and the form says it is taken off the price shown.
- **Map and list labels** take the lowest of the connector prices, a ticked plan, the
  visitor's own rate for the network and each of their cards that works on it; on a tie
  the operator's price is kept, then a ticked plan's, then the own rate, then the card
  added first. The list says "with your card “name”".
- **A site's details** say "Cheapest here: 60p per kWh with your card “name”: its DC
  price, typed in by you." (or "10% off the published price, as you typed in."), list
  each card that works there with its figures for that network, and have a "Change your
  cards" button. A card with a monthly fee is offered in the subscription calculators,
  marked as the visitor's own, rather than being where "What you pay now" starts.

### Not done

- Network lists for restricted roaming providers (Zapmap, Shell Recharge's roaming and
  others whose terms keep their pages off the map): the visitor ticks the networks.
- Checking where a restricted card is really cheaper, to say so without figures under
  ADR 0034: a separate piece of research.
