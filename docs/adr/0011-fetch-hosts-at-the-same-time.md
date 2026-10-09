# 0011: Fetch operators on different hosts at the same time

Date: 2026-10-09. Status: proposed.

The daily run fetched every operator one after another (ADR 0009). The repository owner
asked whether the fetch could be faster, within every operator's published rate limits,
now that the project has a relay on Cloudflare Workers (ADR 0010).

## Timings

From run 37860826824 (8 October 2026, the last full run before this decision), the fetch
step took 14 min 3 s:

| Operator   | Requests | Gap kept | Time      | Limit source                       |
|------------|----------|----------|-----------|------------------------------------|
| char.gy    | 120      | 6 s      | 13 min 36 s | none published; 6 s is our choice |
| GeniePoint | 2        | 2 s      | about 7 s | none published                     |
| Jolt       | 6        | 2 s      | about 19 s | none published                    |

char.gy is 97% of the run. Its server returns at most 50 locations a page, and the gap was
raised from 2 to 6 seconds after it answered HTTP 403 part-way through the first run
(operators/chargy.yaml, findings).

## Options looked at

- **The relay.** It does not change any limit: the relay keeps the same User-Agent and
  the same gaps, timed on the operator's own host (ADR 0010, CLAUDE.md). It must not be
  used to get round a refusal that may be about request rate. Not used to speed anything.
- **Only fetch what changed (OCPI date_from).** char.gy supports it, but the recorded
  fixture shows 551 of 5,946 locations changed in about 90 minutes
  (tests/fixtures/chargy/locations_since_page1.json), so a daily change list would be
  close to the whole feed, and removed locations would need extra handling. Not worth it
  now.
- **Bigger pages.** char.gy caps pages at 50. Not possible.
- **A shorter gap for char.gy.** Possible, as no limit is published, but the 6 s gap
  follows a refusal. The owner decided on 9 October 2026 to try 4 s (operators/chargy.yaml):
  about 4 minutes shorter a run. If char.gy refuses requests again, the gap goes back to
  6 s.
- **Fetch operators on different hosts at the same time.** Allowed by CLAUDE.md ("Never
  run two fetches that use the same host in parallel"). Chosen.

## Decisions

- **`pipeline.run.host_groups`** splits the enabled operators into groups that share no
  host: every endpoint host, the base URL host, and the relay. Two operators share a group
  when they share a host directly or through another operator. All relayed operators are
  in one group, so the relay never carries two fetches at once. Operators with no known
  host share one group.
- **Each group runs in its own thread**, one operator at a time within the group, in
  registry order. Gaps, Retry-After holds and timers are unchanged and still per host
  (`adapters/http.py`), so no host sees any more requests, or any sooner, than before.
- **Results, logs and the report** keep registry order whatever order groups finish in.
  A failure still fails only that operator.
- **Progress lines** are printed whole and start with the operator id, so interleaved
  lines from different groups still read clearly.

## What it saves

Today almost nothing: GeniePoint and Jolt (about 26 s) now run while char.gy is fetched,
so the run takes about as long as char.gy alone. The gain grows as operators on other
hosts are switched on. Gridserve allows one request every 30 seconds (31 s with our
margin), and the four operators on open-chargepoints.com share 29 requests an hour; one
after another, those would add their whole time on top of char.gy's. In groups, the run
takes as long as its slowest group.
