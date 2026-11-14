# Pod's prices exclude VAT after all

From 29 October to 14 November 2026 the map showed Pod's prices about a sixth lower than drivers
pay. Pod's feed states VAT at 20% beside each price, and we had read that VAT as already in the
price. On 14 November 2026 Pod's app showed 44p per kWh for a 7 kW connector whose tariff in the
feed gives 0.37 with VAT 20. With 20% added, 0.37 is 44.4p, so the feed follows OCPI 2.2.1 and its
prices exclude VAT. The map now adds it.

## What we had decided, and why

OCPI 2.2.1 gives each price excluding VAT, with the VAT rate alongside. Not every feed follows
that, so on 29 October 2026 the project owner decided how to read three networks on Eco-Movement's
platform whose prices state VAT at 20% but are all whole pence as published: Pod, ESB Energy and
ESB ecars. Every one of Pod's 823 energy prices that day was a whole number of pence, most often
38p and 42p per kWh, while only 121 would have been once 20% was added. A whole number of pence
looked like a price set for drivers, so the owner decided the stated VAT was already in them. The
[post of 29 October](findings/eco-movement-networks/) says so, and that this was
inferred from the figures and needed confirming by each network.

## What showed it was wrong

On 14 November 2026 a check of Pod's app gave 44p per kWh for one 7 kW connector. In that morning's
daily fetch its tariff had one energy price, 0.37 with VAT 20, every day of the week, and the map
showed 37p. 0.37 with 20% added is 44.4p, which the app showed as 44p. That day 642 of Pod's 1,795
sites on the map had a connector priced at 37p, more than any other price.

One reading is that Pod publishes its prices without VAT, rounded to whole pence: 44p divided by
1.2 is 36.7p, which rounds to 37p. That is inferred from one price and needs confirming by Pod.
Either way, whole pence as published did not show that VAT was already in a price.

## What changes

On 14 November 2026 the owner withdrew the decision for Pod. Its stated VAT is now added, as for
any feed that states its VAT rate, so every Pod price on the map is a fifth higher than before:
37p becomes 44.4p, 42p becomes 50.4p and 52p becomes 62.4p. The feed does not say whether Pod
charges 44p or 44.4p, so a price on the map can differ from the app's by part of a penny. The
tariffs are published unchanged, and the [transparency page](transparency/) shows the dated
record in Pod's row.

The decisions for ESB Energy and ESB ecars rest on the same reading of whole pence. They are
unchanged and still need confirming by each network. If a price on the map does not match what a
network charges, please [report a mistake](report/).
