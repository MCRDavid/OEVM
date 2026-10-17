import assert from "node:assert/strict";
import * as nodeModule from "node:module";
import { afterEach, beforeEach, test } from "node:test";

// ocpi/worker.js imports "cloudflare:workers", which only the Workers runtime has. Node 22.15 or
// later can point that import at a stub for this file only (each test file runs in its own process).
assert.equal(typeof nodeModule.registerHooks, "function", "these tests need Node 22.15 or later");
const stub = new URL("./cloudflare-workers-stub.js", import.meta.url).href;
nodeModule.registerHooks({
  resolve: (specifier, context, next) =>
    specifier === "cloudflare:workers" ? { url: stub, shortCircuit: true } : next(specifier, context),
});
const worker = await import("../../ocpi/worker.js");
const {
  CALL_TIMEOUT_MS,
  CONTACT_EVERY_MS,
  GAP_MS,
  HANDSHAKE_BUDGET_MS,
  HANDSHAKE_EXPIRY_MS,
  MAX_BODY_BYTES,
  MAX_PEER_BODY_BYTES,
  OBJECT_NAME,
  OcpiConnection,
  PARTY,
  PATHS,
  PREVIOUS_TOKEN_GRACE_MS,
  REGISTERED_HTTP_STATUS,
  SETUP_RETRY_GRACE_MS,
  STORAGE_KEY,
  USER_AGENT,
  newToken,
  sameToken,
  sha256Hex,
  tokenForms,
} = worker;
const handler = worker.default;

// The Worker runs here against an in-memory stand-in for its Durable Object storage and a mock
// of the other party's server ("the peer"). No test contacts any host, and the clock is the
// test's own, so nothing waits for real except the 5 ms call timers in two tests.

const TOKEN_A = "test-token-a-for-setup-not-a-real-one";
const TOKEN_A2 = "test-token-a-second-setup-not-real-1";
const PULL = "test-pull-token-for-the-daily-run-not-real";
const TOKEN_B = "test-token-b-from-the-peer";
const TOKEN_B2 = "test-token-b-renewed-by-the-peer";
const WORKER = "https://ocpi.example.workers.dev";
const PEER = "https://peer.example";
const VERSIONS_URL = `${PEER}/ocpi/versions`;
const DETAILS_URL = `${PEER}/ocpi/2.2.1`;
const ENDPOINTS = {
  credentials: `${PEER}/ocpi/2.2.1/credentials`,
  locations: `${PEER}/ocpi/cpo/2.2.1/locations`,
  tariffs: `${PEER}/ocpi/cpo/2.2.1/tariffs`,
};

const BUSY = "A credentials handshake is already in progress; try again in a minute.";
const STOPPED = "The handshake took too long and was stopped; try again.";
const LATE = "Could not use the client's API: the handshake took too long, so nothing was changed.";
const TOO_LARGE = "The request body is too large.";
const NOT_JSON = "The request body is not valid JSON.";
const NOT_CREDENTIALS = "The request body must be a Credentials object.";
const TOKEN_MESSAGE = "token must be 1 to 255 printable characters with no spaces.";
const URL_MESSAGE =
  "url must be an https address on a named host, with no port, user name or password, of at most 255 characters.";
const USED = "Already registered: this setup token has been used. Use the token from the registration reply.";
const REGISTERED = "Already registered: use PUT to update the credentials or DELETE to end the connection.";
const ONLY_POST = "This token can only register: use POST.";
const NOT_HERE = "This method is not allowed here.";
const UNEXPECTED = "Unexpected server error.";
const LACK = "The client's 2.2.1 endpoints lack: locations (SENDER).";
const UNUSABLE = "The client's 2.2.1 endpoints give no address this Worker will use for: locations (SENDER).";
const api = (text) => `Could not use the client's API: ${text}.`;

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/;
const TIMESTAMP = /^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d(\.\d{1,3})?Z$/;
const NEW_TOKEN = /^[A-Za-z0-9_-]{43}$/;
const LOGGING = ["log", "info", "warn", "error", "debug"];
const iso = (ms) => new Date(ms).toISOString();

const realFetch = globalThis.fetch;
const realConsole = {};
let calls = [];
let current = null;

beforeEach(() => {
  calls = [];
  globalThis.fetch = async (url, init) => {
    calls.push({ url: String(url), init });
    throw new Error("no call to the peer was expected");
  };
  for (const name of LOGGING) {
    realConsole[name] = console[name];
    console[name] = () => {
      throw new Error("the Worker must not log");
    };
  }
});

afterEach(() => {
  globalThis.fetch = realFetch;
  for (const name of LOGGING) console[name] = realConsole[name];
});

// Synchronous, like ctx.storage.kv on a SQLite-backed Durable Object. failNext makes the next get
// throw, failNextPut the next put, and failAlways every get.
function memoryStorage() {
  const storage = {
    store: new Map(),
    failNext: false,
    failNextPut: false,
    failAlways: false,
    kv: {
      get(key) {
        if (storage.failAlways || storage.failNext) {
          storage.failNext = false;
          throw new Error("storage failed for the test");
        }
        return storage.store.get(key);
      },
      put(key, value) {
        if (storage.failNextPut) {
          storage.failNextPut = false;
          throw new Error("storage failed for the test");
        }
        storage.store.set(key, value);
      },
      delete(key) {
        return storage.store.delete(key);
      },
    },
  };
  return storage;
}

// A fresh Worker: its env, storage, the waits it asked for, the object names it used and its clock.
function setup({ env = {}, now = 1_000_000, answerMs = 700 } = {}) {
  const storage = memoryStorage();
  const waits = [];
  const names = [];
  const clock = { now };
  const ids = new Set();
  let object = null;
  const instance = () => {
    if (object === null) {
      object = new OcpiConnection({ storage }, fullEnv);
      object.sleep = async (ms) => {
        waits.push(ms);
        clock.now += ms;
      };
      object.now = () => clock.now;
    }
    return object;
  };
  const fullEnv = {
    OCPI_TOKEN_A: TOKEN_A,
    OCPI_PULL_TOKEN: PULL,
    CONNECTION: {
      idFromName(name) {
        names.push(name);
        const id = { name };
        ids.add(id);
        return id;
      },
      get(id) {
        assert.ok(ids.has(id), "get takes an id from idFromName");
        return { fetch: (request) => instance().fetch(request) };
      },
    },
    ...env,
  };
  current = { env: fullEnv, storage, waits, names, clock, answerMs, instance, answered: [] };
  return current;
}

const stored = () => current.storage.store.get(STORAGE_KEY);
const record = () => JSON.parse(stored());

// Changes the stored record as if an earlier request had left it so.
function rewrite(change) {
  current.storage.store.set(STORAGE_KEY, JSON.stringify({ ...record(), ...change }));
}

function ocpiAnswer(data, statusCode = 1000) {
  const body = { data, status_code: statusCode, status_message: "Success", timestamp: iso(0) };
  return new Response(JSON.stringify(body), { headers: { "content-type": "application/json" } });
}
const endpoint = (identifier, role, url) => ({ identifier, role, url });
const versionsAnswer = () =>
  ocpiAnswer([
    { version: "2.1.1", url: `${PEER}/ocpi/2.1.1` },
    { version: "2.2.1", url: DETAILS_URL },
  ]);
const ALL_ENDPOINTS = [
  endpoint("credentials", "SENDER", ENDPOINTS.credentials),
  endpoint("locations", "SENDER", ENDPOINTS.locations),
  endpoint("tariffs", "SENDER", ENDPOINTS.tariffs),
  endpoint("commands", "RECEIVER", `${PEER}/ocpi/emsp/2.2.1/commands`),
];
const detailsAnswer = (endpoints = ALL_ENDPOINTS) =>
  ocpiAnswer({ version: "2.2.1", endpoints, a_field_this_worker_does_not_know: true });

// The peer's server. Each answer moves the clock on by answerMs, so a gap measured from the start
// of a call instead of the end of its answer would show.
function peer(overrides = {}) {
  calls = [];
  const answers = { versions: versionsAnswer, details: () => detailsAnswer(), ...overrides };
  globalThis.fetch = async (url, init) => {
    const target = String(url);
    calls.push({ url: target, init, at: current.clock.now });
    const answer = await answers[target === DETAILS_URL ? "details" : "versions"](target, init);
    current.clock.now += current.answerMs;
    return answer;
  };
}
const authorization = (call) => call.init.headers.authorization;

function gate() {
  let open;
  const promise = new Promise((resolve) => {
    open = resolve;
  });
  return { promise, open };
}

// The peer, with its first versions answer held until the test opens the gate.
function gatedPeer(overrides = {}) {
  const held = gate();
  let first = true;
  peer({
    versions: async () => {
      if (first) {
        first = false;
        await held.promise;
      }
      return versionsAnswer();
    },
    ...overrides,
  });
  return held;
}

async function until(condition) {
  for (let i = 0; i < 1000 && !condition(); i += 1) await new Promise((resolve) => setTimeout(resolve, 1));
  assert.ok(condition(), "waited too long");
}

// A body that makes `chunks` chunks of 1 KB only when they are read, then ends.
function stream(chunks, onPull = () => {}) {
  let made = 0;
  return new ReadableStream(
    {
      pull(controller) {
        onPull();
        if (made === chunks) {
          controller.close();
          return;
        }
        made += 1;
        controller.enqueue(new Uint8Array(1024).fill(0x20));
      },
    },
    { highWaterMark: 0 },
  );
}

// An answer that starts and never ends.
function hanging() {
  return new ReadableStream({ pull: () => new Promise(() => {}) }, { highWaterMark: 0 });
}

// A request body that arrives only once the gate is open.
function gatedBody(held, text, onPull) {
  return new ReadableStream(
    {
      async pull(controller) {
        onPull();
        await held.promise;
        controller.enqueue(new TextEncoder().encode(text));
        controller.close();
      },
    },
    { highWaterMark: 0 },
  );
}

function credentialsBody({ token = TOKEN_B, url = VERSIONS_URL, ...rest } = {}) {
  return {
    token,
    url,
    roles: [{ role: "CPO", party_id: "ABC", country_code: "GB", business_details: { name: "Peer for the test" } }],
    ...rest,
  };
}

function request(path, options = {}) {
  const { method = "GET", token = TOKEN_A, form = "plain", body, headers = {}, signal, base = WORKER } = options;
  const init = { method, headers: {}, signal };
  if (token !== null) init.headers.authorization = `Token ${form === "base64" ? btoa(token) : token}`;
  if (options.ids !== false) {
    Object.assign(init.headers, { "x-request-id": "request-1", "x-correlation-id": "correlation-1" });
  }
  if (body !== undefined) {
    init.headers["content-type"] = "application/json";
    const raw = typeof body === "string" || body instanceof Uint8Array || body instanceof ReadableStream;
    init.body = raw ? body : JSON.stringify(body);
    if (body instanceof ReadableStream) init.duplex = "half";
  }
  Object.assign(init.headers, headers);
  return new Request(`${base}${path}`, init);
}

// Every answer in every test is checked for sharing headers and kept for the exposure tests.
async function send(incoming, label) {
  const response = await handler.fetch(incoming, current.env);
  for (const name of response.headers.keys()) {
    assert.ok(!name.startsWith("access-control-"), `${name} on ${label}`);
  }
  current.answered.push({ label, response: response.clone() });
  return response;
}
const ask = (path, options = {}) => send(request(path, options), `${options.method ?? "GET"} ${path}`);
const post = (options = {}) => ask(PATHS.credentials, { method: "POST", body: credentialsBody(), ...options });
const put = (token, options = {}) =>
  ask(PATHS.credentials, { method: "PUT", token, body: credentialsBody({ token: TOKEN_B2 }), ...options });

function handOut({ token = PULL, method = "GET", path = PATHS.connection } = {}) {
  const headers = token === null ? {} : { "x-pull-token": token };
  return send(new Request(`${WORKER}${path}`, { method, headers }), `${method} ${path}`);
}

async function read(response) {
  const text = await response.text();
  return text === "" ? null : JSON.parse(text);
}

function expectedCredentials(token, origin = WORKER) {
  return {
    token,
    url: `${origin}/ocpi/versions`,
    roles: [
      {
        role: "NSP",
        party_id: PARTY.party_id,
        country_code: "GB",
        business_details: { name: "OEVM", website: "https://mcrdavid.github.io/OEVM/" },
      },
    ],
  };
}

async function register({ form = "plain", token = TOKEN_A, body = credentialsBody() } = {}) {
  peer();
  const answer = await read(await post({ form, token, body }));
  assert.equal(answer.status_code, 1000, answer.status_message);
  calls = [];
  return { tokenC: answer.data.token, answer };
}

async function renew(token, { body = credentialsBody({ token: TOKEN_B2 }), form = "plain" } = {}) {
  peer();
  const answer = await read(await put(token, { body, form }));
  assert.equal(answer.status_code, 1000, answer.status_message);
  calls = [];
  return { tokenC: answer.data.token, answer };
}

// What every failed registration leaves: nothing registered, the flag free, TOKEN_A still good.
async function failedRegistration(statusCode, message) {
  const saved = record();
  assert.equal(saved.state, "unregistered");
  assert.equal(saved.handshake, null);
  assert.equal(saved.token_b, null);
  assert.equal(saved.token_c_sha256, null);
  assert.equal(saved.last_handshake.status_code, statusCode);
  assert.equal(saved.last_handshake.message, message);
  assert.equal((await ask(PATHS.versions)).status, 200, "TOKEN_A still works");
}

const handshakeOf = (saved) => ({
  kind: saved.last_handshake.kind,
  status_code: saved.last_handshake.status_code,
  message: saved.last_handshake.message,
});

// Front handler

test("unknown paths answer 404 with the OCPI envelope and never reach the object", async () => {
  const t = setup();
  for (const path of ["/", "/ocpi", "/ocpi/2.2", "/ocpi/versions//", "/OCPI/versions", "/oevm", "/oevm/x"]) {
    const response = await ask(path);
    assert.equal(response.status, 404, path);
    assert.equal(response.headers.get("cache-control"), "no-store");
    const answer = await read(response);
    assert.equal(answer.status_code, 2000);
    assert.equal(answer.status_message, "Not found.");
    assert.equal("data" in answer, false);
  }
  assert.deepEqual(t.names, []);
  assert.equal(t.storage.store.size, 0);
});

test("one trailing slash is ignored", async () => {
  setup();
  const envelope = (answer) => ({ ...answer, timestamp: null });
  for (const path of [PATHS.versions, PATHS.details, PATHS.credentials]) {
    const without = await ask(path);
    const plain = await read(without);
    const response = await ask(`${path}/`);
    assert.equal(response.status, 200, path);
    assert.equal(response.headers.get("x-total-count"), without.headers.get("x-total-count"));
    const answer = await read(response);
    assert.equal(answer.status_code, 1000);
    assert.deepEqual(envelope(answer), envelope(plain));
  }
  const versions = await read(await ask(`${PATHS.versions}/`));
  assert.equal(versions.data[0].url, `${WORKER}/ocpi/2.2.1`);
  const details = await read(await ask(`${PATHS.details}/`));
  assert.equal(details.data.endpoints[0].url, `${WORKER}/ocpi/2.2.1/credentials`);
  const credentials = await read(await ask(`${PATHS.credentials}/`));
  assert.equal(credentials.data.url, `${WORKER}/ocpi/versions`);
  const out = await handOut({ path: `${PATHS.connection}/` });
  assert.equal(out.status, 200);
  assert.equal((await out.json()).state, "unregistered");
});

test("versions and version details allow only GET and HEAD, before any token check", async () => {
  const t = setup();
  for (const path of [PATHS.versions, PATHS.details, `${PATHS.details}/`]) {
    for (const method of ["POST", "PUT", "DELETE", "PATCH", "OPTIONS"]) {
      for (const token of [TOKEN_A, null]) {
        const response = await ask(path, { method, token });
        assert.equal(response.status, 405, `${method} ${path}`);
        assert.equal(response.headers.get("allow"), "GET, HEAD");
        const answer = await read(response);
        assert.equal(answer.status_code, 2000);
        assert.equal(answer.status_message, "Only GET and HEAD are allowed.");
      }
    }
  }
  assert.deepEqual(t.names, []);
});

test("OCPI requests without a usable Token header are refused before the object", async () => {
  const t = setup();
  const values = [
    null,
    `Bearer ${TOKEN_A}`,
    "Token",
    "Token ",
    "Token a b",
    `Token ${"~".repeat(65)}`,
    `Token ${"A".repeat(92)}`,
  ];
  for (const path of [PATHS.versions, PATHS.details, PATHS.credentials]) {
    for (const value of values) {
      const headers = value === null ? {} : { authorization: value };
      const response = await ask(path, { token: null, headers });
      assert.equal(response.status, 401, `${path} ${value}`);
      assert.equal(response.headers.get("www-authenticate"), "Token");
      const answer = await read(response);
      assert.equal(answer.status_code, 2000);
      assert.equal(answer.status_message, "Not allowed.");
    }
  }
  assert.equal((await post({ token: null })).status, 401);
  assert.deepEqual(t.names, []);
  assert.equal(calls.length, 0);
});

test("the hand-out allows only GET and needs the pull token, before the object", async () => {
  let t = setup();
  for (const method of ["POST", "PUT", "DELETE", "PATCH"]) {
    const response = await handOut({ method });
    assert.equal(response.status, 405, method);
    assert.equal(response.headers.get("allow"), "GET");
    assert.equal(response.headers.get("cache-control"), "no-store");
    assert.deepEqual(await response.json(), { error: "Only GET is allowed." });
  }
  const refusals = [];
  for (const token of [null, "wrong", `${PULL}x`, PULL.slice(0, -1), TOKEN_A]) {
    refusals.push(await handOut({ token }));
  }
  assert.deepEqual(t.names, []);
  const spaced = "test pull token with spaces not real 1";
  for (const secret of [undefined, PULL.slice(0, 31), spaced]) {
    t = setup({ env: { OCPI_PULL_TOKEN: secret } });
    refusals.push(await handOut({ token: secret ?? PULL }));
    assert.deepEqual(t.names, []);
  }
  for (const response of refusals) {
    assert.equal(response.status, 403);
    assert.equal(response.headers.get("cache-control"), "no-store");
    assert.equal(response.headers.get("www-authenticate"), null);
    const text = await response.text();
    assert.equal(text, '{"error":"Not allowed."}');
    assert.ok(!text.includes(PULL));
  }
});

test("the front handler uses one object by a neutral name", async () => {
  const t = setup();
  await ask(PATHS.versions);
  await ask(PATHS.details);
  await ask(PATHS.credentials);
  await handOut();
  await register();
  assert.ok(t.names.length >= 5);
  assert.deepEqual(new Set(t.names), new Set(["connection"]));
  assert.equal(OBJECT_NAME, "connection");
});

// Envelope, ids and HEAD

test("every OCPI answer has the envelope and a UTC timestamp", async () => {
  const t = setup();
  const seen = [];
  const check = async (response) => {
    assert.match(response.headers.get("content-type"), /^application\/json/);
    assert.equal(response.headers.get("cache-control"), "no-store");
    const answer = await read(response);
    assert.equal(typeof answer.status_code, "number");
    assert.equal(typeof answer.status_message, "string");
    assert.match(answer.timestamp, TIMESTAMP);
    assert.ok(answer.timestamp.length <= 25);
    seen.push(`${response.status} ${answer.status_code}`);
  };
  await check(await ask(PATHS.versions));
  await check(await ask(PATHS.versions, { token: null }));
  await check(await ask(PATHS.versions, { token: "wrong" }));
  await check(await ask("/elsewhere"));
  await check(await ask(PATHS.versions, { method: "POST" }));
  await check(await post({ body: "{" }));
  await check(await post({ body: [] }));
  peer({
    versions: () => {
      throw new TypeError("network down");
    },
  });
  await check(await post());
  peer({ versions: () => ocpiAnswer([{ version: "2.1.1", url: `${PEER}/ocpi/2.1.1` }]) });
  await check(await post());
  peer({ details: () => detailsAnswer([]) });
  await check(await post());
  const held = gatedPeer();
  const first = post();
  await until(() => calls.length === 1);
  await check(await post());
  held.open();
  await check(await first);
  t.storage.failAlways = true;
  await check(await ask(PATHS.versions));
  assert.deepEqual(seen, [
    "200 1000",
    "401 2000",
    "401 2000",
    "404 2000",
    "405 2000",
    "400 2001",
    "200 2001",
    "200 3001",
    "200 3002",
    "200 3003",
    "200 3000",
    "200 1000",
    "500 3000",
  ]);
});

test("every OCPI answer returns the request's X-Request-ID and X-Correlation-ID", async () => {
  setup();
  const responses = [
    await ask(PATHS.versions),
    await ask(PATHS.versions, { token: null }),
    await ask(PATHS.versions, { token: "wrong" }),
    await ask("/elsewhere"),
    await ask(PATHS.details, { method: "POST" }),
    await ask(PATHS.credentials, { method: "PATCH" }),
    await ask(PATHS.versions, { method: "HEAD" }),
  ];
  assert.deepEqual(
    responses.map((r) => r.status),
    [200, 401, 401, 404, 405, 405, 200],
  );
  for (const response of responses) {
    assert.equal(response.headers.get("x-request-id"), "request-1");
    assert.equal(response.headers.get("x-correlation-id"), "correlation-1");
  }
});

test("a request without usable ids gets fresh ones", async () => {
  setup();
  const unusable = { "x-request-id": "r".repeat(300), "x-correlation-id": "a b" };
  for (const options of [{ ids: false }, { ids: false, token: null }, { ids: false, headers: unusable }]) {
    const response = await ask(PATHS.versions, options);
    const requestId = response.headers.get("x-request-id");
    const correlationId = response.headers.get("x-correlation-id");
    assert.match(requestId, UUID);
    assert.match(correlationId, UUID);
    assert.notEqual(requestId, correlationId);
  }
});

test("a POST without ids still ties the calls back to it", async () => {
  setup();
  peer();
  const response = await post({ ids: false });
  assert.equal((await read(response)).status_code, 1000);
  const correlationId = response.headers.get("x-correlation-id");
  assert.match(correlationId, UUID);
  assert.equal(calls.length, 2);
  for (const call of calls) assert.equal(call.init.headers["x-correlation-id"], correlationId);
});

test("HEAD gets the GET answer without a body", async () => {
  setup();
  for (const path of [PATHS.versions, PATHS.details]) {
    const get = await ask(path);
    const head = await ask(path, { method: "HEAD" });
    assert.equal(head.status, 200, path);
    assert.equal(await head.text(), "");
    const names = ["content-type", "cache-control", "x-total-count", "x-limit", "x-request-id", "x-correlation-id"];
    for (const name of names) assert.equal(head.headers.get(name), get.headers.get(name), name);
  }
  assert.equal((await ask(PATHS.versions, { method: "HEAD" })).headers.get("x-total-count"), "1");
  for (const options of [{ token: null }, { token: "wrong" }]) {
    const refused = await ask(PATHS.versions, { method: "HEAD", ...options });
    assert.equal(refused.status, 401);
    assert.equal(refused.headers.get("www-authenticate"), "Token");
    assert.equal(await refused.text(), "");
  }
  const missing = await ask("/elsewhere", { method: "HEAD" });
  assert.equal(missing.status, 404);
  assert.equal(await missing.text(), "");
  const setupHead = await ask(PATHS.credentials, { method: "HEAD" });
  assert.equal(setupHead.status, 405);
  assert.equal(setupHead.headers.get("allow"), "GET, POST");
  assert.equal(await setupHead.text(), "");
  const { tokenC } = await register();
  const peerHead = await ask(PATHS.credentials, { method: "HEAD", token: tokenC });
  assert.equal(peerHead.status, 405);
  assert.equal(peerHead.headers.get("allow"), "GET, PUT, DELETE");
  assert.equal(await peerHead.text(), "");
  const handOutHead = await handOut({ method: "HEAD" });
  assert.equal(handOutHead.status, 405);
  assert.equal(handOutHead.headers.get("allow"), "GET");
  assert.equal(handOutHead.headers.get("cache-control"), "no-store");
  assert.equal(await handOutHead.text(), "");
});

test("no answer is ever marked for sharing with browsers", async () => {
  const t = setup();
  const preflight = {
    origin: "https://elsewhere.example",
    "access-control-request-method": "POST",
    "access-control-request-headers": "authorization",
  };
  for (const path of [PATHS.versions, PATHS.details, PATHS.credentials, PATHS.connection, "/"]) {
    await ask(path, { method: "OPTIONS", token: null, headers: preflight });
    await ask(path, { headers: { origin: "https://elsewhere.example" } });
  }
  await handOut();
  await register();
  await handOut();
  assert.ok(t.answered.length >= 13);
  // send() checks every answer in every test; this repeats it for the ones above.
  for (const { response } of t.answered) {
    for (const name of response.headers.keys()) assert.ok(!name.startsWith("access-control-"), name);
  }
});

// Versions, details and tokens

test("the versions list names only 2.2.1 at the Worker's own address", async () => {
  setup();
  await ask(PATHS.details);
  const before = record();
  const response = await ask(PATHS.versions);
  assert.equal(response.status, 200);
  assert.equal(response.headers.get("x-total-count"), "1");
  assert.equal(response.headers.get("x-limit"), "1");
  const answer = await read(response);
  assert.equal(answer.status_code, 1000);
  assert.equal(answer.status_message, "Success");
  assert.deepEqual(answer.data, [{ version: "2.2.1", url: `${WORKER}/ocpi/2.2.1` }]);
  assert.equal(calls.length, 0);
  const after = record();
  assert.deepEqual({ ...after, last_contact: null }, { ...before, last_contact: null });
  assert.deepEqual(Object.keys(after.last_contact), ["GET /ocpi/2.2.1", "GET /ocpi/versions"]);
});

test("version details list only the credentials endpoint, as SENDER", async () => {
  setup();
  const answer = await read(await ask(PATHS.details));
  assert.equal(answer.status_code, 1000);
  assert.deepEqual(answer.data, {
    version: "2.2.1",
    endpoints: [{ identifier: "credentials", role: "SENDER", url: `${WORKER}/ocpi/2.2.1/credentials` }],
  });
});

test("addresses are always https", async () => {
  setup();
  const base = "http://ocpi.example.workers.dev";
  const versions = await read(await ask(PATHS.versions, { base }));
  assert.equal(versions.data[0].url, `${WORKER}/ocpi/2.2.1`);
  const details = await read(await ask(PATHS.details, { base }));
  assert.equal(details.data.endpoints[0].url, `${WORKER}/ocpi/2.2.1/credentials`);
  const credentials = await read(await ask(PATHS.credentials, { base }));
  assert.equal(credentials.data.url, `${WORKER}/ocpi/versions`);
});

test("TOKEN_A is accepted plain, in Base64 padded or not, URL-safe, with the spec example's newline, and with any case of the scheme word", async () => {
  setup();
  assert.match(btoa(TOKEN_A), /=$/, "the padded form has padding to leave out");
  const values = [
    `Token ${TOKEN_A}`,
    `Token ${btoa(TOKEN_A)}`,
    `Token ${btoa(`${TOKEN_A}\n`)}`,
    `Token ${btoa(TOKEN_A).replace(/=+$/, "")}`,
    `token ${TOKEN_A}`,
    `TOKEN  ${TOKEN_A}`,
  ];
  for (const value of values) {
    const response = await ask(PATHS.versions, { token: null, headers: { authorization: value } });
    assert.equal(response.status, 200, value);
  }
  const secret = "~~~-token-a-for-setup-not-a-real-one";
  setup({ env: { OCPI_TOKEN_A: secret } });
  const standard = btoa(secret);
  assert.match(standard, /[+/]/, "the standard encoding differs from the URL-safe one");
  const urlSafe = standard.replace(/\+/g, "-").replace(/\//g, "_");
  for (const value of [urlSafe, `${urlSafe.replace(/=+$/, "")}`]) {
    const response = await ask(PATHS.versions, { token: null, headers: { authorization: `Token ${value}` } });
    assert.equal(response.status, 200, value);
  }
  assert.equal(record().last_contact["GET /ocpi/versions"].form, "base64");
});

test("near misses are refused and leave no trace", async () => {
  const t = setup();
  await ask(PATHS.details);
  const before = stored();
  const reached = t.names.length;
  assert.equal(btoa(TOKEN_A).slice(0, -1).match(/=/g).length, 1, "one padding character of two");
  const values = [
    `${TOKEN_A}x`,
    TOKEN_A.slice(0, -1),
    btoa(TOKEN_A).slice(0, -3),
    btoa(TOKEN_A).slice(0, -1),
    btoa(TOKEN_A).toLowerCase(),
  ];
  for (const value of values) {
    const response = await ask(PATHS.versions, { token: null, headers: { authorization: `Token ${value}` } });
    assert.equal(response.status, 401, value);
    assert.equal(response.headers.get("www-authenticate"), "Token");
  }
  assert.equal(t.names.length, reached + values.length, "each reached the object");
  assert.equal(stored(), before);
});

test("an unusable setup secret refuses every setup request", async () => {
  const spaced = "test token a with a space in it not real";
  assert.equal(spaced.length, 40);
  for (const secret of [undefined, "", "short", spaced, "x".repeat(65)]) {
    setup({ env: { OCPI_TOKEN_A: secret } });
    const tokens = [TOKEN_A, secret].filter((token) => typeof token === "string" && /^\S+$/.test(token));
    for (const token of tokens) {
      assert.equal((await ask(PATHS.versions, { token })).status, 401, `${secret} ${token}`);
    }
    assert.equal((await post()).status, 401);
    assert.equal(calls.length, 0);
  }
});

test("tokenForms reads only clean tokens", () => {
  assert.deepEqual(tokenForms("Token abc.def"), [{ form: "plain", token: "abc.def" }]);
  assert.deepEqual(tokenForms(`Token ${btoa(TOKEN_B)}`), [
    { form: "plain", token: btoa(TOKEN_B) },
    { form: "base64", token: TOKEN_B },
  ]);
  assert.deepEqual(tokenForms(`Token ${btoa("x\u0001y")}`), [{ form: "plain", token: btoa("x\u0001y") }]);
  assert.equal(
    tokenForms(`Token ${"~".repeat(65)}`).some((f) => f.form === "plain"),
    false,
  );
  const unpadded = btoa("x".repeat(49)).replace(/=+$/, "");
  assert.equal(unpadded.length, 66);
  assert.deepEqual(tokenForms(`Token ${unpadded}`), [{ form: "base64", token: "x".repeat(49) }]);
  assert.deepEqual(tokenForms(`Token ${"A".repeat(92)}`), []);
  for (const header of ["Bearer x", "", null, undefined, "Token", "Token a b"]) {
    assert.deepEqual(tokenForms(header), [], String(header));
  }
});

test("sameToken compares whole strings only", () => {
  assert.equal(sameToken(TOKEN_A, TOKEN_A), true);
  assert.equal(sameToken("", ""), false);
  assert.equal(sameToken(undefined, TOKEN_A), false);
  assert.equal(sameToken(TOKEN_A, undefined), false);
  assert.equal(sameToken(null, TOKEN_A), false);
  assert.equal(sameToken("wrong", TOKEN_A), false);
  assert.equal(sameToken(`${TOKEN_A}x`, TOKEN_A), false);
  assert.equal(sameToken(TOKEN_A.slice(0, -1), TOKEN_A), false);
});

// Before registration

test("GET credentials with TOKEN_A gives the project's details and echoes TOKEN_A", async () => {
  setup();
  for (const form of ["plain", "base64"]) {
    const response = await ask(PATHS.credentials, { form });
    assert.equal(response.status, 200);
    const answer = await read(response);
    assert.equal(answer.status_code, 1000);
    assert.deepEqual(answer.data, expectedCredentials(TOKEN_A));
    assert.ok(!JSON.stringify(answer).includes("logo"));
  }
  assert.equal(calls.length, 0);
  assert.equal(record().state, "unregistered");
});

test("PUT and DELETE with a setup token answer 405", async () => {
  setup();
  for (const method of ["PUT", "DELETE"]) {
    const body = method === "PUT" ? credentialsBody() : undefined;
    const response = await ask(PATHS.credentials, { method, body });
    assert.equal(response.status, 405, method);
    assert.equal(response.headers.get("allow"), "GET, POST");
    const answer = await read(response);
    assert.equal(answer.status_code, 2000);
    assert.equal(answer.status_message, ONLY_POST);
  }
  assert.equal(calls.length, 0);
  assert.equal(record().state, "unregistered");
});

test("other methods answer 405 with Allow for who is asking", async () => {
  const t = setup();
  for (const method of ["PATCH", "OPTIONS"]) {
    const response = await ask(PATHS.credentials, { method });
    assert.equal(response.status, 405);
    assert.equal(response.headers.get("allow"), "GET, POST");
    assert.equal((await read(response)).status_message, NOT_HERE);
  }
  const { tokenC } = await register();
  const response = await ask(PATHS.credentials, { method: "PATCH", token: tokenC });
  assert.equal(response.status, 405);
  assert.equal(response.headers.get("allow"), "GET, PUT, DELETE");
  assert.equal((await read(response)).status_message, NOT_HERE);
  const reached = t.names.length;
  const anonymous = await ask(PATHS.credentials, { method: "PATCH", token: null });
  assert.equal(anonymous.status, 401);
  assert.equal(anonymous.headers.get("www-authenticate"), "Token");
  assert.equal(t.names.length, reached, "refused by the front handler");
});

test("a body that is not JSON gets HTTP 400 and OCPI 2001, for POST and PUT", async () => {
  setup();
  const bodies = ["{", "not json", "", new Uint8Array([0x7b, 0xff, 0xfe, 0x7d])];
  for (const body of bodies) {
    const response = await post({ body });
    assert.equal(response.status, 400);
    const answer = await read(response);
    assert.equal(answer.status_code, 2001);
    assert.equal(answer.status_message, NOT_JSON);
    assert.deepEqual(handshakeOf(record()), { kind: "register", status_code: 2001, message: NOT_JSON });
  }
  assert.equal(calls.length, 0);
  assert.equal(record().state, "unregistered");
  const { tokenC } = await register();
  for (const body of bodies) {
    const response = await put(tokenC, { body });
    assert.equal(response.status, 400);
    assert.equal((await read(response)).status_code, 2001);
    assert.deepEqual(handshakeOf(record()), { kind: "update", status_code: 2001, message: NOT_JSON });
  }
  assert.equal(calls.length, 0);
  assert.equal((await ask(PATHS.credentials, { token: tokenC })).status, 200);
  assert.equal(record().token_b, TOKEN_B);
});

test("a body over the limit gets OCPI 2001 and is never held, for POST and PUT", async () => {
  setup();
  const refuse = async (method, token, kind) => {
    let pulls = 0;
    const counted = () => {
      pulls += 1;
    };
    const check = async (response) => {
      assert.equal(response.status, 200);
      const answer = await read(response);
      assert.equal(answer.status_code, 2001);
      assert.equal(answer.status_message, TOO_LARGE);
      assert.deepEqual(handshakeOf(record()), { kind, status_code: 2001, message: TOO_LARGE });
    };
    // A content-length over the limit is refused without reading anything.
    const declared = { method, token, body: stream(100, counted), headers: { "content-length": "99999" } };
    await check(await ask(PATHS.credentials, declared));
    assert.equal(pulls, 0);
    // Without one, reading stops just past the limit.
    const over = request(PATHS.credentials, { method, token, body: new Uint8Array(MAX_BODY_BYTES + 1).fill(0x20) });
    assert.equal(over.headers.get("content-length"), null);
    await check(await send(over, "over the limit"));
    await check(await ask(PATHS.credentials, { method, token, body: stream(1024, counted) }));
    assert.ok(pulls <= MAX_BODY_BYTES / 1024 + 3, `${pulls} reads`);
  };
  await refuse("POST", TOKEN_A, "register");
  assert.equal(calls.length, 0);
  const { tokenC } = await register();
  await refuse("PUT", tokenC, "update");
  assert.equal(calls.length, 0);
  // A body of exactly the limit is read.
  setup();
  peer();
  const text = JSON.stringify(credentialsBody());
  const padded = text + " ".repeat(MAX_BODY_BYTES - text.length);
  assert.equal(new TextEncoder().encode(padded).length, MAX_BODY_BYTES);
  assert.equal((await read(await post({ body: padded }))).status_code, 1000);
});

test("a body from an unknown caller is never read", async () => {
  const t = setup();
  for (const method of ["POST", "PUT"]) {
    let pulls = 0;
    const body = stream(1024, () => {
      pulls += 1;
    });
    const reached = t.names.length;
    const response = await ask(PATHS.credentials, { method, token: "wrong", body });
    assert.equal(response.status, 401);
    assert.equal(t.names.length, reached + 1, "the object refused it");
    assert.ok(pulls <= 1, `${pulls} reads`);
  }
  assert.equal(calls.length, 0);
});

test("unusable fields get OCPI 2001 over HTTP 200, naming the field but never a value, for POST and PUT", async () => {
  const userinfo = `https://${["user", "pw"].join(":")}@peer.example/ocpi/versions`;
  const longUrl = `${PEER}/${"v".repeat(235)}`;
  assert.equal(longUrl.length, 256);
  const cases = [
    [[credentialsBody()], NOT_CREDENTIALS, "ABC"],
    [null, NOT_CREDENTIALS, "null"],
    ["just a string", NOT_CREDENTIALS, "just"],
    [{ url: VERSIONS_URL }, TOKEN_MESSAGE, "peer.example"],
    [credentialsBody({ token: "a b" }), TOKEN_MESSAGE, "a b"],
    [credentialsBody({ token: "t".repeat(256) }), TOKEN_MESSAGE, "tttt"],
    [credentialsBody({ token: "test-token-\u00e9" }), TOKEN_MESSAGE, "\u00e9"],
    [credentialsBody({ token: 12345 }), TOKEN_MESSAGE, "12345"],
    [credentialsBody({ url: "http://peer.example/ocpi/versions" }), URL_MESSAGE, "http:"],
    [credentialsBody({ url: "not a url" }), URL_MESSAGE, "not a url"],
    [credentialsBody({ url: longUrl }), URL_MESSAGE, "vvvv"],
    [credentialsBody({ url: userinfo }), URL_MESSAGE, "user:pw"],
    [credentialsBody({ url: "https://192.0.2.1/ocpi/versions" }), URL_MESSAGE, "192.0.2.1"],
    [credentialsBody({ url: "https://0x7f.1/ocpi/versions" }), URL_MESSAGE, "0x7f"],
    [credentialsBody({ url: "https://[2001:db8::1]/ocpi/versions" }), URL_MESSAGE, "2001:db8"],
    [credentialsBody({ url: "https://localhost/ocpi/versions" }), URL_MESSAGE, "localhost/"],
    [credentialsBody({ url: "https://api.localhost/ocpi/versions" }), URL_MESSAGE, "api."],
    [credentialsBody({ url: "https://localhost./ocpi/versions" }), URL_MESSAGE, "localhost./"],
    [credentialsBody({ url: "https://api.localhost./ocpi/versions" }), URL_MESSAGE, "localhost./"],
    [credentialsBody({ url: "https://peer.example:8443/ocpi/versions" }), URL_MESSAGE, "8443"],
    [credentialsBody({ url: "https://peer/ocpi/versions" }), URL_MESSAGE, "https://peer/"],
    [credentialsBody({ url: "https://peer./ocpi/versions" }), URL_MESSAGE, "https://peer./"],
  ];
  const refuse = async (method, token, kind) => {
    for (const [body, message, value] of cases) {
      const options = { method, token, body: body === null ? "null" : body };
      if (typeof body === "string") options.body = JSON.stringify(body);
      const response = await ask(PATHS.credentials, options);
      assert.equal(response.status, 200, message);
      const answer = await read(response);
      assert.equal(answer.status_code, 2001, value);
      assert.equal(answer.status_message, message);
      assert.ok(!answer.status_message.includes(value), value);
      assert.deepEqual(handshakeOf(record()), { kind, status_code: 2001, message });
    }
  };
  setup();
  await refuse("POST", TOKEN_A, "register");
  assert.equal(record().state, "unregistered");
  assert.equal(calls.length, 0);
  const { tokenC } = await register();
  await refuse("PUT", tokenC, "update");
  assert.equal(calls.length, 0);
  assert.equal(record().token_b, TOKEN_B);
});

test("fields the Worker does not rely on never block a registration", async () => {
  const role = (r, p, c) => ({ role: r, party_id: p, country_code: c });
  const known = [role("CPO", "ABC", "GB")];
  const noRoles = credentialsBody();
  delete noRoles.roles;
  const eleven = Array.from({ length: 11 }, (_, i) => role("CPO", `A${String(i).padStart(2, "0")}`, "GB"));
  const odd = [{ role: "XYZ", party_id: "ABCD", country_code: "GBR", business_details: null }];
  const long = `test-token-b-${"x".repeat(87)}`;
  assert.equal(long.length, 100);
  const cases = [
    [noRoles, [], ["no roles listed"]],
    [credentialsBody({ roles: [] }), [], ["no roles listed"]],
    [credentialsBody({ roles: [null, "x"] }), [role(null, null, null), role(null, null, null)], []],
    [credentialsBody({ roles: "x" }), [], ["no roles listed"]],
    [credentialsBody({ roles: eleven }), eleven.slice(0, 10), []],
    [credentialsBody({ roles: odd }), [role(null, null, null)], []],
    [credentialsBody({ token: long }), known, ["token longer than 64 characters"]],
    [{ ...credentialsBody(), hello: "world", party_id: 7, business_details: null }, known, []],
  ];
  for (const [body, roles, notes] of cases) {
    setup();
    peer();
    const answer = await read(await post({ body }));
    assert.equal(answer.status_code, 1000, answer.status_message);
    assert.equal(authorization(calls[0]), `Token ${body.token}`);
    const saved = record();
    assert.deepEqual(saved.peer.roles, roles);
    assert.deepEqual(saved.last_handshake.notes, notes);
    const out = await (await handOut()).json();
    assert.equal(out.token, body.token);
    assert.deepEqual(out.peer_roles, roles);
  }
});

// Registration

test("a POST with TOKEN_A reads the peer's versions then its 2.2.1 details with TOKEN_B, 2 seconds after the first answer ended, and answers a new TOKEN_C", async () => {
  const t = setup();
  peer();
  const response = await post();
  assert.equal(response.status, REGISTERED_HTTP_STATUS);
  assert.equal(response.status, 200);
  const answer = await read(response);
  assert.equal(answer.status_code, 1000);
  assert.equal(answer.status_message, "Success");
  assert.deepEqual(
    calls.map((c) => c.url),
    [VERSIONS_URL, DETAILS_URL],
  );
  assert.deepEqual(t.waits, [GAP_MS]);
  assert.equal(calls[1].at - (calls[0].at + t.answerMs), GAP_MS, "measured from the end of the answer");
  for (const { init } of calls) {
    assert.equal(init.method, "GET");
    assert.equal(init.body, undefined);
    assert.equal(init.redirect, "manual");
    assert.ok(init.signal instanceof AbortSignal);
    assert.deepEqual(init.cf, { cacheTtl: 0, cacheEverything: false });
    assert.deepEqual(Object.keys(init.headers).sort(), [
      "accept",
      "authorization",
      "user-agent",
      "x-correlation-id",
      "x-request-id",
    ]);
    assert.equal(init.headers.accept, "application/json");
    assert.equal(init.headers.authorization, `Token ${TOKEN_B}`);
    assert.equal(init.headers["user-agent"], USER_AGENT);
    assert.equal(init.headers["x-correlation-id"], "correlation-1");
    assert.notEqual(init.headers["x-request-id"], "request-1");
  }
  assert.notEqual(calls[0].init.headers["x-request-id"], calls[1].init.headers["x-request-id"]);
  assert.match(answer.data.token, NEW_TOKEN);
  assert.deepEqual(answer.data, expectedCredentials(answer.data.token));
});

test("a registration is one stored JSON record and never the raw TOKEN_C", async () => {
  const t = setup();
  peer();
  const tokenC = (await read(await post())).data.token;
  assert.deepEqual([...t.storage.store.keys()], [STORAGE_KEY]);
  assert.equal(typeof stored(), "string");
  const saved = record();
  const hashA = await sha256Hex(TOKEN_A);
  assert.equal(saved.schema_version, 1);
  assert.equal(saved.state, "registered");
  assert.equal(saved.token_b, TOKEN_B);
  assert.equal(saved.token_b_encoding, "plain");
  assert.equal(saved.token_c_sha256, await sha256Hex(tokenC));
  assert.match(saved.token_c_sha256, /^[0-9a-f]{64}$/);
  assert.equal(saved.previous_token_c, null);
  assert.deepEqual(saved.setup_retry, { sha256: hashA, until: t.clock.now + SETUP_RETRY_GRACE_MS });
  assert.deepEqual(saved.retired_token_a_sha256, [hashA]);
  assert.deepEqual(saved.peer, {
    versions_url: VERSIONS_URL,
    version: "2.2.1",
    details_url: DETAILS_URL,
    credentials_url: ENDPOINTS.credentials,
    locations_url: ENDPOINTS.locations,
    tariffs_url: ENDPOINTS.tariffs,
    roles: [{ role: "CPO", party_id: "ABC", country_code: "GB" }],
  });
  assert.equal(saved.handshake, null);
  assert.equal(saved.registered_at, iso(t.clock.now));
  assert.equal(saved.registered_at, saved.updated_at);
  assert.equal(saved.ended_at, null);
  assert.equal(saved.last_call_ended_at, t.clock.now);
  assert.deepEqual(saved.last_handshake, {
    at: iso(t.clock.now),
    kind: "register",
    status_code: 1000,
    message: "Success",
    forms_tried: ["plain", "plain"],
    notes: [],
  });
  assert.deepEqual(saved.handouts, { count: 0, last_at: null });
  for (const secret of [tokenC, TOKEN_A, PULL]) assert.ok(!stored().includes(secret));
});

test("a Base64 POST is called back in Base64", async () => {
  setup();
  peer();
  const answer = await read(await post({ form: "base64" }));
  assert.equal(answer.status_code, 1000);
  assert.equal(calls.length, 2);
  for (const call of calls) assert.equal(authorization(call), `Token ${btoa(TOKEN_B)}`);
  assert.equal(record().token_b_encoding, "base64");
  assert.deepEqual(record().last_handshake.forms_tried, ["base64", "base64"]);
});

test("a refused versions call is tried once in the other form", async () => {
  const t = setup();
  peer({
    versions: (url, init) =>
      init.headers.authorization === `Token ${TOKEN_B}` ? new Response(null, { status: 401 }) : versionsAnswer(),
  });
  const answer = await read(await post());
  assert.equal(answer.status_code, 1000);
  assert.deepEqual(
    calls.map((c) => [c.url, authorization(c)]),
    [
      [VERSIONS_URL, `Token ${TOKEN_B}`],
      [VERSIONS_URL, `Token ${btoa(TOKEN_B)}`],
      [DETAILS_URL, `Token ${btoa(TOKEN_B)}`],
    ],
  );
  assert.deepEqual(t.waits, [2000, 2000]);
  assert.deepEqual(record().last_handshake.forms_tried, ["plain", "base64", "base64"]);
  assert.equal(record().token_b_encoding, "base64");
});

test("a refused details call is tried once in the other form", async () => {
  for (const status of [401, 403]) {
    setup();
    peer({
      details: (url, init) =>
        init.headers.authorization === `Token ${TOKEN_B}` ? new Response(null, { status }) : detailsAnswer(),
    });
    const answer = await read(await post());
    assert.equal(answer.status_code, 1000, String(status));
    assert.deepEqual(
      calls.map((c) => [c.url, authorization(c)]),
      [
        [VERSIONS_URL, `Token ${TOKEN_B}`],
        [DETAILS_URL, `Token ${TOKEN_B}`],
        [DETAILS_URL, `Token ${btoa(TOKEN_B)}`],
      ],
    );
    assert.equal(record().token_b_encoding, "base64");
    assert.deepEqual(record().last_handshake.forms_tried, ["plain", "plain", "base64"]);
  }
});

test("only one fallback per registration", async () => {
  setup();
  peer({
    versions: (url, init) =>
      init.headers.authorization === `Token ${TOKEN_B}` ? new Response(null, { status: 401 }) : versionsAnswer(),
    details: (url, init) =>
      init.headers.authorization === `Token ${btoa(TOKEN_B)}` ? new Response(null, { status: 401 }) : detailsAnswer(),
  });
  const answer = await read(await post());
  const message = api("its 2.2.1 details endpoint answered HTTP 401");
  assert.equal(answer.status_code, 3001);
  assert.equal(answer.status_message, message);
  assert.equal(calls.length, 3);
  await failedRegistration(3001, message);
});

test("after TOKEN_C is used, TOKEN_A is refused, and a POST with it answers 405", async () => {
  setup();
  const { tokenC } = await register();
  assert.equal((await ask(PATHS.versions, { token: tokenC })).status, 200);
  for (const path of [PATHS.versions, PATHS.details, PATHS.credentials]) {
    const response = await ask(path);
    assert.equal(response.status, 401, path);
    assert.equal(response.headers.get("www-authenticate"), "Token");
  }
  const response = await post();
  assert.equal(response.status, 405);
  assert.equal(response.headers.get("allow"), "GET, PUT, DELETE");
  assert.equal((await read(response)).status_message, USED);
  assert.equal(calls.length, 0);
  for (const form of ["plain", "base64"]) {
    assert.equal((await ask(PATHS.versions, { token: tokenC, form })).status, 200, form);
    const echoed = await read(await ask(PATHS.credentials, { token: tokenC, form }));
    assert.deepEqual(echoed.data, expectedCredentials(tokenC));
  }
});

test("a POST with TOKEN_C answers 405 with Allow GET, PUT, DELETE", async () => {
  setup();
  const { tokenC } = await register();
  const first = await post({ token: tokenC });
  assert.equal(first.status, 405);
  const before = stored();
  const response = await post({ token: tokenC });
  assert.equal(response.status, 405);
  assert.equal(response.headers.get("allow"), "GET, PUT, DELETE");
  const answer = await read(response);
  assert.equal(answer.status_code, 2000);
  assert.equal(answer.status_message, REGISTERED);
  assert.equal(stored(), before);
  assert.equal(calls.length, 0);
  assert.equal(record().token_c_sha256, await sha256Hex(tokenC));
});

test("each TOKEN_C is new", async () => {
  setup();
  const first = (await register()).tokenC;
  setup();
  const second = (await register()).tokenC;
  assert.notEqual(first, second);
  const made = new Set(Array.from({ length: 100 }, () => newToken()));
  assert.equal(made.size, 100);
  for (const token of made) assert.match(token, NEW_TOKEN);
});

test("only a locations endpoint is required", async () => {
  const without = (name) => ALL_ENDPOINTS.filter((e) => e.identifier !== name);
  const cases = [
    [without("tariffs"), "tariffs_url", null, ["no tariffs endpoint"]],
    [without("credentials"), "credentials_url", null, ["no credentials endpoint"]],
    [
      [...without("tariffs"), endpoint("tariffs", "SENDER", "http://peer.example/ocpi/cpo/2.2.1/tariffs")],
      "tariffs_url",
      null,
      ["tariffs endpoint address not usable"],
    ],
    [
      [...without("credentials"), endpoint("credentials", "SENDER", "https://peer.example:8443/credentials")],
      "credentials_url",
      null,
      ["credentials endpoint address not usable"],
    ],
    [
      [endpoint("locations", "SENDER", "http://peer.example/old"), ...ALL_ENDPOINTS],
      "locations_url",
      ENDPOINTS.locations,
      [],
    ],
    [[endpoint("locations", "SENDER", ENDPOINTS.locations)], "tariffs_url", null, [
      "no tariffs endpoint",
      "no credentials endpoint",
    ]],
  ];
  for (const [endpoints, field, value, notes] of cases) {
    setup();
    peer({ details: () => detailsAnswer(endpoints) });
    const answer = await read(await post());
    assert.equal(answer.status_code, 1000, answer.status_message);
    const saved = record();
    assert.equal(saved.peer[field], value, field);
    assert.deepEqual(saved.last_handshake.notes, notes);
    const out = await (await handOut()).json();
    assert.equal(out.tariffs_url, saved.peer.tariffs_url);
    assert.equal(out.locations_url, saved.peer.locations_url);
  }
});

// Handshake failures

test("an unreachable peer gives 3001", async () => {
  setup();
  peer({
    versions: () => {
      throw new TypeError("network down");
    },
  });
  const answer = await read(await post());
  const message = api("its versions endpoint could not be reached");
  assert.equal(answer.status_code, 3001);
  assert.equal(answer.status_message, message);
  await failedRegistration(3001, message);
});

test("a peer that does not answer in time gives 3001", async () => {
  const t = setup();
  t.instance().timeoutMs = 5;
  peer({
    versions: (url, init) =>
      new Promise((resolve, reject) => {
        init.signal.addEventListener("abort", () => reject(new DOMException("The operation was aborted.", "AbortError")));
      }),
  });
  const answer = await read(await post());
  const message = api("its versions endpoint did not answer in time");
  assert.equal(answer.status_code, 3001);
  assert.equal(answer.status_message, message);
  assert.equal(calls.length, 1);
  await failedRegistration(3001, message);
});

test("an answer that never ends is given up", async () => {
  const t = setup();
  t.instance().timeoutMs = 5;
  peer({ versions: () => new Response(hanging(), { headers: { "content-type": "application/json" } }) });
  const answer = await read(await post());
  const message = api("its versions endpoint did not answer in time");
  assert.equal(answer.status_code, 3001);
  assert.equal(answer.status_message, message);
  await failedRegistration(3001, message);
});

test("a large answer is never held", async () => {
  const message = api("its versions endpoint gave too large an answer");
  setup();
  let pulls = 0;
  const counted = () => {
    pulls += 1;
  };
  const tenMegabytes = 10 * 1024 * 1024;
  peer({ versions: () => new Response(stream(10_240, counted), { headers: { "content-length": String(tenMegabytes) } }) });
  let answer = await read(await post());
  assert.equal(answer.status_code, 3001);
  assert.equal(answer.status_message, message);
  assert.equal(pulls, 0);
  await failedRegistration(3001, message);
  setup();
  peer({ versions: () => new Response(stream(10_240, counted)) });
  answer = await read(await post());
  assert.equal(answer.status_message, message);
  assert.ok(pulls <= MAX_PEER_BODY_BYTES / 1024 + 3, `${pulls} reads`);
  await failedRegistration(3001, message);
});

test("redirects are never followed", async () => {
  const message = api("its versions endpoint answered with a redirect, which is not followed");
  for (const [status, location] of [
    [302, "https://elsewhere.example/"],
    [301, `${PEER}/ocpi/versions/`],
  ]) {
    setup();
    peer({ versions: () => new Response(null, { status, headers: { location } }) });
    const answer = await read(await post());
    assert.equal(answer.status_code, 3001);
    assert.equal(answer.status_message, message);
    assert.deepEqual(
      calls.map((c) => c.url),
      [VERSIONS_URL],
    );
    await failedRegistration(3001, message);
  }
});

test("unusable answers give 3001 with their own message", async () => {
  const raw = (body, headers = { "content-type": "application/json" }) => () => new Response(body, { headers });
  const cases = [
    [{ versions: () => new Response("{}", { status: 500 }) }, "its versions endpoint answered HTTP 500", 1],
    [{ versions: raw("<html></html>", { "content-type": "text/html" }) }, "its versions endpoint did not answer with JSON", 1],
    [{ versions: raw('{"data":[]}') }, "its versions endpoint did not answer with an OCPI response", 1],
    [{ versions: raw('{"status_code":2001,"status_message":"x"}') }, "its versions endpoint answered OCPI status 2001", 1],
    [{ versions: raw(new Uint8Array([0x7b, 0xff, 0x7d])) }, "its versions endpoint did not answer with JSON", 1],
    [{ details: raw("null") }, "its 2.2.1 details endpoint did not answer with an OCPI response", 2],
    [{ details: () => ocpiAnswer({ version: "2.2", endpoints: [] }) }, "its version details are not for version 2.2.1", 2],
    [{ details: () => ocpiAnswer({ version: "2.2.1" }) }, "its version details are not for version 2.2.1", 2],
    [
      { versions: () => ocpiAnswer([{ version: "2.2.1", url: "http://peer.example/ocpi/2.2.1" }]) },
      "its address for version 2.2.1 is not an https address this Worker will use",
      1,
    ],
    [{ versions: () => detailsAnswer() }, "the url given is a version details address, not a versions address", 1],
    [{ versions: () => ocpiAnswer("versions") }, "its versions endpoint did not answer with a list of versions", 1],
  ];
  for (const [overrides, text, count] of cases) {
    setup();
    peer(overrides);
    const answer = await read(await post());
    assert.equal(answer.status_code, 3001, text);
    assert.equal(answer.status_message, api(text));
    assert.equal(calls.length, count, text);
    await failedRegistration(3001, api(text));
  }
});

test("a versions list without 2.2.1 gives 3002 and no second call", async () => {
  setup();
  peer({ versions: () => ocpiAnswer([{ version: "2.1.1", url: `${PEER}/ocpi/2.1.1` }]) });
  const answer = await read(await post());
  const message = "The client's versions list has no version 2.2.1.";
  assert.equal(answer.status_code, 3002);
  assert.equal(answer.status_message, message);
  assert.equal(calls.length, 1);
  await failedRegistration(3002, message);
});

test("a missing or unusable locations endpoint gives 3003", async () => {
  const credentials = endpoint("credentials", "SENDER", ENDPOINTS.credentials);
  const cases = [
    [[credentials, endpoint("locations", "RECEIVER", ENDPOINTS.locations)], LACK],
    [[credentials], LACK],
    [[credentials, endpoint("locations", "SENDER", "http://peer.example/ocpi/cpo/2.2.1/locations")], UNUSABLE],
    [[credentials, endpoint("locations", "SENDER", "https://192.0.2.1/ocpi/cpo/2.2.1/locations")], UNUSABLE],
  ];
  for (const [endpoints, message] of cases) {
    setup();
    peer({ details: () => detailsAnswer(endpoints) });
    const answer = await read(await post());
    assert.equal(answer.status_code, 3003);
    assert.equal(answer.status_message, message);
    assert.equal(calls.length, 2);
    await failedRegistration(3003, message);
  }
});

test("a failed handshake keeps the gap for the next one", async () => {
  const t = setup({ answerMs: 0 });
  peer({ versions: () => new Response(null, { status: 500 }) });
  assert.equal((await read(await post())).status_code, 3001);
  assert.deepEqual(t.waits, []);
  assert.equal(record().last_call_ended_at, 1_000_000);
  t.clock.now = 1_000_500;
  peer();
  assert.equal((await read(await post())).status_code, 1000);
  assert.deepEqual(t.waits, [1500, GAP_MS]);
});

// Lost replies

test("a POST whose caller has hung up is not saved", async () => {
  setup();
  const held = gatedPeer();
  const hangUp = new AbortController();
  const pending = post({ signal: hangUp.signal });
  await until(() => calls.length === 1);
  hangUp.abort();
  held.open();
  const answer = await read(await pending);
  assert.equal(answer.status_code, 3001);
  assert.equal(answer.status_message, LATE);
  assert.equal(calls.length, 1);
  await failedRegistration(3001, LATE);
});

test("a PUT whose caller has hung up changes nothing", async () => {
  setup();
  const { tokenC } = await register();
  const before = record();
  const held = gatedPeer();
  const hangUp = new AbortController();
  const pending = put(tokenC, { signal: hangUp.signal });
  await until(() => calls.length === 1);
  hangUp.abort();
  held.open();
  const answer = await read(await pending);
  assert.equal(answer.status_code, 3001);
  assert.equal(answer.status_message, LATE);
  assert.equal(calls.length, 1);
  assert.equal(record().token_c_sha256, before.token_c_sha256);
  assert.equal(record().handshake, null);
  assert.equal((await ask(PATHS.versions, { token: tokenC })).status, 200);
  const out = await (await handOut()).json();
  assert.equal(out.token, TOKEN_B);
  assert.equal(out.updated_at, before.updated_at);
});

test("a handshake past its budget starts no call and saves nothing", async () => {
  let t = setup();
  peer({
    versions: () => {
      t.clock.now += HANDSHAKE_BUDGET_MS;
      return versionsAnswer();
    },
  });
  let answer = await read(await post());
  assert.equal(answer.status_code, 3001);
  assert.equal(answer.status_message, LATE);
  assert.equal(calls.length, 1);
  await failedRegistration(3001, LATE);
  t = setup();
  peer({
    details: () => {
      t.clock.now += HANDSHAKE_BUDGET_MS;
      return detailsAnswer();
    },
  });
  answer = await read(await post());
  assert.equal(answer.status_code, 3001);
  assert.equal(answer.status_message, LATE);
  assert.equal(calls.length, 2);
  await failedRegistration(3001, LATE);
});

test("a retried registration within the grace replaces one whose reply was lost", async () => {
  setup();
  const lost = (await register()).tokenC;
  assert.equal((await ask(PATHS.versions)).status, 200);
  peer();
  const answer = await read(await post());
  assert.equal(answer.status_code, 1000);
  const tokenC = answer.data.token;
  assert.notEqual(tokenC, lost);
  assert.equal(record().token_c_sha256, await sha256Hex(tokenC));
  assert.deepEqual(record().retired_token_a_sha256, [await sha256Hex(TOKEN_A)]);
  assert.equal((await ask(PATHS.versions, { token: lost })).status, 401);
  assert.equal((await ask(PATHS.versions, { token: tokenC })).status, 200);
});

test("the setup token's grace ends after its time, or once TOKEN_C is used", async () => {
  let t = setup();
  await register();
  t.clock.now += SETUP_RETRY_GRACE_MS;
  assert.equal((await ask(PATHS.versions)).status, 401);
  const response = await post();
  assert.equal(response.status, 405);
  assert.equal((await read(response)).status_message, USED);
  t = setup();
  const { tokenC } = await register();
  assert.notEqual(record().setup_retry, null);
  assert.equal((await ask(PATHS.versions, { token: tokenC })).status, 200);
  assert.equal(record().setup_retry, null);
  assert.equal((await ask(PATHS.versions)).status, 401);
});

test("after a PUT the previous TOKEN_C still works until the new one is used", async () => {
  let t = setup();
  const first = (await register()).tokenC;
  assert.equal((await ask(PATHS.versions, { token: first })).status, 200);
  const second = (await renew(first)).tokenC;
  assert.deepEqual(record().previous_token_c, {
    sha256: await sha256Hex(first),
    until: t.clock.now + PREVIOUS_TOKEN_GRACE_MS,
  });
  assert.equal((await ask(PATHS.versions, { token: first })).status, 200);
  assert.notEqual(record().previous_token_c, null, "using the old token keeps the grace");
  const third = (await renew(first, { body: credentialsBody({ token: "test-token-b-third-from-the-peer" }) })).tokenC;
  assert.equal(record().token_c_sha256, await sha256Hex(third));
  assert.equal(record().previous_token_c.sha256, await sha256Hex(first));
  assert.equal((await ask(PATHS.versions, { token: third })).status, 200);
  assert.equal(record().previous_token_c, null);
  assert.equal((await ask(PATHS.versions, { token: first })).status, 401);
  assert.equal((await ask(PATHS.versions, { token: second })).status, 401);
  t = setup();
  const old = (await register()).tokenC;
  const renewed = (await renew(old)).tokenC;
  t.clock.now += PREVIOUS_TOKEN_GRACE_MS;
  assert.equal((await ask(PATHS.versions, { token: old })).status, 401);
  assert.equal((await ask(PATHS.versions, { token: renewed })).status, 200);
});

test("a caller whose token stops working while its body arrives is refused", async () => {
  setup();
  const { tokenC } = await register();
  // A retry with the setup token, while the peer starts using TOKEN_C.
  let held = gate();
  let pulled = false;
  const body = gatedBody(held, JSON.stringify(credentialsBody()), () => {
    pulled = true;
  });
  const retry = post({ body });
  await until(() => pulled);
  assert.equal((await ask(PATHS.versions, { token: tokenC })).status, 200);
  held.open();
  const response = await retry;
  assert.equal(response.status, 405);
  assert.equal((await read(response)).status_message, USED);
  // A renewal whose connection is ended before its body arrives.
  held = gate();
  pulled = false;
  const renewal = put(tokenC, {
    body: gatedBody(held, JSON.stringify(credentialsBody({ token: TOKEN_B2 })), () => {
      pulled = true;
    }),
  });
  await until(() => pulled);
  assert.equal((await read(await ask(PATHS.credentials, { method: "DELETE", token: tokenC }))).status_code, 1000);
  held.open();
  assert.equal((await renewal).status, 401);
  assert.equal(record().state, "ended");
  assert.equal(calls.length, 0);
});

// Concurrency

test("while a handshake waits on the peer, other handshakes and the hand-out are refused, but versions, details and credentials are still answered", async () => {
  setup();
  const held = gatedPeer();
  const first = post();
  await until(() => calls.length === 1);
  const second = await post();
  assert.equal(second.status, 200);
  const answer = await read(second);
  assert.equal(answer.status_code, 3000);
  assert.equal(answer.status_message, BUSY);
  const out = await handOut();
  assert.equal(out.status, 409);
  const report = await out.json();
  assert.deepEqual(Object.keys(report), [
    "state",
    "retry_after_seconds",
    "handouts",
    "last_handshake",
    "last_contact",
  ]);
  assert.equal(report.state, "handshake_in_progress");
  const seconds = Number(out.headers.get("retry-after"));
  assert.ok(seconds >= 1 && seconds <= 60, String(seconds));
  assert.equal(report.retry_after_seconds, seconds);
  for (const path of [PATHS.versions, PATHS.details, PATHS.credentials]) {
    assert.equal((await ask(path)).status, 200, path);
  }
  held.open();
  assert.equal((await read(await first)).status_code, 1000);
  assert.equal(calls.length, 2);
});

test("POSTs that arrive together start one handshake", async () => {
  setup();
  const held = gatedPeer();
  const settled = [];
  const posts = [0, 1, 2].map(() =>
    post()
      .then(read)
      .then((answer) => {
        settled.push(answer.status_code);
        return answer;
      }),
  );
  await until(() => settled.length === 2);
  assert.equal(calls.length, 1);
  assert.deepEqual(settled, [3000, 3000]);
  held.open();
  const codes = (await Promise.all(posts)).map((answer) => answer.status_code);
  assert.deepEqual(
    [...codes].sort((a, b) => a - b),
    [1000, 3000, 3000],
  );
  assert.equal(calls.length, 2);
  assert.equal(record().state, "registered");
});

test("a stale handshake flag is ignored after a minute", async () => {
  let t = setup();
  await ask(PATHS.versions);
  rewrite({ handshake: { id: "an-old-flag", kind: "register", started_at: t.clock.now - 61_000 } });
  peer();
  assert.equal((await read(await post())).status_code, 1000);
  assert.equal(record().handshake, null);
  t = setup();
  await ask(PATHS.versions);
  rewrite({ handshake: { id: "a-recent-flag", kind: "register", started_at: t.clock.now - 30_000 } });
  peer();
  const answer = await read(await post());
  assert.equal(answer.status_code, 3000);
  assert.equal(answer.status_message, BUSY);
  assert.equal(calls.length, 0);
  // The hand-out says when the flag lapses: at least 1 second, and never more than 60.
  for (const [age, seconds] of [
    [30_000, 30],
    [59_999, 1],
    [-5_000, 60],
  ]) {
    rewrite({ handshake: { id: "a-recent-flag", kind: "register", started_at: t.clock.now - age } });
    const out = await handOut();
    assert.equal(out.status, 409, String(age));
    assert.equal(out.headers.get("retry-after"), String(seconds));
    assert.equal((await out.json()).retry_after_seconds, seconds);
  }
});

test("an overtaken handshake stops without calling again or writing", async () => {
  const t = setup();
  const held = gatedPeer();
  const first = post();
  await until(() => calls.length === 1);
  t.clock.now += 61_000;
  const second = await read(await post());
  assert.equal(second.status_code, 1000);
  const after = stored();
  held.open();
  const overtaken = await read(await first);
  assert.equal(overtaken.status_code, 3000);
  assert.equal(overtaken.status_message, STOPPED);
  assert.equal(calls.length, 3);
  assert.equal(stored(), after);
  assert.equal(record().token_c_sha256, await sha256Hex(second.data.token));
});

test("DELETE during a renewal is refused", async () => {
  setup();
  const { tokenC } = await register();
  const held = gatedPeer();
  const renewal = put(tokenC);
  await until(() => calls.length === 1);
  const answer = await read(await ask(PATHS.credentials, { method: "DELETE", token: tokenC }));
  assert.equal(answer.status_code, 3000);
  assert.equal(answer.status_message, BUSY);
  held.open();
  assert.equal((await read(await renewal)).status_code, 1000);
  assert.equal(record().state, "registered");
});

test("a body that is not JSON gets HTTP 400 even during a handshake", async () => {
  setup();
  const held = gatedPeer();
  const first = post();
  await until(() => calls.length === 1);
  const response = await post({ body: "{" });
  assert.equal(response.status, 400);
  const answer = await read(response);
  assert.equal(answer.status_code, 2001);
  assert.equal(answer.status_message, NOT_JSON);
  held.open();
  assert.equal((await read(await first)).status_code, 1000);
});

// Renewal

test("a PUT with TOKEN_C reads the peer again with the new TOKEN_B and answers a new TOKEN_C", async () => {
  for (const form of ["plain", "base64"]) {
    setup();
    const { tokenC } = await register({ form });
    const before = record();
    peer();
    const response = await put(tokenC);
    assert.equal(response.status, 200);
    const answer = await read(response);
    assert.equal(answer.status_code, 1000);
    const expected = form === "base64" ? btoa(TOKEN_B2) : TOKEN_B2;
    assert.deepEqual(
      calls.map((c) => [c.url, authorization(c)]),
      [
        [VERSIONS_URL, `Token ${expected}`],
        [DETAILS_URL, `Token ${expected}`],
      ],
    );
    const renewed = answer.data.token;
    assert.match(renewed, NEW_TOKEN);
    assert.notEqual(renewed, tokenC);
    assert.deepEqual(answer.data, expectedCredentials(renewed));
    const after = record();
    assert.equal(after.token_b, TOKEN_B2);
    assert.equal(after.token_b_encoding, form);
    assert.equal(after.token_c_sha256, await sha256Hex(renewed));
    assert.equal(after.registered_at, before.registered_at);
    assert.notEqual(after.updated_at, before.updated_at);
    assert.deepEqual(after.retired_token_a_sha256, before.retired_token_a_sha256);
    assert.equal(after.previous_token_c.sha256, await sha256Hex(tokenC));
    assert.equal(after.setup_retry, null);
    assert.deepEqual(handshakeOf(after), { kind: "update", status_code: 1000, message: "Success" });
    assert.deepEqual(after.last_handshake.forms_tried, [form, form]);
    assert.equal((await ask(PATHS.versions, { token: renewed })).status, 200);
  }
});

test("a renewal has no second form", async () => {
  const t = setup();
  const { tokenC } = await register();
  const waits = t.waits.length;
  t.clock.now += 10_000;
  peer({ versions: () => new Response(null, { status: 401 }) });
  const answer = await read(await put(tokenC));
  const message = api("its versions endpoint answered HTTP 401");
  assert.equal(answer.status_code, 3001);
  assert.equal(answer.status_message, message);
  assert.equal(calls.length, 1);
  assert.equal(t.waits.length, waits);
  assert.equal(record().token_b, TOKEN_B);
  assert.deepEqual(handshakeOf(record()), { kind: "update", status_code: 3001, message });
});

test("a failed renewal keeps the old tokens and addresses", async () => {
  setup();
  const { tokenC } = await register();
  const before = record();
  peer({
    versions: () => {
      throw new TypeError("network down");
    },
  });
  const answer = await read(await put(tokenC));
  const message = api("its versions endpoint could not be reached");
  assert.equal(answer.status_code, 3001);
  assert.equal(answer.status_message, message);
  const after = record();
  assert.equal(after.token_c_sha256, before.token_c_sha256);
  assert.equal(after.token_b_encoding, before.token_b_encoding);
  assert.deepEqual(after.peer, before.peer);
  assert.equal(after.handshake, null);
  assert.deepEqual(handshakeOf(after), { kind: "update", status_code: 3001, message });
  assert.equal((await ask(PATHS.versions, { token: tokenC })).status, 200);
  const out = await (await handOut()).json();
  assert.equal(out.token, TOKEN_B);
  assert.equal(out.locations_url, before.peer.locations_url);
  assert.equal(out.tariffs_url, before.peer.tariffs_url);
});

// Unregistration

test("DELETE with TOKEN_C ends the connection without calling the peer", async () => {
  const t = setup();
  const { tokenC } = await register();
  const response = await ask(PATHS.credentials, { method: "DELETE", token: tokenC });
  assert.equal(response.status, 200);
  const answer = await read(response);
  assert.equal(answer.status_code, 1000);
  assert.equal(answer.status_message, "Success");
  assert.equal("data" in answer, false);
  assert.equal(calls.length, 0);
  const saved = record();
  assert.equal(saved.state, "ended");
  for (const field of ["token_b", "token_b_encoding", "token_c_sha256", "previous_token_c", "setup_retry", "peer"]) {
    assert.equal(saved[field], null, field);
  }
  assert.equal(saved.handshake, null);
  assert.equal(saved.ended_at, iso(t.clock.now));
  assert.equal(saved.updated_at, saved.ended_at);
  assert.equal((await ask(PATHS.versions, { token: tokenC })).status, 401);
  const out = await handOut();
  assert.equal(out.status, 200);
  const report = await out.json();
  assert.deepEqual(Object.keys(report), ["state", "ended_at", "handouts", "last_handshake", "last_contact"]);
  assert.equal(report.state, "ended");
  assert.equal(report.ended_at, saved.ended_at);
  assert.deepEqual(handshakeOf(report), { kind: "delete", status_code: 1000, message: "Success" });
  assert.equal("token" in report, false);
});

test("after DELETE only a new setup token can register", async () => {
  const t = setup();
  const { tokenC } = await register();
  await ask(PATHS.credentials, { method: "DELETE", token: tokenC });
  assert.equal((await ask(PATHS.versions)).status, 401);
  assert.equal((await post()).status, 401);
  assert.equal(calls.length, 0);
  t.env.OCPI_TOKEN_A = TOKEN_A2;
  peer();
  const answer = await read(await post({ token: TOKEN_A2 }));
  assert.equal(answer.status_code, 1000);
  const saved = record();
  assert.equal(saved.state, "registered");
  assert.equal(saved.ended_at, null);
  assert.deepEqual(saved.retired_token_a_sha256, [await sha256Hex(TOKEN_A), await sha256Hex(TOKEN_A2)]);
});

test("a new setup token replaces a registration", async () => {
  const t = setup();
  const { tokenC } = await register();
  assert.equal((await ask(PATHS.versions, { token: tokenC })).status, 200);
  const before = record();
  t.clock.now += 60_000;
  t.env.OCPI_TOKEN_A = TOKEN_A2;
  assert.equal((await ask(PATHS.versions, { token: TOKEN_A2 })).status, 200);
  for (const method of ["PUT", "DELETE"]) {
    const body = method === "PUT" ? credentialsBody() : undefined;
    const response = await ask(PATHS.credentials, { method, token: TOKEN_A2, body });
    assert.equal(response.status, 405, method);
    assert.equal(response.headers.get("allow"), "GET, POST");
    assert.equal((await read(response)).status_message, ONLY_POST);
  }
  peer();
  const answer = await read(await post({ token: TOKEN_A2 }));
  assert.equal(answer.status_code, 1000);
  assert.equal((await ask(PATHS.versions, { token: tokenC })).status, 401);
  assert.equal((await ask(PATHS.versions, { token: answer.data.token })).status, 200);
  assert.notEqual(record().registered_at, before.registered_at);
  assert.equal((await ask(PATHS.versions)).status, 401);
});

// Hand-out

test("before registration the hand-out gives no token", async () => {
  setup();
  for (let i = 0; i < 2; i += 1) {
    const response = await handOut();
    assert.equal(response.status, 200);
    assert.match(response.headers.get("content-type"), /^application\/json/);
    assert.equal(response.headers.get("cache-control"), "no-store");
    const report = await response.json();
    assert.deepEqual(Object.keys(report), ["state", "handouts", "last_handshake", "last_contact"]);
    assert.deepEqual(report, {
      state: "unregistered",
      handouts: { count: 0, last_at: null },
      last_handshake: null,
      last_contact: {},
    });
  }
});

test("after registration the hand-out gives TOKEN_B, its form and the data addresses", async () => {
  const t = setup();
  const { tokenC } = await register();
  for (const count of [1, 2]) {
    const response = await handOut();
    assert.equal(response.status, 200);
    assert.equal(response.headers.get("cache-control"), "no-store");
    const text = await response.text();
    const report = JSON.parse(text);
    assert.deepEqual(Object.keys(report), [
      "state",
      "token",
      "token_encoding",
      "version",
      "locations_url",
      "tariffs_url",
      "peer_roles",
      "registered_at",
      "updated_at",
      "handouts",
      "last_handshake",
      "last_contact",
    ]);
    const saved = record();
    assert.deepEqual(report, {
      state: "registered",
      token: TOKEN_B,
      token_encoding: "plain",
      version: "2.2.1",
      locations_url: ENDPOINTS.locations,
      tariffs_url: ENDPOINTS.tariffs,
      peer_roles: saved.peer.roles,
      registered_at: saved.registered_at,
      updated_at: saved.updated_at,
      handouts: { count, last_at: iso(t.clock.now) },
      last_handshake: saved.last_handshake,
      last_contact: saved.last_contact,
    });
    assert.deepEqual(saved.handouts, report.handouts);
    for (const secret of [tokenC, await sha256Hex(tokenC), TOKEN_A, await sha256Hex(TOKEN_A), PULL]) {
      assert.ok(!text.includes(secret));
    }
    t.clock.now += 1000;
  }
});

test("the hand-out shows the owner the peer's attempts", async () => {
  const t = setup();
  await ask(PATHS.versions);
  const firstCall = t.clock.now;
  peer({ details: () => detailsAnswer([endpoint("credentials", "SENDER", ENDPOINTS.credentials)]) });
  assert.equal((await read(await post())).status_code, 3003);
  const report = await (await handOut()).json();
  assert.deepEqual(report.last_handshake, {
    at: iso(t.clock.now),
    kind: "register",
    status_code: 3003,
    message: LACK,
    forms_tried: ["plain", "plain"],
    notes: [],
  });
  assert.deepEqual(report.last_contact["GET /ocpi/versions"], {
    at: iso(firstCall),
    who: "setup",
    form: "plain",
    request_ids: true,
  });
  assert.equal(report.last_contact["POST /ocpi/2.2.1/credentials"].who, "setup");
  await ask(PATHS.versions, { ids: false });
  assert.equal(record().last_contact["GET /ocpi/versions"].request_ids, false);
  const before = stored();
  await ask(PATHS.versions, { ids: false });
  assert.equal(stored(), before);
  t.clock.now += CONTACT_EVERY_MS;
  await ask(PATHS.versions, { ids: false });
  assert.equal(record().last_contact["GET /ocpi/versions"].at, iso(t.clock.now));
  await ask(PATHS.versions, { form: "base64", ids: false });
  assert.equal(record().last_contact["GET /ocpi/versions"].form, "base64");
  await ask(PATHS.credentials, { method: "PATCH" });
  assert.ok(Object.keys(record().last_contact).every((key) => !key.startsWith("PATCH")));
});

test("a call with a used setup token is noted as retired", async () => {
  setup();
  const { tokenC } = await register();
  assert.equal((await ask(PATHS.versions, { token: tokenC })).status, 200);
  assert.equal(record().last_contact["GET /ocpi/versions"].who, "peer");
  assert.equal((await ask(PATHS.versions)).status, 401);
  assert.equal(record().last_contact["GET /ocpi/versions"].who, "retired");
});

// Secrets, logging and errors

test("tokens do not open each other's doors", async () => {
  setup();
  assert.equal((await ask(PATHS.versions, { token: PULL })).status, 401);
  assert.equal((await handOut({ token: TOKEN_A })).status, 403);
  const { tokenC } = await register();
  for (const token of [TOKEN_A, tokenC, TOKEN_B, btoa(TOKEN_B)]) {
    assert.equal((await handOut({ token })).status, 403, token);
  }
  for (const form of ["plain", "base64"]) {
    for (const token of [TOKEN_B, PULL]) {
      for (const path of [PATHS.versions, PATHS.credentials]) {
        assert.equal((await ask(path, { token, form })).status, 401, `${token} ${form} ${path}`);
      }
    }
  }
  assert.equal((await put(TOKEN_B)).status, 401);
  assert.equal(calls.length, 0);
});

// Registers, reads, fails, renews and ends a connection, keeping every answer and every stored
// record on the way, for the two tests below.
async function exposureFlow() {
  const t = setup();
  const snapshots = [];
  const hashes = new Set();
  const step = () => {
    const text = stored();
    if (text === undefined) return;
    snapshots.push(text);
    const saved = JSON.parse(text);
    const found = [saved.token_c_sha256, saved.previous_token_c?.sha256, saved.setup_retry?.sha256];
    for (const hash of [...found, ...saved.retired_token_a_sha256]) if (hash) hashes.add(hash);
  };
  await ask(PATHS.versions);
  step();
  await ask(PATHS.details, { form: "base64" });
  step();
  await ask(PATHS.credentials);
  const echo = t.answered.length - 1;
  step();
  await ask(PATHS.versions, { token: "wrong" });
  await post({ body: "{" });
  step();
  peer({
    versions: () => {
      throw new TypeError("network down");
    },
  });
  await post();
  step();
  const first = (await register()).tokenC;
  step();
  await ask(PATHS.versions, { token: first });
  await ask(PATHS.credentials, { token: first, form: "base64" });
  step();
  await handOut();
  step();
  peer({ versions: () => new Response(null, { status: 503 }) });
  await put(first);
  step();
  const second = (await renew(first)).tokenC;
  step();
  await ask(PATHS.details, { token: second });
  await post({ token: second });
  step();
  await ask(PATHS.credentials, { method: "DELETE", token: second });
  step();
  await handOut();
  return { t, echo, snapshots, hashes, tokens: [first, second] };
}

test("no answer to the peer ever carries TOKEN_B, the pull token or the hashes", async () => {
  const { t, echo, hashes } = await exposureFlow();
  assert.ok(hashes.size >= 3);
  const never = [TOKEN_B, btoa(TOKEN_B), TOKEN_B2, btoa(TOKEN_B2), PULL, btoa(PULL), ...hashes];
  let checked = 0;
  for (const [index, { label, response }] of t.answered.entries()) {
    if (label.endsWith(PATHS.connection)) continue;
    const text = [await response.text(), ...response.headers.values()].join("\n");
    for (const value of never) assert.ok(!text.includes(value), `${label} carries a secret`);
    if (index !== echo) {
      assert.ok(!text.includes(TOKEN_A) && !text.includes(btoa(TOKEN_A)), `${label} carries TOKEN_A`);
    }
    checked += 1;
  }
  assert.ok(checked >= 14);
});

test("storage never holds TOKEN_A, TOKEN_C or the pull token", async () => {
  const { snapshots, tokens } = await exposureFlow();
  assert.ok(snapshots.length >= 10);
  const never = [TOKEN_A, PULL, ...tokens].flatMap((value) => [value, btoa(value)]);
  for (const text of snapshots) {
    for (const value of never) assert.ok(!text.includes(value));
  }
});

test("a storage error before the caller is recognised answers 500 with OCPI 3000 and nothing more", async () => {
  const t = setup();
  t.storage.failAlways = true;
  for (const response of [await ask(PATHS.versions), await post()]) {
    assert.equal(response.status, 500);
    const text = await response.text();
    const answer = JSON.parse(text);
    assert.equal(answer.status_code, 3000);
    assert.equal(answer.status_message, UNEXPECTED);
    assert.equal("data" in answer, false);
    assert.ok(!text.includes("storage failed"));
  }
  assert.equal(calls.length, 0);
});

test("a storage error during a handshake answers 200 with 3000 and frees the flag", async () => {
  const t = setup();
  peer({
    details: () => {
      t.storage.failNext = true;
      return detailsAnswer();
    },
  });
  const response = await post();
  assert.equal(response.status, 200);
  const text = await response.text();
  const answer = JSON.parse(text);
  assert.equal(answer.status_code, 3000);
  assert.equal(answer.status_message, UNEXPECTED);
  assert.ok(!text.includes("storage failed"));
  const saved = record();
  assert.equal(saved.handshake, null);
  assert.equal(saved.state, "unregistered");
  assert.deepEqual(handshakeOf(saved), { kind: "register", status_code: 3000, message: UNEXPECTED });
  // The end of the last call is kept, so a retry at once still waits out the gap.
  assert.equal(saved.last_call_ended_at, t.clock.now);
  assert.deepEqual(t.waits, [GAP_MS]);
  peer();
  assert.equal((await read(await post())).status_code, 1000);
  assert.deepEqual(t.waits, [GAP_MS, GAP_MS, GAP_MS]);
});

test("a storage error while saving a handshake's result still frees the flag", async () => {
  for (const outcome of ["failure", "success"]) {
    const t = setup();
    const failSave = () => {
      t.storage.failNextPut = true;
    };
    const overrides =
      outcome === "failure"
        ? {
            versions: () => {
              failSave();
              return new Response(null, { status: 500 });
            },
          }
        : {
            details: () => {
              failSave();
              return detailsAnswer();
            },
          };
    peer(overrides);
    const response = await post();
    assert.equal(response.status, 200, outcome);
    const answer = await read(response);
    assert.equal(answer.status_code, 3000, outcome);
    assert.equal(answer.status_message, UNEXPECTED);
    const saved = record();
    assert.equal(saved.handshake, null, outcome);
    assert.equal(saved.state, "unregistered");
    assert.equal(saved.token_c_sha256, null);
    assert.equal(saved.last_call_ended_at, t.clock.now);
    assert.deepEqual(handshakeOf(saved), { kind: "register", status_code: 3000, message: UNEXPECTED });
    peer();
    assert.equal((await read(await post())).status_code, 1000, outcome);
  }
});

test("a storage error in the hand-out answers 500 and nothing more", async () => {
  const t = setup();
  t.storage.failAlways = true;
  const response = await handOut();
  assert.equal(response.status, 500);
  assert.equal(response.headers.get("cache-control"), "no-store");
  assert.equal(await response.text(), '{"error":"Unexpected server error."}');
});

test("the object refuses on its own what the front handler refuses", async () => {
  const t = setup();
  const direct = (incoming) => t.instance().fetch(incoming);
  const wrongPull = new Request(`${WORKER}${PATHS.connection}`, { headers: { "x-pull-token": "wrong" } });
  const refused = await direct(wrongPull);
  assert.equal(refused.status, 403);
  assert.deepEqual(await refused.json(), { error: "Not allowed." });
  const posted = await direct(request(PATHS.versions, { method: "POST" }));
  assert.equal(posted.status, 405);
  assert.equal(posted.headers.get("allow"), "GET, HEAD");
  assert.equal((await direct(request("/ocpi/2.2.1/locations"))).status, 404);
  assert.equal((await direct(request(PATHS.versions, { token: null }))).status, 401);
  assert.equal(calls.length, 0);
});

test("the limits fit together", () => {
  assert.ok(GAP_MS >= 2000);
  assert.ok(2 * CALL_TIMEOUT_MS + GAP_MS < HANDSHAKE_BUDGET_MS);
  assert.ok(HANDSHAKE_BUDGET_MS + CALL_TIMEOUT_MS + GAP_MS < HANDSHAKE_EXPIRY_MS);
  for (const grace of [SETUP_RETRY_GRACE_MS, PREVIOUS_TOKEN_GRACE_MS]) {
    assert.ok(grace >= 60_000 && grace <= 900_000, String(grace));
  }
  assert.equal(PARTY.role, "NSP");
  assert.equal(PARTY.country_code, "GB");
  assert.equal(PARTY.name, "OEVM");
  assert.match(PARTY.party_id, /^[A-Z0-9]{3}$/);
  assert.notEqual(PARTY.party_id, "TES");
  assert.match(PARTY.website, /^https:\/\//);
  assert.equal(USER_AGENT, "OEVM/0.1 (+https://github.com/MCRDavid/OEVM)");
});
