import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import relay, { DISPATCH_BODY, DISPATCH_URL, ROUTES, sameToken, startDailyFetch } from "../../relay/worker.js";

const TOKEN = "test-token-not-a-real-one";
const env = { RELAY_TOKEN: TOKEN };
const realFetch = globalThis.fetch;
let calls = [];

function upstream(status = 200, headers = {}) {
  calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    return new Response('{"data":[]}', { status, headers: { "content-type": "application/json", ...headers } });
  };
}

function ask(path, { token = TOKEN, method = "GET", headers = {} } = {}) {
  return relay.fetch(
    new Request(`https://relay.example.workers.dev${path}`, {
      method,
      headers: { ...(token ? { "x-relay-token": token } : {}), "user-agent": "OEVM/0.1 (+https://github.com/MCRDavid/OEVM)", ...headers },
    }),
    env,
  );
}

afterEach(() => {
  globalThis.fetch = realFetch;
});

test("only the listed GeniePoint files are relayed", () => {
  assert.deepEqual(Object.values(ROUTES), [
    "https://opendata.geniepoint.co.uk/locations",
    "https://opendata.geniepoint.co.uk/tariffs",
  ]);
});

test("a request without the right token is refused and nothing is fetched", async () => {
  upstream();
  for (const token of [null, "wrong", `${TOKEN}x`, TOKEN.slice(0, -1)]) {
    const response = await ask("/geniepoint/locations", { token });
    assert.equal(response.status, 401);
  }
  assert.equal(calls.length, 0);
  assert.equal((await relay.fetch(new Request("https://r.example/geniepoint/locations", { headers: { "x-relay-token": "" } }), { RELAY_TOKEN: "" })).status, 401);
});

test("other paths and methods are refused, so it is not an open proxy", async () => {
  upstream();
  for (const path of ["/", "/geniepoint", "/geniepoint/locations/x", "/https://example.org/", "/geniepoint/../chargy"]) {
    assert.equal((await ask(path)).status, 404, path);
  }
  assert.equal((await ask("/geniepoint/locations", { method: "POST" })).status, 405);
  assert.equal(calls.length, 0);
});

test("the feed is fetched with the project's User-Agent and its paging parameters", async () => {
  upstream(200, { "x-total-count": "306", "x-limit": "0", "set-cookie": "a=b", server: "IIS" });
  const response = await ask("/geniepoint/tariffs?offset=0&limit=50", { headers: { cookie: "c=d", authorization: "x" } });
  assert.equal(response.status, 200);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].url, "https://opendata.geniepoint.co.uk/tariffs?offset=0&limit=50");
  assert.deepEqual(calls[0].init.headers, {
    "user-agent": "OEVM/0.1 (+https://github.com/MCRDavid/OEVM)",
    accept: "application/json",
  });
  assert.equal(response.headers.get("x-total-count"), "306");
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(response.headers.get("set-cookie"), null);
  assert.equal(response.headers.get("server"), null);
  assert.equal(await response.text(), '{"data":[]}');
});

test("the operator's answer is passed back as it came, refusals included", async () => {
  upstream(403);
  assert.equal((await ask("/geniepoint/locations")).status, 403);
  upstream(429, { "retry-after": "3600" });
  const busy = await ask("/geniepoint/locations");
  assert.equal(busy.status, 429);
  assert.equal(busy.headers.get("retry-after"), "3600", "the operator's wait reaches the daily run");
  globalThis.fetch = async () => {
    throw new TypeError("network down");
  };
  assert.equal((await ask("/geniepoint/locations")).status, 502);
});

test("token comparison", () => {
  assert.equal(sameToken(TOKEN, TOKEN), true);
  assert.equal(sameToken("", ""), false);
  assert.equal(sameToken(undefined, TOKEN), false);
  assert.equal(sameToken(TOKEN, undefined), false);
});

// The timer that starts Fetch daily (ADR 0024).

const GITHUB = "test-github-token-not-real";

function github(...statuses) {
  calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    const status = statuses.length > 1 ? statuses.shift() : statuses[0];
    if (status === "unreachable") throw new TypeError("network down");
    return new Response(null, { status });
  };
}

const noWait = { sleep: async () => {} };

test("the timer asks GitHub to start Fetch daily on main, marked as started by the timer", async () => {
  github(204);
  assert.equal(await startDailyFetch({ GITHUB_DISPATCH_TOKEN: GITHUB }, noWait), 1);
  assert.equal(calls.length, 1);
  const { url, init } = calls[0];
  assert.equal(url, "https://api.github.com/repos/MCRDavid/OEVM/actions/workflows/fetch-daily.yml/dispatches");
  assert.equal(init.method, "POST");
  assert.equal(init.headers.authorization, `Bearer ${GITHUB}`);
  assert.equal(init.headers["x-github-api-version"], "2022-11-28");
  assert.match(init.headers["user-agent"], /^OEVM /);
  assert.deepEqual(JSON.parse(init.body), { ref: "main", inputs: { started_by: "timer" } });
  assert.deepEqual(DISPATCH_BODY, { ref: "main", inputs: { started_by: "timer" } });
  assert.match(DISPATCH_URL, /^https:\/\/api\.github\.com\/repos\//);
});

test("an answer with the new run's details also counts as started", async () => {
  github(200);
  assert.equal(await startDailyFetch({ GITHUB_DISPATCH_TOKEN: GITHUB }, noWait), 1);
});

test("without its token the timer asks nothing and says why", async () => {
  github(204);
  for (const env of [{}, { GITHUB_DISPATCH_TOKEN: "" }]) {
    await assert.rejects(startDailyFetch(env, noWait), /GITHUB_DISPATCH_TOKEN is not set/);
  }
  assert.equal(calls.length, 0);
});

test("a busy or unreachable GitHub is tried three times, a minute apart", async () => {
  const waits = [];
  const sleep = async (ms) => waits.push(ms);
  github(503, "unreachable", 204);
  assert.equal(await startDailyFetch({ GITHUB_DISPATCH_TOKEN: GITHUB }, { sleep }), 3);
  assert.deepEqual(waits, [60_000, 60_000]);

  github(502);
  await assert.rejects(startDailyFetch({ GITHUB_DISPATCH_TOKEN: GITHUB }, noWait), /HTTP 502/);
  assert.equal(calls.length, 3);
});

test("a refusal is not retried, and the message never includes the token", async () => {
  github(401);
  const error = await startDailyFetch({ GITHUB_DISPATCH_TOKEN: GITHUB }, noWait).catch((e) => e);
  assert.match(error.message, /HTTP 401/);
  assert.ok(!error.message.includes(GITHUB));
  assert.equal(calls.length, 1);
});

test("the scheduled event starts Fetch daily, and a failure fails the invocation", async () => {
  github(204);
  await relay.scheduled({ cron: "17 4 * * *", scheduledTime: Date.now() }, { GITHUB_DISPATCH_TOKEN: GITHUB });
  assert.equal(calls.length, 1);
  await assert.rejects(relay.scheduled({ cron: "17 4 * * *" }, {}), /not set/);
});

test("the timer's token does not open the relay", async () => {
  upstream();
  const response = await relay.fetch(
    new Request("https://relay.example.workers.dev/geniepoint/locations", { headers: { "x-relay-token": GITHUB } }),
    { RELAY_TOKEN: TOKEN, GITHUB_DISPATCH_TOKEN: GITHUB },
  );
  assert.equal(response.status, 401);
  assert.equal(calls.length, 0);
});
