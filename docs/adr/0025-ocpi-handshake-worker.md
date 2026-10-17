# 0025: OCPI handshake Worker

Date: 2026-10-16. Status: proposed.

Tesla offers its UK charger data through an OCPI 2.2.1 connection on its developer portal,
which is "currently available on a pilot and invitation basis only"
(https://developer.tesla.com/en_GB/docs/charging/roaming, read 13 October 2026). Its
signed-in connection form, read by the repository owner on 13 October 2026 and not
submitted, asks the requester for a connection scope (US or UK), an authentication token, a
role, a party ID and a "URL to OCPI Versions endpoint" (`operators/tesla.yaml`).

That makes this project the credentials Receiver in OCPI 2.2.1 terms. It creates the first
token (CREDENTIALS_TOKEN_A, "TOKEN_A" below) and gives it to Tesla with its versions address.
Tesla reads the project's versions and version details with it, then POSTs its own token
(TOKEN_B) and versions address. "The Receiver stores `CREDENTIALS_TOKEN_B` and uses it for
any requests to the Sender Platform, including the version information and details", reads
Tesla's endpoints while the POST is still open, and answers with a new token, TOKEN_C
(OCPI 2.2.1 `credentials.asciidoc`, https://github.com/ocpi/ocpi/tree/release-2.2.1-bugfixes,
read 16 and 17 October 2026). Tesla may later PUT new credentials or DELETE the connection.

GitHub Pages cannot answer POST, PUT or DELETE, and the relay (ADR 0010) answers only GET, on
fixed routes, behind its own token. So connecting needs a small service that this project
runs. The owner asked where and how to host one while keeping to the brief's zero or minimal
cost. Hosts were compared on their own pages on 15 and 16 October 2026, and each claim was
checked a second time by a separate reviewer. The design was then reviewed twice more, for
OCPI conformance and for security, on 17 October 2026.

## Decisions

- **A separate Worker does only the handshake.** `ocpi/worker.js`, deployed as `oevm-ocpi` on
  the owner's existing free Cloudflare account, answers `GET` and `HEAD` on `/ocpi/versions`
  (version 2.2.1 only) and `/ocpi/2.2.1` (the credentials endpoint only), `GET`, `POST`, `PUT`
  and `DELETE` on `/ocpi/2.2.1/credentials`, and `GET /oevm/connection` for the daily run.
  Every other path answers 404, and one trailing slash is ignored. It never fetches Tesla's
  locations, tariffs or statuses, and the only addresses it calls are the versions and version
  details addresses it is given in a handshake.
- **Deployed from the repository, like the relay.** Its own Cloudflare Git integration builds
  `ocpi/` from `main` (root directory `ocpi`, build watch path `ocpi/*`, preview builds off).
  `ocpi/wrangler.toml` sets `workers_dev = true`, `preview_urls = false`, observability off and
  the `enable_request_signal` compatibility flag, creates the Durable Object class with a
  `[[migrations]]` entry (Cloudflare's newer `exports` table needs a recent Wrangler and cannot
  be undone), and has no Cron Trigger, no KV namespace, no plain variable, no route and no
  custom domain.
- **Not a route on the relay.** ADR 0010 keeps the relay for feeds that need no key, and the
  registry refuses a relay on an operator with a key; both stay as they are. A separate Worker
  keeps keyed and keyless traffic apart, keeps the relay's `GITHUB_DISPATCH_TOKEN` (ADR 0024)
  and Tesla's tokens in different Workers' secrets, and lets either be changed, stopped or
  disconnected without touching the other. The relay is also GET only behind `X-Relay-Token`,
  while the handshake needs POST, PUT and DELETE with OCPI's own `Authorization` header. The
  cost is a second setup in Cloudflare.
- **One Durable Object holds the connection.** One SQLite-backed Durable Object keeps all of
  the Worker's state as one record under one key: TOKEN_B and the form Tesla accepts it in,
  Tesla's versions, details, credentials, locations and tariffs addresses, the hash of TOKEN_C,
  the hashes of the last ten setup tokens used, whether a handshake is in progress, and what the
  owner needs to see (below). Every change is one write, made with the synchronous storage API
  with no wait between reading and writing: "SQLite storage operations are synchronous and do
  not yield the event loop, so they execute atomically without it"
  (https://developers.cloudflare.com/durable-objects/api/state/, read 16 October 2026). "Each
  Durable Object has its own durable, transactional, and strongly consistent storage"
  (https://developers.cloudflare.com/durable-objects/concepts/what-are-durable-objects/) and
  "All Durable Object data, including metadata, is encrypted at rest"
  (https://developers.cloudflare.com/durable-objects/reference/data-security/), both read 15
  and 16 October 2026. Workers KV is not used: "Changes may take up to 60 seconds or more to be
  visible in other global network locations"
  (https://developers.cloudflare.com/kv/concepts/how-kv-works/), so a new token could be
  refused, or a replaced one accepted, for a minute or more.
- **The Worker recognises the caller's token before reading anything else.** A request body is
  read only once its token has been recognised, and never more than 16 KB of it; Tesla's
  answers are read the same way, up to 64 KB. Cloudflare allows request bodies of 100 MB on the
  free plan and 128 MB of memory per isolate
  (https://developers.cloudflare.com/workers/platform/limits/, read 17 October 2026), so
  reading whole bodies would let one large request stop the only object.
- **TOKEN_A** is made by the owner in a password manager (40 to 64 letters and digits; OCPI
  allows at most 64 printable characters, and the Worker treats a secret shorter than 32
  characters, longer than 64 or with a space as unset), kept as the Worker secret
  `OCPI_TOKEN_A` and pasted only into Tesla's form. It is accepted only on the versions,
  version details and credentials routes. Once a POST with it succeeds ("The
  `CREDENTIALS_TOKEN_A` can then be thrown away, it MAY no longer be used"), the Worker keeps
  its hash and refuses it from then on, even if the secret is still set, with one exception
  (D7): for 10 minutes after the first registration made with it, and only until Tesla first
  uses TOKEN_C, the same TOKEN_A may register again, replacing the connection, in case Tesla
  never received the answer. The exception works from the stored hash, so deleting the secret
  does not end it, and a retry keeps the first deadline, so retrying never makes it longer.
  After that a POST with it answers HTTP 405 while the connection stands, and any other
  request 401. The refusal depends on the stored record, so the owner deletes the secret as
  soon as Tesla has connected. Setting a different `OCPI_TOKEN_A` and submitting Tesla's form
  again starts a new registration that replaces the old one (D6).
- **TOKEN_B** arrives in Tesla's POST or PUT and is kept only in the Durable Object. It may be
  up to 255 printable characters; anything longer than OCPI's 64 is noted for the owner.
- **TOKEN_C** is made in the object from 32 random bytes (`crypto.getRandomValues`), returned
  once to Tesla and stored only as its SHA-256 hash. A GET of credentials returns the token
  Tesla presented. Every successful PUT makes a new one. The previous one keeps working for 10
  minutes, or until the new one is first used, in case Tesla never received the answer; OCPI
  does not say when it must stop.
- **The pull token** is the Worker secret `OCPI_PULL_TOKEN`, sent in an `X-Pull-Token` header,
  with a matching GitHub Actions secret added by the pipeline change. It can read TOKEN_B, so
  it is treated like a key: the same length rules as TOKEN_A apply, it is compared by hash,
  and a wrong one gets HTTP 403. Nothing goes in the repository, and this Worker holds no
  GitHub token.
- **The handshake keeps to OCPI 2.2.1.** A POST with TOKEN_C answers HTTP 405 ("This method
  MUST return a `HTTP status code 405: method not allowed` if the client has already been
  registered before"), and so do a PUT or DELETE with a setup token ("... if the client has not
  been registered yet" for PUT, "... if the client has not been registered before" for
  DELETE), each with an `Allow` header. Unknown tokens get HTTP 401 with `WWW-Authenticate:
  Token`, and so does a request with no usable `Authorization` header, before any 405. The
  one exception: a method other than GET or HEAD on versions or details answers 405 without
  the object being asked whether a token in a usable form is known, so such stray requests
  use no Durable Object requests. A body that is not JSON gets HTTP 400; one over 16 KB, or a
  Credentials object the Worker cannot use, gets OCPI status 2001. Every OCPI answer uses the
  OCPI response envelope and returns the caller's `X-Request-ID` and `X-Correlation-ID` (or
  new ones if it sent none). The `Authorization: Token` header is accepted Base64 encoded
  (padded or not, standard or URL-safe), as OCPI 2.2.1 asks, or plain, as its own note says
  many implementations send it. Tokens are compared in constant time, by comparing their
  SHA-256 hashes with the same function as the relay. If the Worker cannot use
  Tesla's API the POST answers OCPI status 3001; if Tesla does not offer version 2.2.1, 3002;
  and if its details lack a locations endpoint, 3003. A missing tariffs or credentials
  endpoint is noted for the owner but does not stop the connection (D3), because role NSP is
  "probably only interested in Location information" (OCPI 2.2.1 `types.asciidoc`). A failed
  handshake changes nothing, so Tesla can try again. Any other error answers OCPI status 3000,
  with HTTP 200 once the caller's token is known, because OCPI says that to such a request "an
  HTTP error status code MUST NOT be returned". Cloudflare passes "Any uncaught exceptions
  thrown by a Durable Object or thrown by Durable Objects' infrastructure (such as overloads or
  network errors)" back to the Worker that called it
  (https://developers.cloudflare.com/durable-objects/best-practices/error-handling/, read 17
  October 2026). So if the object cannot answer, the front handler answers OCPI status 3000
  with HTTP 500 and the caller's ids (only the object can recognise the token), and the
  handout answers a JSON HTTP 500. Nothing about the error is logged or returned.
- **Its own calls keep the project's rules.** The Worker's calls to Tesla (its versions, then
  its 2.2.1 details) send the project's User-Agent,
  `OEVM/0.1 (+https://github.com/MCRDavid/OEVM)`, go only to an https address on a named host
  with no port and no IP address (D4), never follow a redirect, give up after 10 seconds
  including reading the answer, and keep the 2 seconds between requests set in
  `operators/tesla.yaml`, measured from the end of the last answer, also across handshakes. On
  a registration they send TOKEN_B in the form Tesla used for the setup token; the first call
  Tesla refuses with HTTP 400, 401 or 403 is tried once more in the other form, which is then
  used (400 because a server that decodes the header strictly may answer it to a token that is
  not Base64). There is still only one switch, so a registration makes at most three calls.
  A renewal uses the stored form only. The form that works is kept and given to the daily run.
  Waiting uses no CPU time.
- **One handshake at a time, within a time budget.** Cloudflare warns that "Input gates only
  protect during storage operations. Non-storage I/O like `fetch()` or writing to R2 allows
  other requests to interleave"
  (https://developers.cloudflare.com/durable-objects/best-practices/rules-of-durable-objects/,
  read 16 October 2026). So the object stores a "handshake in progress" flag before its first
  call to Tesla. While it is set, another POST, PUT or DELETE gets OCPI status 3000 (with HTTP
  200), and the daily run's handout gets HTTP 409. Versions, version details and credentials
  are still answered, so a later handshake started by this project is not blocked by Tesla's
  calls back. A handshake starts no call and saves no registration after 25 seconds, or once
  Tesla has hung up where Cloudflare reports it, because Tesla might not receive the answer.
  The flag lapses after a minute, in case a deploy or restart stops a handshake part way, and
  an unexpected error clears it at once. A handshake that finds its flag gone stops without
  calling Tesla again or saving anything.
- **The owner can see what Tesla did.** Logs are off, so the record keeps, without any token or
  address: the result of the last handshake with a fixed message, the token forms tried and
  notes; when each route was last called, with which kind of token, in which form and whether
  request IDs were sent; and how often the daily run's handout gave out TOKEN_B. The handout
  returns them, and `docs/GITHUB_SETTINGS.md` shows the owner how to read them without printing
  TOKEN_B.
- **The daily run will fetch Tesla itself.** `GET /oevm/connection`, with the pull token,
  returns the current TOKEN_B, its form, Tesla's locations and tariffs addresses and the items
  above. It refuses while a handshake is in progress and says so when there is no connection. A
  later pull request will have the pipeline read it once per run inside the fetch step (keys
  reach that step only), keep TOKEN_B in memory, mask it and its Base64 form in the logs, and
  fetch Tesla directly from GitHub with the polite client, at least 2 seconds apart. It will use
  an address from the handout only if its host is the one recorded in `operators/tesla.yaml`
  ("Only use feed URLs with a known source; record the source in the operator file",
  `CLAUDE.md`), which the owner records after the first registration (D8).
- **An exception to ADR 0010: a second key holder.** ADR 0010 says "Only feeds that need no key
  may be relayed, so no key ever passes through a third party." That stays true of the relay.
  Here no key passes through on its way somewhere else: OCPI requires the Receiver to store the
  operator's token, so whatever runs the endpoint holds it. Cloudflare becomes a second place
  where an operator's key is kept, next to GitHub Actions secrets (which already hold
  `JOLT_API_KEY`), and the first that takes calls from an operator. Only the tokens of a
  handshake connection live there; other operators' keys stay in GitHub. The blueprint
  expected Workers to hold keys: "In Phase 3, the Worker reads them from **Cloudflare Worker
  secrets**" (`docs/BLUEPRINT.md`).
- **No operator's name in names.** Cloudflare's Developer Platform terms prohibit accounts or
  projects "using subdomains that include deceptive or offensive terms or names of other
  businesses" (https://www.cloudflare.com/service-specific-terms-developer-platform/, read 16
  October 2026). So "tesla" stays out of the Worker's name, the account subdomain, the routes
  and the Durable Object's names.
- **The project's credentials name only the project.** The Worker's reply gives role NSP,
  country GB, the party ID in `ocpi/worker.js` (typed into Tesla's form unchanged, D2), the
  name OEVM and the site's address, and no logo. Never the owner's name or any other personal
  detail.
- **Tesla's data stays switched off.** `operators/tesla.yaml` keeps `enabled: false`. No
  adapter, fixture or `DATA_LICENCES.md` row is added until Tesla's terms, licence and rate
  limits have been read and its licence section filled in, as for every operator. Holding a
  token switches nothing on.

## Why

- **It costs nothing.** Workers Free: "a daily request limit of 100,000 requests, resetting at
  midnight UTC"; 10 ms of CPU per request, and "Waiting on network requests (such as `fetch()`
  calls, KV reads, or database queries) does **not** count toward CPU time"; 50 subrequests per
  invocation (a handshake makes at most 3 calls to Tesla); "There is no hard limit on duration
  for HTTP-triggered Workers. As long as the client remains connected, the Worker can continue
  processing"; 100 Workers per account
  (https://developers.cloudflare.com/workers/platform/limits/, read 15 October 2026). "Workers
  Free plan: Only Durable Objects with SQLite storage backend are available", with 100,000
  requests and 100,000 rows written a day and 5 GB of storage
  (https://developers.cloudflare.com/durable-objects/platform/pricing/). No card is needed
  (https://www.cloudflare.com/plans/). A connection is a few requests and writes a day and a
  few kilobytes.
- **It uses what the project already has.** The account, the GitHub app and deploying from
  `main` already exist for the relay (ADR 0010).
- **The Worker does not write GitHub secrets.** That would need a GitHub token with "Secrets"
  write permission, which GitHub grants for every secret in the repository (so it could also
  overwrite `JOLT_API_KEY` and the relay's), and a sealed box library that WebCrypto lacks.
  GitHub secrets cannot be read back either, so it would gain nothing.
- **It settles a question from ADR 0015:** Durable Objects are on the free plan.

## Risks accepted

- **One shared daily allowance.** The 100,000 requests a day are per account. Anyone can call a
  public workers.dev address, and if the allowance ran out, Cloudflare would return Error 1027
  to the relay, the timer and Tesla's calls alike until midnight UTC. There is no billing risk,
  only an outage. The Worker refuses requests without a usable token before they reach the
  Durable Object, but a refused request still counts. A separate free account would keep this
  Worker apart (not done).
- **The address can change.** "Cloudflare may change Cloudflare Workers/Pages subdomain names of
  projects hosted at workers.dev or pages.dev for any or no reason. Cloudflare will attempt to
  provide you with at least one week prior notice for such change" (Developer Platform terms,
  above). Tesla would then hold an old versions address. The fix is a credentials PUT from this
  project to Tesla with the new address (see "Not done"). Cloudflare recommends "a Workers
  route or custom domain" for production Workers
  (https://developers.cloudflare.com/workers/configuration/routing/workers-dev/), and custom
  domains are not renamed, but a domain costs money (price not checked).
- **Free services can end.** Cloudflare's free services last until, among other things,
  "termination of the Free Service by Cloudflare in our sole discretion" (Self-Serve
  Subscription Agreement, https://www.cloudflare.com/terms/). The connection would then stop
  until it is moved and Tesla's form is filled in again.
- **No fixed outbound address.** On the free plan a Worker has no address of its own that Tesla
  could allow, and every `fetch()` carries a `CF-Worker` header. The daily pull comes from
  GitHub's runners, which char.gy and GeniePoint refused on 8 October 2026. Whether Tesla
  refuses either network needs testing.
- **Tesla's calls cannot be timed (proposed, D1).** Tesla chooses when to PUT, or to register
  again (D6, D7). The in-progress flag stops a daily pull starting during a handshake, but
  nothing stops Tesla starting one while a pull is running. The Worker's calls back, 2 seconds
  apart, could then reach Tesla while the run is also fetching, closer together than Tesla's
  gap. That would depart from the rules never to go below an operator's gap and never to run
  two fetches to one host at once, for at most three requests (two for a renewal), each
  answering Tesla's own call. This ADR proposes accepting it because the alternatives are
  worse: a lock taken by the daily run would either refuse Tesla's renewal, which might be
  answering a suspected leak, or hold Tesla's PUT open for an unknown time, which could leave
  Tesla without the new TOKEN_C. The same PUT may also replace the TOKEN_B the run holds, so
  that day's Tesla fetch could fail and the next run would use the new token (needs testing).
- **Whoever holds a token chooses the addresses.** Before registration anyone holding TOKEN_A,
  and afterwards anyone holding TOKEN_C, can give the Worker any https address on a named host
  (D4). The Worker would then call it with that party's token and the project's User-Agent, up
  to three times, and might so reach another operator's host outside that operator's own gap.
  And the handout would give the daily run the addresses that party chose. The daily run's host
  check (D8) stops the second; pinning the Worker's own calls to the recorded host is a
  follow-up once Tesla's host is known.
- **Deploy access is the real control.** Anyone who can merge a change to `ocpi/` on `main`, or
  edit the Worker in Cloudflare's dashboard, can deploy code that reads TOKEN_B. Branch
  protection with pull requests and passing checks (`docs/GITHUB_SETTINGS.md`, section 6), a
  careful review of every change to `ocpi/`, and two-factor sign-in on the GitHub and
  Cloudflare accounts are what protect it. Keeping the Worker's address in a GitHub secret
  only cuts stray traffic; the address may be discoverable (needs checking), so it is not a
  protection. The handout count shows reads of TOKEN_B that the daily run did not make.
  Another Worker on the same Cloudflare account could bind to the Durable Object (with
  `script_name = "oevm-ocpi"`) and call its public methods over RPC, so `fetch` is the only
  one: every other member is a JavaScript private method ("Private properties of classes are
  not directly exposed over RPC", https://developers.cloudflare.com/workers/runtime-apis/rpc/,
  read 17 October 2026). `fetch` itself checks the caller's token, and the pull token for the
  handout, so a call through such a binding gets no more than a call to the public address,
  and a handout through it is counted like any other. Tests check that `fetch` is the only
  public method.
- **Removed, not erased.** SQLite-backed Durable Objects can be restored "to any point in time in
  the past 30 days" (https://developers.cloudflare.com/durable-objects/api/sqlite-storage-api/),
  so a DELETE takes TOKEN_B out of use, but Cloudflare keeps it recoverable for 30 days. A
  restore would also bring back the record from before a setup token was used, which is why the
  owner deletes `OCPI_TOKEN_A` once Tesla has connected.

## Alternatives considered

- **A route on the relay, the Worker writing GitHub secrets, Workers KV:** rejected above.
- **A lock for the daily run** (taken when it reads TOKEN_B, released when it finishes), so
  that Tesla's PUT never overlaps a pull: not proposed (see D1). It is added in this pull
  request if D1 is answered no, and could be added later if Tesla publishes a limit that needs
  it.
- **Following a redirect on Tesla's own host:** not done, because each one is a further request
  to that host and Tesla's addresses are its own choice; a redirect fails the handshake with a
  message the owner can pass on.
- **The Worker fetching Tesla's data for the daily run** (a pass-through). Not chosen: it would
  contradict ADR 0010 and the registry's rule, so it would need its own decision. It is the
  fallback if Tesla refuses GitHub's network.
- **Other hosts**, read on their own pages on 15 and 16 October 2026. Vercel Hobby was next best
  (free, but a new vendor, its card rule not stated, and going over a Hobby limit can lock a
  feature for 30 days). Supabase Free pauses projects after a week of low activity. Netlify Free
  charges credits per production deploy, which this repository's merge rate would use up. The
  no-card AWS Free plan account closes after 6 months. Google Cloud Run needs a billing account.
  Render Free sleeps after 15 minutes and has no free token store. Oracle Always Free needs a
  card and a whole server. Fly.io has no free allowance. Deno Deploy is closing about six months
  after 9 October 2026. A computer at home is not always on, and its calls would reveal where it
  is.

## Decided by the owner (16 October 2026)

- After reading the hosting comparison of 15 and 16 October 2026, the repository owner chose
  "Build it": a separate free Cloudflare Worker for Tesla's handshake, with this ADR. That
  comparison planned role NSP ("Navigation Service Provider Role, role like an eMSP (probably
  only interested in Location information)", OCPI 2.2.1 `types.asciidoc`) and a three-letter
  party ID for Tesla's form, as `operators/tesla.yaml` already notes. Which three letters is
  D2 below.

## Proposed defaults awaiting the owner's confirmation

The code follows these defaults, but the repository owner has not confirmed them. The pull
request that adds `ocpi/` asks about each one, and this ADR stays proposed until all are
answered. D1 comes first because it relaxes a rule in `CLAUDE.md`.

- **D1. Overlap with the daily run.** `CLAUDE.md` says "Never run two fetches that use the same
  host in parallel", and never to go below an operator's gap. Proposed: for calls that Tesla
  itself starts, accept that a PUT or a new registration (D6, D7) arriving while a daily pull
  is running may overlap the pull, closer than Tesla's gap, by up to three requests (two for a
  renewal), each made in answer to Tesla's own credentials call ("Risks accepted" above).
  Nothing else may overlap. If not: a lock for the daily run is added in this pull request,
  which refuses Tesla's PUT while a pull runs.
- **D2. Party ID.** Proposed: `OEV`, from OEVM (`party_id` in `PARTY` in `ocpi/worker.js`),
  typed into Tesla's form unchanged. Whether `GB*OEV` is already in use needs checking. If
  not: change `party_id` there; the tests check only that it is three capital letters or
  digits and not Tesla's example `TES`.
- **D3. Only a locations endpoint is required.** Proposed: yes. Tariffs and credentials
  endpoints may be missing, and a missing one is noted for the owner. If not: a missing
  tariffs endpoint also answers OCPI status 3003.
- **D4. Any https address on a named host, for now.** Proposed: the Worker calls any https
  address on a named host with no port, user name, password or IP address, and pinning its
  calls to Tesla's recorded host follows once that host is known (D8). If not: pin now to a
  host Tesla tells the owner in advance.
- **D5. HTTP 200 for a registration.** Proposed: 200 (`REGISTERED_HTTP_STATUS` in
  `ocpi/worker.js`), as for every other successful answer. OCPI says a server SHOULD answer
  "HTTP `201 - Created` when the object has been newly created in the server system"
  (`status_codes.asciidoc`); whether Tesla accepts either needs testing. If not: set the
  constant to 201.
- **D6. A new setup token replaces a registration.** Proposed: yes. A POST with a different
  `OCPI_TOKEN_A` registers afresh and replaces the current connection. This is the recovery
  after a lost reply once D7's 10 minutes are over. If not: a new setup token works only when
  there is no connection, so that recovery needs a code change.
- **D7. The 10-minute retry for a used setup token.** Proposed: yes. For 10 minutes after the
  first registration made with a setup token, and only until Tesla first uses TOKEN_C, that
  setup token may register again, replacing the connection. A retry keeps the first deadline,
  and deleting the secret does not end the 10 minutes, because the Worker uses the stored
  hash. OCPI's text says TOKEN_A "MAY no longer be used", which permits this; its registration
  diagram says the setup token "has now become invalid", which does not. If not:
  `SETUP_RETRY_GRACE_MS` is set to 0, and a lost reply is then recovered only with a new setup
  token and the form (D6).
- **D8. Record Tesla's host.** Proposed: after the first registration, the owner records the
  host of Tesla's locations address (the host only, never the address) in
  `operators/tesla.yaml` with its date and source, and the daily run uses only addresses on
  that host. If Tesla objects to its host being published, the owner decides how the rule
  "Only use feed URLs with a known source" is met before Tesla is switched on.

## Needs testing

- Whether Tesla's form can be used without an invitation, and its rules for the token field
  (the Worker needs at least 32 characters).
- How long Tesla keeps its POST and PUT open while the Worker calls back (2 seconds plus two
  round trips are needed; the Worker stops at 25 seconds), whether Cloudflare tells the Worker
  when Tesla hangs up, and whether Tesla retries a registration whose answer it lost within 10
  minutes.
- Whether Tesla sends and expects Base64 tokens and request ID headers, accepts a peer whose
  version details list only credentials, accepts HTTP 200 for a registration (OCPI suggests
  201), accepts a workers.dev address and country GB, and checks that the role and party ID in
  the reply match its form. If the handout shows that Tesla read the version details and never
  posted, try giving the one credentials entry the role RECEIVER (OCPI 2.2.1's second version
  details example lists credentials once, with that role; the spec says the module "is not
  defined twice"). If a later change lists it twice anyway, record that as a departure from
  `version_information_endpoint.asciidoc`.
- Whether Tesla refuses calls from Cloudflare's or GitHub's networks, and whether its servers
  answer HTTP 403 to automated calls, as its website did on 10 October 2026.
- Whether Tesla's credentials address is on the same host as its locations and tariffs, and
  whether any of them uses a port, a redirect or an IP address.
- Who renews tokens, and how often. OCPI says "It is advisable to renew the credentials tokens
  at least once a month".
- Whether Tesla's host and endpoint addresses may be published in the public operator file.
- Tesla's terms, licence and rate limits: none are stated anywhere.
- Cloudflare's pages disagree on a Durable Object's CPU limit on the free plan (30 seconds or
  the Workers 10 ms); the handlers should stay well under 10 ms.
- Whether Cloudflare holds the first call to Tesla until a synchronous storage write is
  durable, as it does for asynchronous writes.
- Which Wrangler version Cloudflare's build uses, and whether it accepts the `[[migrations]]`
  entry and the compatibility flag without a warning (the first build log shows both).

## Not done

- **The pipeline side**, in its own pull request: an owner decision section in
  `schema/operator.py` for an operator reached this way, modelled on `relay` and naming two
  GitHub secrets (the Worker's address and the pull token) and the operator's recorded host;
  reading TOKEN_B once per run; the token's form; the Base64 form in the scrubber; request ID
  headers; the host check; noting handouts it did not make; workflow and test changes.
- **The adapter**, in its own pull request and only after Tesla's terms are read: real
  fixtures, Tesla's tariff extensions (`CONGESTION_TIME`, `min_vehicle_soc`,
  `min_congestion_threshold`), findings and a `DATA_LICENCES.md` row.
- **A credentials PUT or DELETE started by this project**, to renew tokens, give Tesla a new
  address after a rename, or act on a suspected leak. OCPI says a platform that suspects a
  leaked token "SHALL initiate a credentials token update as soon as possible". It needs a
  client for Tesla's credentials endpoint and an owner-started route or a third Cron Trigger.
  Until then, a leak is handled by asking Tesla to end the connection and starting again with
  a new TOKEN_A.
- Pinning the Worker's calls to Tesla's recorded host, a separate Cloudflare account, a custom
  domain, the pass-through fallback, and encrypting TOKEN_B with a key held as a Worker secret.

## Owner setup

`docs/GITHUB_SETTINGS.md`, section 11: create the Worker from the repository, set its two
secrets, check that it refuses requests without a token and answers with one, and only then
fill in Tesla's form and record the request.
