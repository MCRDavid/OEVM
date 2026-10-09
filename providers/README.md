# Charging plan providers

One file per provider a driver can pay for charging through: a roaming app such as Octopus Electroverse, or an operator's own app and subscriptions. The map lists each plan under "Other ways to pay here" at the networks it covers, and the calculator uses its fee and price. Design: [ADR 0016](../docs/adr/0016-charging-plans.md). Rules: [schema/provider.py](../schema/provider.py).

Check every file with:

```
uv run python -m pipeline.plans --validate
```

## Rules

- Copy plans by hand from the provider's own published pages, never from comparison sites, blogs or forums. Each plan needs the page URL, an exact quote and the date it was read.
- Read the provider's terms first and record what they say about reuse in `terms.reuse`, with the clause word for word:
  - `no_restriction_found` or `attribution`: plans may be listed. For `attribution`, put the wording asked for in `terms.attribution`.
  - `forbidden`, `personal_use_only` or `not_read`: list no plans. Keep the file so the check is recorded, and see "Permission requests" below.
- Never estimate. A fee or price that is not published is `null`. A discount stays a discount ("25% off ..."); never work out a price from it.
- A plan gives a fixed price or a discount, never both, and must publish at least one of a fee, a price or a discount.
- When the provider's own pages disagree, keep the figure from the main pricing page and explain in `needs_testing`; the map shows that note.
- Set `operator_ids` only to ids that have a file in `operators/`, so the plan shows at those networks' chargers.
- British English, neutral wording, no em dashes. Never use a provider's logo or suggest it endorses the project.

## Adding a provider or plan

1. Copy `_template.yaml` to `<id>.yaml` (lower case, underscores).
2. Read the provider's terms and fill in `terms`, with today's date in `checked`.
3. If reuse is allowed, add each plan from the provider's own pages with its exact quote and date.
4. Run `uv run python -m pipeline.plans --validate` and `uv run pytest -q tests/test_plans.py`.
5. Build the map files (`uv run python -m pipeline.run --fixtures --publish build`) and check the plan in `build/data/plans.json`.
6. Open a pull request with one provider per change.

Re-check listed plans regularly: prices change often, and each plan shows the date it was checked.

## Listed providers (10)

| Provider | Plans | Terms |
|---|---|---|
| Be.EV (`be_ev`) | 9 | No restriction found |
| Bonnet (`bonnet`) | 3 | No restriction found |
| char.gy (`chargy`) | 3 | No restriction found |
| Connected Kerb (`connected_kerb`) | 4 | No restriction found |
| Octopus Electroverse (`electroverse`) | 9 | No restriction found |
| Evolt Network (`evolt`) | 0 | No restriction found |
| Fastned (`fastned`) | 3 | No restriction found |
| MFG EV Power (`mfg_ev_power`) | 2 | No restriction found |
| Plugsurfing (`plugsurfing`) | 1 | No restriction found |
| Pod (`pod`) | 0 | No restriction found |

## Permission requests (20 providers)

The owner decided on 9 October 2026 to list plans only where the provider's terms allow reuse, and to ask the others in writing. As of 9 October 2026 the request below is drafted but **not yet sent** to any provider.

| Provider | Why no plans are listed | Request |
|---|---|---|
| Allstar Chargepass (`allstar`) | Terms could not be read | Not sent |
| Arnold Clark Charge (`arnold_clark_charge`) | Terms restrict copying or reuse ([terms](https://www.arnoldclark.com/terms-of-use)) | Not sent |
| Believ (`believ`) | Terms restrict copying or reuse ([terms](https://www.believ.com/legal-notices/)) | Not sent |
| bp pulse (`bp_pulse`) | Terms restrict copying or reuse ([terms](https://www.bppulse.com/en-gb/legal-notice)) | Not sent |
| Chargemap (`chargemap`) | Terms restrict copying or reuse ([terms](https://community-optins.chargemap.com/conditions/3/document?locale=en_GB)) | Not sent |
| EVYVE (`evyve`) | Terms restrict copying or reuse ([terms](https://evyve.co.uk/terms-and-conditions/)) | Not sent |
| GeniePoint (`geniepoint`) | Terms could not be read | Not sent |
| GRIDSERVE Electric Highway (`gridserve`) | Terms restrict copying or reuse ([terms](https://www.gridserve.com/legal-area/website-customer-self-service-portal/)) | Not sent |
| InstaVolt (`instavolt`) | Terms allow personal use only ([terms](https://instavolt.co.uk/app-terms-conditions/)) | Not sent |
| IONITY (`ionity`) | Terms restrict copying or reuse ([terms](https://www.ionity.eu/policies/imprint)) | Not sent |
| Jolt (`jolt`) | Terms restrict copying or reuse ([terms](https://joltcharge.com/uk/terms/)) | Not sent |
| Mer UK (`mer`) | Terms restrict copying or reuse ([terms](https://uk.mer.eco/mer/legal/terms-and-conditions/)) | Not sent |
| Osprey Charging (`osprey`) | Terms allow personal use only ([terms](https://www.ospreycharging.co.uk/terms-conditions)) | Not sent |
| Paua (`paua`) | Terms restrict copying or reuse ([terms](https://www.paua.com/downloads/paua-driver-terms)) | Not sent |
| Raw Charging (`raw_charging`) | Terms restrict copying or reuse ([terms](https://rawcharging.com/legal-information)) | Not sent |
| Sainsbury's Smart Charge (`sainsburys_smart_charge`) | Terms restrict copying or reuse ([terms](https://smartcharge.co.uk/)) | Not sent |
| Shell Recharge (`shell_recharge`) | Terms restrict copying or reuse ([terms](https://www.shell.co.uk/terms-of-use.html)) | Not sent |
| Tesla Supercharger (`tesla`) | Terms could not be read ([terms](https://www.tesla.com/legal/terms)) | Not sent |
| ubitricity (`ubitricity`) | Terms restrict copying or reuse ([terms](https://ubitricity.com/en/legal-notice/)) | Not sent |
| Zapmap (`zapmap`) | Terms restrict copying or reuse ([terms](https://www.zapmap.com/terms-of-use)) | Not sent |

For a provider whose terms could not be read, read them first (in a browser if an automated fetch is refused); a request is only needed if they restrict reuse.

### What's needed to add a provider from this list

1. Send the request below through the provider's own contact or press page. Do not copy contact details into this repository.
2. Update its row above: "Sent <date>", then the outcome. Record the channel and date only, never names or addresses.
3. If the provider agrees, save its reply with names and contact details removed under `evidence/providers/<id>/`, quote the permission in `terms.quote`, set `terms.reuse` to `attribution` (with the wording it asks for) or `no_restriction_found`, and add its plans as in "Adding a provider or plan". The research from 9 October 2026 already lists their published plans; re-check each page before copying.
4. If it declines or does not reply, leave `plans: []`. Its prices still show wherever its own open data feed publishes them.

### The request

> **Subject:** Permission to show your published charging prices on a free, open EV charger map
>
> Hello,
>
> I run OEVM (https://mcrdavid.github.io/OEVM/), a free, non-commercial map of UK public EV chargers built from operators' open data under the Public Charge Point Regulations 2023. It has no adverts, no tracking and no accounts. The code is public at https://github.com/MCRDavid/OEVM.
>
> I would like to help drivers compare ways to pay at each charger, including your published prices and subscriptions. Your website terms restrict copying content, so I am asking before I include anything.
>
> What I would show: the name of each plan, its monthly fee and its price per kWh or discount, exactly as published on your website, with a link to your page and the date it was checked. I would not copy anything else, use your logo, or suggest that you endorse the map. I would remove or correct anything on request.
>
> Could you let me know whether this is acceptable, and if so whether you would like a particular attribution wording? If you publish this information in a form meant for reuse, a link to it would be very welcome.
>
> Thank you,
> OEVM
