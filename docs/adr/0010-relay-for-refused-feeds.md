# 0010: A relay for feeds that refuse the daily run

Date: 2026-10-08. Status: accepted.

In the first daily run from GitHub Actions (8 October 2026), GeniePoint's open data files
answered HTTP 403 to the first request, while the same files answered normally from
another network the same evening. The repository owner decided not to contact GeniePoint
and to fetch the files from somewhere other than GitHub's servers.

## Decisions

- **One Cloudflare Worker the owner runs** (`relay/worker.js`, named `oevm-relay`, free
  plan) fetches the operator's files for the daily run. Each relayed operator has its own
  path prefix on it, and all share the two GitHub secrets `OEVM_RELAY_URL` and
  `OEVM_RELAY_TOKEN`, so another operator needs only a new route and a recorded decision.
  The free plan allows 100 Workers per account (limits page, read 8 October 2026), so
  separate Workers would also be possible; one keeps setup and the token in one place. It is not a general proxy: it serves only the paths
  listed in its `ROUTES`, only GET, and only requests carrying a shared token in the
  `X-Relay-Token` header (a Worker secret and a GitHub Actions secret). It passes on the
  project's own User-Agent and nothing else from the request, passes the answer back as it
  came with only the headers OCPI paging needs, and never caches.
- **The operator file records the decision** (`relay` in `operators/geniepoint.yaml`):
  the date, the reason, the evidence (the run log), and the names of the two GitHub
  secrets holding the Worker's address and its token. The address is a secret too, so it
  is masked in the public run logs. Like the publish flag
  decision, only the owner adds one, and the transparency page shows it.
- **Nothing else changes.** `adapters/http.py` sends the request to the Worker only when
  both settings are present, under the same path and query. Gaps between requests,
  retries and every message still use the operator's own host and URLs, and records keep
  the operator's URLs as their source. Without either setting, requests go direct; with
  only one, the operator's fetch stops with a message, so a half-finished setup is noticed.
  The Worker passes the operator's Retry-After back, so a request to wait is honoured.
- **Only feeds that need no key may be relayed,** so no key ever passes through a third
  party. The registry refuses a relay on an operator with a key.
- **No disguise.** Requests still name the project and link to this repository, at the
  same pace, from one Worker. Addresses are never rotated and a browser is never
  imitated, so the operator can still see who is asking and refuse if it chooses.
- **Fixture replays never use the relay,** whatever the environment holds.

## Why

- Regulation 10(5) asks operators to make the data available to the public free of
  charge, and the files answer other networks normally, so the refusal looks aimed at
  GitHub's network rather than at this project. The owner weighed this against the DfT
  guidance that operators may set terms for the means of access, and chose the relay.
- Cloudflare's free plan allows 100,000 requests a day, does not count time spent waiting
  on the operator against its 10 ms CPU limit, and sets no response size limit; the
  daily run makes two requests (Cloudflare Workers limits page, read 8 October 2026).

## Needs testing

- Whether GeniePoint answers requests from Cloudflare's network. Only a run can show it.
- Whether the answer from the Worker is identical to a direct answer. The tests check the
  Worker passes status, body and paging headers through.

## Not done

- Contacting GeniePoint about the refusal (the owner chose not to).
- Relaying char.gy. It is first being tested at a slower pace (6 seconds between requests).
