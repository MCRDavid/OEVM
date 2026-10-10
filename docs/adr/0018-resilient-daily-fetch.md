# 0018: A daily fetch that rides out refusals and keeps the last good copy

Date: 2026-10-09. Status: proposed.

In a daily run started by hand on 9 October 2026 (run 37969231568), char.gy's locations
feed answered HTTP 403 for offset 2800 after 56 pages, with a 4 second gap. The other
four operators were fetched and the site was deployed, but char.gy's 5,948 locations
dropped off the map and the run showed red. Across three refusals (8 and 9 October, gaps
of about 2.8 and 4 seconds, two networks) char.gy refused after 54 to 58 requests each
time, while a run with a 6 second gap fetched every page. That points to a limit on
requests over some minutes rather than a block on GitHub's network. This is inferred;
char.gy states no limit.

## Decisions

- **A refusal part-way through is waited out, not fought.** When a host that has
  already answered in this run answers HTTP 403, the client waits 5 minutes (or the
  server's own Retry-After or reset time), widens the gap to that host by half for the
  rest of the run, and asks for the same page again, at most twice per request. A 403
  to the first request to a host is not retried: that is a refusal, not a limit
  (GeniePoint, ADR 0010). A wait longer than 10 minutes stops the fetch, as before.
- **Rate limit headers are read.** The IETF RateLimit header (both draft forms) and the
  common RateLimit-*, X-RateLimit-* and X-Rate-Limit-* headers. When a server says no
  requests are left, nothing more goes to that host until its reset time plus the 1
  second margin. A 429 or 403 with a reset time but no Retry-After waits for the reset.
  Gaps only ever get longer; headers never make the client go faster than the operator
  file allows.
- **Error messages say who answered** (the Server header and the names of any rate
  limit headers), so a refusal by a CDN or firewall can be told apart from the feed.
- **A failed fetch says how far it got.** The run log keeps the pages, records and
  requests made before the error, for the feed health page.
- **The map keeps the last good copy.** When an operator fails, its map points and
  detail files are copied from the files last published, if that copy came from a live
  fetch, is at most 7 days old and still passes today's checks. The manifest marks it
  `kept_from_previous` and keeps its original fetch time, and every detail file keeps
  its own `fetched_at`, so nothing looks newer than it is. The feed health page says
  "Fetch failed; the map still shows its last good copy, fetched <date>".
- **Partial fetches are not published.** A fetch that stopped half way would show only
  some locations, and without the tariffs module every price would be unknown. The last
  complete copy is more useful and honest about its date.
- **The run is red only when the map lost an operator.** Exit code 3 (every failed
  operator kept its copy) leaves the run green with a warning; exit code 2 (an operator
  is missing from the map) still ends red, which also covers a copy older than 7 days.
- **char.gy's gap goes back to 6 seconds,** as its operator file said it would if the
  feed refused again.

## Not done

- **Smaller pages.** char.gy already serves at most 50 records a page and the limit
  looks like a request count, so smaller pages would mean more requests and earlier
  refusals.
- **Skipping a failed page.** Paging follows the server's Link header, so a skipped page
  cannot be stepped over safely, and a map with gaps would look complete when it is not.
- **Routing char.gy through the relay.** It was refused from a network other than
  GitHub's too, so the relay would not help, and using another address to get round a
  limit is what ADR 0010 rules out.
