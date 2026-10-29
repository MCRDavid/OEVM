# Sent copies

Copies of operators' charge point data that the operator sent to this project, for
example attached to an email, because it publishes none at an address that can be
fetched. One folder per operator id: `sent_copies/<operator id>/`.

A copy is shown on the map only where the operator file records the repository owner's
decision in `sent_copy` (ADR 0029, `docs/adr/0029-sent-copies.md`). The `sent_copy`
adapter (`adapters/sent_copy.py`) reads it on every run without making any request. The
map says the data is a copy, when it was sent and made, and that it is not updated; every
charge point status is shown as unknown.

Rules:

- Each file is the operator's OCPI 2.2.1 response exactly as received, gzipped. Nothing in
  it is changed. Name each file by the date received and the module, for example
  `2026-10-26-locations.json.gz`.
- The message that came with the copy is saved under `evidence/<operator id>/` with names
  and addresses removed, and logged in the operator file's `engagement.log`.
- When the operator publishes its data at an address that can be fetched, switch the
  operator to that feed and delete its folder here. A newer copy replaces the older one.
- The data keeps its source's licence and attribution (`DATA_LICENCES.md`). This
  repository's Apache-2.0 licence does not apply to it.
