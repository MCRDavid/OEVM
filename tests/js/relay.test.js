import assert from "node:assert/strict";
import { afterEach, test } from "node:test";

import relay, { ROUTES, sameToken } from "../../relay/worker.js";

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
