import assert from "node:assert/strict";
import { afterEach, beforeEach, test } from "node:test";

import live, { CACHE_SECONDS, MAX_SNAPSHOT_BYTES, OPERATORS, checkSnapshot } from "../../proxy/worker.js";

const TOKEN = "test-token-not-a-real-one";
const SITE = "https://mcrdavid.github.io";
const KEY = "1111111111111111";
const realFetch = globalThis.fetch;

// Workers KV, kept in memory.
function memoryKv() {
  const store = new Map();
  return {
    store,
    async get(name) {
      return store.get(name)?.value ?? null;
    },
    async getWithMetadata(name) {
      const entry = store.get(name);
      return entry ? { value: entry.value, metadata: entry.metadata } : { value: null, metadata: null };
    },
    async put(name, value, options = {}) {
      store.set(name, { value, metadata: options.metadata ?? null });
    },
  };
}

function snapshot(fetchedAt = "2026-10-09T07:00:00Z", status = "available") {
  return {
    schema_version: 1,
    operator: "chargy",
    fetched_at: fetchedAt,
    full_fetch_at: "2026-10-09T04:17:00Z",
    locations: { [KEY]: [{ uid: "evse-1", status, status_at: "2026-10-09T06:58:00Z" }] },
  };
}

let env;
beforeEach(() => {
  env = { LIVE_TOKEN: TOKEN, SITE_ORIGIN: SITE, SNAPSHOTS: memoryKv() };
  globalThis.fetch = async () => {
    throw new Error("the live Worker must never fetch anything");
  };
});

afterEach(() => {
  globalThis.fetch = realFetch;
});

function ask(path, { method = "GET", token, origin, body } = {}) {
  const headers = {};
  if (token) headers["x-live-token"] = token;
  if (origin) headers.origin = origin;
  if (body !== undefined) headers["content-length"] = String(new TextEncoder().encode(body).length);
  return live.fetch(new Request(`https://live.example.workers.dev${path}`, { method, headers, body }), env);
}

function put(body, operator = "chargy") {
  return ask(`/snapshot/${operator}`, { method: "PUT", token: TOKEN, body: JSON.stringify(body) });
}

test("only operators switched on for the daily run are listed", () => {
  assert.deepEqual(OPERATORS, ["chargy", "geniepoint", "jolt"]);
});

test("a stored snapshot answers for one location, with when it was fetched", async () => {
  assert.equal((await put(snapshot())).status, 204);
  const response = await ask(`/live/chargy/${KEY}`, { origin: SITE });
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("access-control-allow-origin"), SITE);
  assert.equal(response.headers.get("cache-control"), `public, max-age=${CACHE_SECONDS}`);
  assert.deepEqual(await response.json(), {
    operator: "chargy",
    location_key: KEY,
    fetched_at: "2026-10-09T07:00:00Z",
    source: "snapshot",
    evses: [{ uid: "evse-1", status: "available", status_at: "2026-10-09T06:58:00Z" }],
  });
});

test("a newer snapshot replaces the one kept in memory", async () => {
  await put(snapshot());
  await ask(`/live/chargy/${KEY}`);
  await put(snapshot("2026-10-09T08:00:00Z", "charging"));
  const body = await (await ask(`/live/chargy/${KEY}`)).json();
  assert.equal(body.fetched_at, "2026-10-09T08:00:00Z");
  assert.equal(body.evses[0].status, "charging");
});

test("other pages' addresses get no CORS header", async () => {
  await put(snapshot());
  const response = await ask(`/live/chargy/${KEY}`, { origin: "https://example.org" });
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("access-control-allow-origin"), null);
});

test("unknown operators, keys and locations are not found", async () => {
  await put(snapshot());
  assert.equal((await ask(`/live/instavolt/${KEY}`)).status, 404);
  assert.equal((await ask("/live/chargy/not-a-key")).status, 404);
  assert.equal((await ask("/live/chargy/0000000000000000")).status, 404);
  assert.equal((await ask(`/live/jolt/${KEY}`)).status, 404); // no snapshot yet
  assert.equal((await ask("/")).status, 404);
});

test("/live/ answers GET only", async () => {
  assert.equal((await ask(`/live/chargy/${KEY}`, { method: "POST", body: "{}" })).status, 405);
});

test("snapshots cannot be stored or read without the token", async () => {
  const body = JSON.stringify(snapshot());
  assert.equal((await ask("/snapshot/chargy", { method: "PUT", body })).status, 401);
  assert.equal((await ask("/snapshot/chargy", { method: "PUT", token: "wrong", body })).status, 401);
  assert.equal((await ask("/snapshot/chargy")).status, 401);
  assert.equal(env.SNAPSHOTS.store.size, 0);
});

test("the stored snapshot can be read back with the token, uncached", async () => {
  await put(snapshot());
  const response = await ask("/snapshot/chargy", { token: TOKEN });
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.deepEqual(await response.json(), snapshot());
});

test("a snapshot for another operator, or not a snapshot, is refused", async () => {
  assert.equal((await put(snapshot(), "jolt")).status, 400);
  assert.equal((await put({ ...snapshot(), schema_version: 2 })).status, 400);
  assert.equal((await ask("/snapshot/chargy", { method: "PUT", token: TOKEN, body: "not json" })).status, 400);
  assert.equal(env.SNAPSHOTS.store.size, 0);
});

test("a snapshot over the size limit is refused before it is read", async () => {
  const response = await live.fetch(
    new Request("https://live.example.workers.dev/snapshot/chargy", {
      method: "PUT",
      headers: { "x-live-token": TOKEN, "content-length": String(MAX_SNAPSHOT_BYTES + 1) },
      body: "{}",
    }),
    env,
  );
  assert.equal(response.status, 413);
});

test("checkSnapshot names what is wrong", () => {
  assert.equal(checkSnapshot(snapshot(), "chargy"), null);
  assert.equal(checkSnapshot(null, "chargy"), "not a JSON object");
  assert.equal(checkSnapshot({ ...snapshot(), fetched_at: "soon" }, "chargy"), "fetched_at is not a date");
  assert.equal(checkSnapshot({ ...snapshot(), locations: null }, "chargy"), "no locations");
});
