# 0029: Showing a copy of its data that an operator sent

Date: 2026-10-29. Status: accepted.

Connekt (party GB CON) answered the project's open data request of 24 October 2026 on
26 October by email. The email attached two OCPI 2.2.1 responses, one for locations and
one for tariffs, made at 14:22 UTC that day, and gave no address to fetch the data from
and no key. The files hold 362 locations, mostly in Scotland, and 326 GBP tariffs.

Regulation 10(5) of the Public Charge Point Regulations 2023 asks for the data to be
"made available to the public free of charge and in a machine readable format". It does
not name an API or a feed. The DfT guidance (updated 21 October 2024) says the data must
be able to be communicated to anyone who wished to receive it, calls an API "the most
widely used method" and says "Other methods may be feasible". So the project is asking
Connekt for an address it can fetch, quoting the guidance and claiming no breach. Until
one comes, the emailed files are the only copy of Connekt's data the project has.

Until now the map only showed data fetched from an operator's own feed, and ADR 0018
keeps a failed operator's last good copy for at most 7 days, so nothing on the map was
more than a week old. A copy sent once cannot meet that.

On 29 October 2026 the repository owner decided to map Connekt's copy, dated as made and
with every charge point status unknown, as an exception to the 7 day rule.

## Decisions

- **A new adapter, `sent_copy`, and an owner's decision field, `sent_copy`.** The field
  records when the owner decided and why, the saved message (`evidence_file`), how the
  copy came (`channel`), the day it arrived (`received`), when the operator made it
  (`made_at`, with a time zone) and the two files. The registry refuses one without the
  other, a sent copy with feed URLs, a key, the relay or an expired certificate bypass,
  files outside `sent_copies/<operator id>/`, missing files, and a copy made after the day
  it arrived. Never add one without the owner's decision.
- **The files are kept exactly as sent.** They are gzipped, because each must stay under
  the repository's 500 KB file limit, and `sent_copies/<operator id>/README.md` gives the
  SHA-256 of the bytes as received so anyone can check them. A test checks them too.
  The message they came with is saved in `evidence/<operator id>/`, with names and
  addresses removed, as for any other reply.
- **They are read on every run and no request is made.** The records go through the same
  conversion as a fetched OCPI 2.2.1 feed, so the publish flag, the UK check, the stated
  VAT and every other rule apply.
- **Dated as made.** Every record carries `made_at` as its fetch time, never the time of
  the run, its provenance method is `operator_static_file`, and its source is the folder
  that holds the files.
- **Status is never shown.** A status in a file sent once says nothing about now, so every
  charge point is shown as status unknown, and no connector is marked out of service
  from the copy. The run log says how many statuses were set aside.
- **Said wherever the data is shown.** Each location's details carry a note naming the
  operator, the channel, the day it arrived, when the copy was made and the owner's
  decision, and say it is not updated. The price hint says prices may have changed, and
  "Where this comes from" links the files rather than a feed. The manifest carries the
  same note. The feed health page shows the operator in yellow with "Not fetched: the
  map shows a copy the operator sent on <date>". The transparency page says no requests
  are made and links the files and the saved message.
- **The exception to the 7 day rule.** A sent copy is shown for as long as the owner's
  decision stands, however old it is, because it is the operator's own data and its date
  is shown everywhere. The 7 day rule still applies to every fetched feed. If the files
  cannot be read, that counts as a failed fetch: ADR 0018's last good copy is measured
  from `made_at`, so once the copy is more than 7 days old nothing is kept, the operator
  leaves the map and the run reports it.
- **Licence and attribution** as for any other operator: the data keeps its source's
  licence, read under the owner's standing rule on regulation 10 data, with a row in
  `DATA_LICENCES.md`.

## Consequences

- Connekt's 362 sites are on the map from the next daily run, with prices as sent on
  26 October 2026 and statuses unknown. Its engagement status stays
  `no_public_feed_found` and the request for an address carries on.
- When Connekt gives an address, its operator file moves to a fetching adapter and the
  `sent_copy` decision and files are removed. If Connekt sends a newer copy instead, the
  owner decides whether it replaces this one.
- Another operator that sends files instead of an address can be shown the same way, but
  only after the owner decides for that operator.

## Later decisions

- 29 October 2026: the repository owner decided to show Zest's copy (party GB ZST) the same
  way. Zest emailed it on 28 October 2026, made on 26 October, and asks for its form to be
  completed monthly for an updated snapshot. By the same decision, each newer copy Zest
  sends replaces the one shown without a new decision (`operators/zest.yaml`,
  `sent_copies/zest/README.md`). Zest's data is licensed under CC BY 4.0, as its open data
  page states, so its attribution names that licence and says the data is adapted.
