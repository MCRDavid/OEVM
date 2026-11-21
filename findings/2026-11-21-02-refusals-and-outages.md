# Refusals and outages: three feeds in November

Between 13 and 21 November 2026 three feeds refused requests or failed in ways their published
documents do not explain. Eco-Movement's platform answered some requests with HTTP 429, "too many
requests", while every network's token was within its published limits. Monta's server timed out on
one page of its list for a day. Roam's locations address has answered HTTP 502 since 16 November
2026, so the map still shows Roam's chargers as they were that morning.

Since 13 November 2026 every request that is tried again is listed, with its answer, in each run's
log and on the [feed health page](status/).

## Eco-Movement: refused within its published limits

The map reads 23 networks through Eco-Movement's platform, each with its own token. Eco-Movement
publishes a rate limit for each part of its feed, and since 29 October 2026, by the project owner's
decision, each token's limit is used as an hourly allowance, with no more than five requests at once
(see [the post on Eco-Movement's networks](findings/eco-movement-networks/)). Under that rule, if
anything goes wrong, every network goes back to one request at a time, each token 125 seconds after
its last.

From 30 October 2026 most daily runs went back that way within their first seconds, so the daily
fetch took about 31 minutes rather than 17. No published limit was passed: spacing requests out is
the stricter way. The logs did not then say why.

Once they did, the answers turned out to be HTTP 429 with no wait named: no Retry-After header, and
no header saying that no requests were left or when they would come back.

- In five hourly status refreshes on 13 November 2026, 1 of 116 requests was answered that way: the
  first request of its run, from a token whose previous request had been nearly an hour before.
- In the daily fetch of 14 November 2026, 4 of 27 tariffs requests were, and none of 37 locations
  requests. One came while requests went close together, and three after the fall back, when
  requests went one at a time.
- Each request was answered when sent again, about two minutes later.

Every token was within its own published limits each time, and spacing the requests out did not
stop the refusals. Why the platform answers this way is unknown; only Eco-Movement can say. Each
case is a dated finding in its network's record on the [transparency page](transparency/).

On 15 November 2026 the owner decided that an HTTP 429 naming no wait slows only the token that
got it. That token goes back to its 125 second gap for the rest of the run, and the others keep
their allowance. Anything else, such as a 429 that names a wait, a server error or a refused
connection, still puts every network back to one request at a time.

The daily fetch of 16 November 2026 had no refusal at all: 60 requests to the platform in 1 minute
17 seconds, and 17 minutes 24 seconds for the whole fetch. In seven hourly refreshes from 21:30 UTC
on 15 November 2026, eight requests were refused this way in four of the runs, all within the first
19 seconds, and each slowed only its own token. In the daily fetch of 21 November 2026, bp pulse's
tariffs request was refused once and ESB ecars' twice, and both networks were read in full.

## Monta: one page timed out for a day

From 08:30 UTC on 13 November 2026, Monta's server answered HTTP 504, a gateway time-out, for a page
near the end of its list of locations, after 48 pages that answered. Each time it asked for a wait
of 120 seconds, and it answered the same way on all four tries. It was not always the same page.
The hourly refreshes kept the statuses last read, and the daily fetch of 14 November 2026 stopped
there, so the map kept Monta's copy of 13 November. Monta's API changelog, read on 13 November 2026,
named no recent change.

On 14 November 2026 the owner decided that the daily fetch handles an HTTP 504 as it already
handles the HTTP 500 described in [the post on Monta's feed](findings/monta-feed-and-prices/): it
asks for that page in smaller pieces, waits as long as asked, and skips only a site that still
fails, marking the run incomplete. The waits in one run are capped at 80 minutes.

It has not been needed so far. The daily fetch of 15 November 2026 read Monta's whole list, 50
requests with no 504, and every daily fetch since has too, up to 21 November 2026, when 747 Monta
locations were on the map.

## Roam: a long wait, then HTTP 502

Roam's locations address states a limit of five requests an hour, and the map keeps 721 seconds
between requests to it (see [the post on three requests
answered](findings/three-requests-answered/)). In the daily fetch of 13 November 2026 the locations
request was answered, but the server then asked for a further wait of about 20 minutes before the
next request. The fetch waits at most 10 minutes for one request, so it stopped before asking for
the tariffs, and the map kept Roam's copy of 12 November. The hourly refresh, new that day, had
asked the locations address once at about 03:31 UTC. Two requests in that hour are within the
stated limit, so why the server asked for the wait is not known. The next day's fetch read Roam
normally.

Since the morning of 16 November 2026 the locations address has answered HTTP 502, a bad gateway,
on all four tries in every daily fetch. The map shows Roam's 442 locations as fetched at 04:17 UTC
on 16 November 2026, and the feed health page says that it is a kept copy and how old it is. The
map keeps a copy for at most seven days, so unless the address answers again, Roam's chargers
should leave the map with the daily run of 23 November 2026.
