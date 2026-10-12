# 0021: Reading past one expired certificate, and leaving named locations off

Date: 2026-10-11. Status: accepted.

ParkRecharge publishes its OCPI 2.2.1 reference data on ocpi-pcpr.hubeleon.net. That
host's TLS certificate (for `*.hubeleon.net`, issued by Go Daddy Secure Certificate
Authority G2) expired on 7 October 2026 at 07:59 UTC. OpenSSL reports no other problem
with it: the chain leads to a trusted authority and the certificate names the host. Until
now an expired certificate stopped the fetch, as it should by default.

On 11 October 2026 the repository owner decided: "Let's bypass the certificate warning,
but note in transparency." The same day, on two locations in the file named as test units,
the owner decided: "Let's leave off the test ones".

## Decisions

- **Opt-in per operator, by the owner only.** `expired_certificate` in the operator file
  records the date, the basis, evidence, the host, the SHA-256 fingerprint of the one
  certificate accepted and the day it expired. Without it, nothing changes.
- **Only the dates are relaxed.** For such an operator the client uses httpx's usual TLS
  settings with OpenSSL's `X509_V_FLAG_NO_CHECK_TIME` added, so the chain and the host
  name are still checked. Verification is never turned off.
- **Only that one certificate.** Before a response body is read, the client reads the
  certificate the server presented. The response is used only if its fingerprint is the
  recorded one, or if the certificate is in date today. Any other certificate stops the
  fetch and is not retried. An old certificate whose key had leaked would be refused,
  because expired certificates are no longer tracked for revocation.
- **Self-retiring.** When the host presents a certificate that is in date, the run log
  says once per run that the decision can be removed, and the feed is read as normal.
- **Narrow by construction.** The registry check refuses the decision for a feed that
  needs a key (so no key is ever sent over such a connection), for a relayed feed, and
  when any of the operator's URLs is not https on the named host.
- **Visible.** The transparency page shows the decision, the expiry date and the
  fingerprint, and the operator's findings record the certificate and how it is handled.
- **Named locations left off.** `excluded_locations` in the operator file records the
  owner's decision to leave named locations off the map, such as test sites, by their
  exact OCPI id, with the date, basis and evidence. Each one is logged in the run's issues
  and counted as dropped, and the transparency page lists them by name and id. Without
  it, every location the feed marks for publishing is kept.

## Consequences

- ParkRecharge's 440 UK locations can be fetched daily while the certificate stays
  expired, less the two test sites. Its 7 Argentine locations are left off as outside the
  UK (ADR 0017); none of them lands in the UK with its coordinates swapped or a sign
  changed.
- If the host's certificate is replaced by another expired one, the fetch fails and the
  map keeps the last good copy (ADR 0018) until the owner decides again.
