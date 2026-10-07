# 0002: OCPI adapter, data licences, privacy and disclaimer

Date: 2026-10-07. Status: accepted.

## OCPI 2.2.1 adapter (blueprint task 4)

- Section numbers refer to the OCPI 2.2.1 PDF linked from the blueprint. That link now
  redirects to `OCPI-2.2.1-d2.pdf`, whose footer reads "OCPI 2.2.1-d3-pre1".
- The adapter both fetches and converts records into the project's models, so a live run
  checks real data against the schema straight away.
- Paging follows the Link header, falls back to offset when only X-Total-Count is sent,
  refuses a next link to another site and stops if a link repeats.
- The client waits `min_seconds_between_requests` between calls, retries 429 and 5xx with
  backoff (honouring Retry-After), does not follow redirects, and adds keys only at the
  moment of sending, so saved URLs and error messages never contain them.
- Records that cannot be used are skipped and logged, as section 4.1.4.1 advises.
  Duplicates keep the last copy.
- Locations with `publish` false or missing are never kept (section 8.3.1).
- A value that is not valid OCPI becomes "unknown" with a logged issue. On 7 October 2026
  char.gy used the EVSE statuses `WORKING` and `FAULTED`. Regulation 10(6)(a) defines
  "working" as an OCPI status of available, charging or reserved, so `WORKING` cannot be
  mapped to one status without guessing.
- Power is `max_electric_power` if given, otherwise voltage times amperage times phases
  (three for AC_3_PHASE, where OCPI gives voltage line to neutral). Two-phase supplies get
  no figure, because OCPI does not say how to read their voltage.
- Currencies are kept as published. char.gy published tariffs in EUR, USD and GBP.
- Location `access` stays "unknown" for operator feeds, because OCPI has no direct field
  for it. Exceptional opening and closing dates are not represented yet.
- `--live` only runs for operators switched on in the registry.

## Tariff model changes

- `min_price` and `max_price` (excluding VAT) were added. A tariff is only
  `free_confirmed` if every component is zero **and** there is no minimum charge above
  zero.
- The `reservation` restriction and the tariff `type` were added.
- The VAT description now quotes OCPI: an omitted VAT means no VAT is applicable, which
  is different from 0%. It is still shown as "VAT not stated".

## Data licences

- The registry has a `licence` section. An operator can only be switched on once its own
  pages have been read and the date recorded in `licence.checked`.
- Jolt is switched off: its help page sat behind a bot check on 7 October 2026, so its
  terms could not be read.
- Apache-2.0 is stated to cover code only. `DATA_LICENCES.md` records each source's
  licence, attribution and the date its terms were checked.
- The DfT guidance sentence "Data must be open in line with the Open Government Licence"
  and regulation 10(5) were checked against the primary sources.

## Privacy and cookies

- PECR regulation 6 was replaced on 5 February 2026 by the Data (Use and Access) Act 2025,
  with exceptions in a new Schedule A1. The site rules in `docs/PRIVACY_AND_COOKIES.md`
  follow that text.
- Saving settings on the device is opt-in, so no cookie banner is needed as long as
  nothing else is stored.

## Disclaimer

`DISCLAIMER.md` holds the full text and a short version. The short version sits at the
top of the README and must appear on every page of the site.
