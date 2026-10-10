# 0020: Prices from a related operator's tariffs

Date: 2026-10-10. Status: accepted.

PoGo Charge, Evolt Network and ChargePlace Scotland publish separate OCPI 2.2.1 feeds on
info.smartcharging.uk, and the terms pages of all three name SWARCO Smart Charging as the
network's operator. On 10 October 2026, 806 of PoGo Charge's 809 connectors named one of 5
tariff ids that are only in Evolt Network's tariff response, 462 ChargePlace Scotland
connectors named one of 11 that are only in Evolt Network's, and 2 Evolt Network connectors
named one that is only in ChargePlace Scotland's. Until now a connector was priced only from
its own operator's tariffs (ADR 0005), so all of these showed "Price unknown".

The repository owner decided the same day: "we should only match to another operator if
it's definitely matching for that site and that we're not matching operators together that
have no relationship and coincidental same tarrif names".

## Decisions

- **Opt-in per operator, by the owner only.** `tariffs_from` in the operator file records
  the date, the basis for treating the operators as related, evidence and the ids of the
  related operators. Without it, nothing is matched. The registry check refuses a decision
  that names the operator itself, an operator that is not in the registry, or one whose
  feeds are not on the same host as this operator's.
- **Only an exact, certain match.** A connector's tariff id is matched only when all of
  these hold:
  - its OCPI id is in the form of a UUID, so it names one record and cannot match another
    tariff by chance;
  - no tariff in the operator's own response has that OCPI id, under any country or party
    code;
  - exactly one tariff across all the named related operators' responses has that exact
    OCPI id (letter case included), with the same country code.
  Anything else stays unresolved and the price stays unknown. Tariff names and
  descriptions are never compared.
- **Only from the same run.** The related operator's tariffs are used only when it was
  fetched in the same run. A last good copy kept for a failed fetch (ADR 0018) holds no
  tariffs, so it is never used, and a run that fetches one operator alone matches nothing.
- **The tariff keeps its own provenance.** The matched tariff is published with its own
  id, provenance and price wording exactly as the related operator published it. Nothing
  is copied into the operator's own records.
- **Visible everywhere it matters.** Each tariff option at the location names the operator
  whose feed published it (`published_by`). The detail file lists each related feed used
  (`tariff_sources`) with a note, its attribution, its tariff feed URL, its licence and
  when it was fetched, and the map shows them under "Where this comes from". The manifest
  counts the connectors priced this way per operator (`priced_from_related`), and the
  publish report names the count. The transparency page shows the decision, and each
  operator file records the finding and how it is handled.

## Consequences

- PoGo Charge's, ChargePlace Scotland's and Evolt Network's connectors that name such
  tariffs show the price the related network publishes, instead of "Price unknown".
- The feed health page and the run report still measure each feed on its own, so they
  show these connectors as having a tariff that was not found in the operator's own data.
  That is the state of each feed as published.
- If the related operator's fetch fails, these prices show as unknown for that day.
