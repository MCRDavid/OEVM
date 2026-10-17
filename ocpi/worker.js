// OEVM OCPI handshake, a Cloudflare Worker (see docs/adr/0025-ocpi-handshake-worker.md).
//
// Answers the OCPI 2.2.1 credentials handshake that an operator's server starts by calling
// this project, and keeps that one connection's tokens in a Durable Object. It fetches no
// charger data and is not a proxy:
// - GET (or HEAD) /ocpi/versions and /ocpi/2.2.1 list version 2.2.1 and its credentials
//   endpoint;
// - GET, POST, PUT and DELETE on /ocpi/2.2.1/credentials register, renew and end the
//   connection. Before registering, the operator uses the setup token (a Worker secret named
//   OCPI_TOKEN_A, which the owner pasted into the operator's form); after it, the token this
//   Worker returned, which is kept only as a SHA-256 hash;
// - while a POST or PUT is open, it reads the operator's versions and 2.2.1 details with the
//   operator's token: with the project's User-Agent, 2 seconds apart, never following a
//   redirect, within a time budget, and one handshake at a time;
// - GET /oevm/connection gives the operator's token and its locations and tariffs addresses to
//   the daily run, which fetches them itself, and shows the owner the last handshake and the
//   operator's last calls. It needs the pull token in the X-Pull-Token header (a Worker secret
//   named OCPI_PULL_TOKEN, which the daily run will keep as a GitHub Actions secret).
// Every other path answers 404. Nothing is logged and no answer is cached.
//
// Cloudflare deploys this folder from main through its own Git integration (wrangler.toml and
// docs/GITHUB_SETTINGS.md, section 11), so the deployed Worker is always this file.

import { DurableObject } from "cloudflare:workers";

export const VERSION = "2.2.1";
export const PATHS = {
  versions: "/ocpi/versions",
  details: "/ocpi/2.2.1",
  credentials: "/ocpi/2.2.1/credentials",
  connection: "/oevm/connection",
};
// The project's details in every credentials reply. party_id is what the owner types into the
// operator's form (ADR 0025, D2); never an operator's example such as TES, never initials.
export const PARTY = {
  role: "NSP",
  party_id: "OEV",
  country_code: "GB",
  name: "OEVM",
  website: "https://mcrdavid.github.io/OEVM/",
};
// adapters/http.py USER_AGENT; tests/test_ocpi_worker.py checks they match.
export const USER_AGENT = "OEVM/0.1 (+https://github.com/MCRDavid/OEVM)";
// At least the operator's gap (operators/tesla.yaml rate_limit.min_seconds_between_requests: 2),
// measured from the end of the previous answer, as adapters/http.py does.
export const GAP_MS = 2_000;
// Cloudflare sets no limit on a subrequest, so each call to the other party gets one, covering
// the request and reading the answer.
export const CALL_TIMEOUT_MS = 10_000;
// A handshake that has run this long starts no further call and saves no registration, because
// the other party may have stopped waiting for the answer (needs testing: its timeout is unknown).
export const HANDSHAKE_BUDGET_MS = 25_000;
// Longer than any handshake can run (the budget plus one call and one gap), so only a handshake
// that has stopped, for example in a restart, can be overtaken.
export const HANDSHAKE_EXPIRY_MS = 60_000;
// How long a token whose replacement the other party may never have received still works:
// the setup token after a registration (ADR 0025, D7) and the old token after a renewal.
// Either ends early once the new token has been used.
export const SETUP_RETRY_GRACE_MS = 600_000;
export const PREVIOUS_TOKEN_GRACE_MS = 600_000;
// The operator's last calls are noted for the owner at most this often per route and method.
export const CONTACT_EVERY_MS = 60_000;
export const MAX_BODY_BYTES = 16_384;
export const MAX_PEER_BODY_BYTES = 65_536;
export const OBJECT_NAME = "connection";
export const STORAGE_KEY = "connection";
export const PULL_HEADER = "x-pull-token";
// OCPI suggests 201 for a newly created object. Many implementations answer 200 to everything,
// and whether the operator accepts 201 needs testing (ADR 0025, D5).
export const REGISTERED_HTTP_STATUS = 200;
export const ROLES = ["CPO", "EMSP", "HUB", "NAP", "NSP", "OTHER", "SCSP"];
const MIN_SECRET_LENGTH = 32;
const MAX_TOKEN_LENGTH = 64;
// The Base64 form of a 64-character token, or of one with the spec example's trailing newline.
const MAX_ENCODED_LENGTH = 88;
const MAX_PEER_TOKEN_LENGTH = 255;
const MAX_URL_LENGTH = 255;
const MAX_ROLES = 10;
const CONTACT_METHODS = ["GET", "HEAD", "POST", "PUT", "DELETE"];

const PRINTABLE = /^[\x21-\x7e]+$/;
const TOKEN_HEADER = /^token +(\S+) *$/i;
const BASE64_TEXT = /^[A-Za-z0-9+/_-]+={0,2}$/;
const ID = /^[\x21-\x7e]{1,255}$/;
const IPV4 = /^\d+\.\d+\.\d+\.\d+$/;
const PAGED = { "x-total-count": "1", "x-limit": "1" };

const BUSY = "A credentials handshake is already in progress; try again in a minute.";
const STOPPED = "The handshake took too long and was stopped; try again.";
const LATE = "Could not use the client's API: the handshake took too long, so nothing was changed.";

// The connection's whole state, kept as one JSON string under one key, so every change is one
// write and nothing depends on how the storage API copies objects.
const EMPTY = {
  schema_version: 1,
  state: "unregistered",
  handshake: null,
  token_b: null,
  token_b_encoding: null,
  token_c_sha256: null,
  previous_token_c: null,
  setup_retry: null,
  retired_token_a_sha256: [],
  peer: null,
  registered_at: null,
  updated_at: null,
  ended_at: null,
  last_call_ended_at: null,
  last_handshake: null,
  last_contact: {},
  handouts: { count: 0, last_at: null },
};
const BLANK = JSON.stringify(EMPTY);

// The same as in relay/worker.js; each Worker is deployed from its own folder.
// Compares two strings in time that does not depend on where they first differ.
export function sameToken(given, expected) {
  if (typeof given !== "string" || typeof expected !== "string" || expected === "") return false;
  const a = new TextEncoder().encode(given);
  const b = new TextEncoder().encode(expected);
  let difference = a.length ^ b.length;
  for (let i = 0; i < b.length; i += 1) difference |= (a[i] ?? 0) ^ b[i];
  return difference === 0;
}

// The token in an "Authorization: Token <value>" header, as sent and, when the value is clean
// Base64, as decoded. OCPI 2.2.1 asks for Base64; its own note says many implementations send
// the token as it is, so both are tried, and each is only ever compared with a known token.
export function tokenForms(header) {
  const match = TOKEN_HEADER.exec(header ?? "");
  if (!match) return [];
  const value = match[1];
  const forms = [];
  if (value.length <= MAX_TOKEN_LENGTH && PRINTABLE.test(value)) forms.push({ form: "plain", token: value });
  const decoded = value.length <= MAX_ENCODED_LENGTH ? fromBase64(value) : null;
  if (decoded !== null) forms.push({ form: "base64", token: decoded });
  return forms;
}

// Standard or URL-safe Base64 (RFC 4648 sections 4 and 5), padded correctly or not at all.
// The checks run before atob, which would quietly skip spaces and accept any padding. A trailing
// newline after decoding is dropped, because the spec's own examples encode one.
function fromBase64(value) {
  if (!BASE64_TEXT.test(value)) return null;
  const bare = value.replace(/=+$/, "");
  if (bare.length % 4 === 1) return null;
  const standard = bare.replace(/-/g, "+").replace(/_/g, "/");
  const padded = standard + "=".repeat((4 - (standard.length % 4)) % 4);
  if (value !== bare && value.length !== padded.length) return null;
  try {
    const bytes = Uint8Array.from(atob(padded), (c) => c.charCodeAt(0));
    const token = new TextDecoder("utf-8", { fatal: true }).decode(bytes).replace(/\s+$/, "");
    return token.length <= MAX_TOKEN_LENGTH && PRINTABLE.test(token) ? token : null;
  } catch {
    return null;
  }
}

export async function sha256Hex(text) {
  const digest = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(text));
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

// 32 random bytes as 43 URL-safe Base64 characters: printable, no spaces, under OCPI's 64.
export function newToken() {
  const bytes = crypto.getRandomValues(new Uint8Array(32));
  return btoa(String.fromCharCode(...bytes)).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
const iso = (ms) => new Date(ms).toISOString();
const other = (form) => (form === "base64" ? "plain" : "base64");
const retire = (list, hash) => [...list.filter((h) => h !== hash), hash].slice(-10);
const busy = (record, now) =>
  record.handshake !== null && now - record.handshake.started_at < HANDSHAKE_EXPIRY_MS;

// A dashboard secret counts only if it is a whole token: 32 to 64 printable characters, no spaces.
function setupSecret(value) {
  return (
    typeof value === "string" &&
    value.length >= MIN_SECRET_LENGTH &&
    value.length <= MAX_TOKEN_LENGTH &&
    PRINTABLE.test(value)
  );
}

// Both sides are hashed first, so the comparison runs over a fixed length and the secret's
// length never shows in the timing.
async function pullAllowed(request, env) {
  const given = request.headers.get(PULL_HEADER);
  if (!setupSecret(env.OCPI_PULL_TOKEN) || given === null) return false;
  return sameToken(await sha256Hex(given), await sha256Hex(env.OCPI_PULL_TOKEN));
}

// One trailing slash is ignored: OCPI's own diagrams write version details addresses with one.
function routePath(pathname) {
  return pathname.length > 1 && pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;
}

// OCPI asks every answer to carry the request's X-Request-ID and X-Correlation-ID. A request
// without them (or with unusable ones) gets fresh ids, so the answer can still be traced.
function answerFor(request) {
  const usable = (name) => {
    const value = request.headers.get(name);
    return value !== null && ID.test(value) ? value : null;
  };
  const requestId = usable("x-request-id");
  const correlationId = usable("x-correlation-id");
  return {
    request: requestId ?? crypto.randomUUID(),
    correlation: correlationId ?? crypto.randomUUID(),
    given: requestId !== null && correlationId !== null,
    head: request.method === "HEAD",
  };
}

// The OCPI response format, used for every answer on the OCPI routes, errors included. An
// answer to HEAD has the same status and headers and no body.
function ocpi(ids, httpStatus, statusCode, message, { data, headers = {} } = {}) {
  const body = {
    ...(data === undefined ? {} : { data }),
    status_code: statusCode,
    status_message: message,
    timestamp: new Date().toISOString(),
  };
  return new Response(ids.head ? null : JSON.stringify(body), {
    status: httpStatus,
    headers: {
      "content-type": "application/json",
      "cache-control": "no-store",
      "x-request-id": ids.request,
      "x-correlation-id": ids.correlation,
      ...headers,
    },
  });
}
const refused = (ids) => ocpi(ids, 401, 2000, "Not allowed.", { headers: { "www-authenticate": "Token" } });
const notAllowed = (ids, allow, message) => ocpi(ids, 405, 2000, message, { headers: { allow } });
const usedSetupToken = (ids) =>
  notAllowed(
    ids,
    "GET, PUT, DELETE",
    "Already registered: this setup token has been used. Use the token from the registration reply.",
  );

function json(status, body, headers = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json", "cache-control": "no-store", ...headers },
  });
}

// Reads at most `limit` bytes and stops there, so a large body is never held in memory.
// Returns the bytes, or null when there are more than `limit`.
async function readAtMost(reader, limit) {
  const parts = [];
  let size = 0;
  for (;;) {
    const { done, value } = await reader.read();
    if (done) break;
    size += value.byteLength;
    if (size > limit) {
      await reader.cancel().catch(() => {});
      return null;
    }
    parts.push(value);
  }
  const bytes = new Uint8Array(size);
  let offset = 0;
  for (const part of parts) {
    bytes.set(part, offset);
    offset += part.byteLength;
  }
  return bytes;
}

// An address this Worker will call with the other party's token: https on the default port, a
// named host with a dot (no IP address, no localhost), no user name or password, and at most
// 255 characters. Returns the address, or null.
function usableUrl(value) {
  if (typeof value !== "string" || value.length > MAX_URL_LENGTH) return null;
  let url;
  try {
    url = new URL(value);
  } catch {
    return null;
  }
  const host = url.hostname;
  if (url.protocol !== "https:" || url.username !== "" || url.password !== "" || url.port !== "") return null;
  if (!host.includes(".") || host.startsWith("[") || IPV4.test(host)) return null;
  if (host === "localhost" || host.endsWith(".localhost")) return null;
  return url.href;
}

const short = (value, max) =>
  typeof value === "string" && value.length <= max && PRINTABLE.test(value) ? value : null;
function roleOf(r) {
  const role = short(r?.role, 5);
  return {
    role: ROLES.includes(role) ? role : null,
    party_id: short(r?.party_id, 3),
    country_code: short(r?.country_code, 2),
  };
}

// The other party's Credentials object, checked only where this Worker relies on it (the token
// and the versions address). Unknown fields are ignored, as the operator's documentation asks,
// and a missing or odd roles list is kept as far as it can be.
async function readCredentials(request) {
  const tooLarge = { http: 200, message: "The request body is too large." };
  const notJson = { http: 400, message: "The request body is not valid JSON." };
  if (Number(request.headers.get("content-length") ?? 0) > MAX_BODY_BYTES) return tooLarge;
  let text;
  try {
    const bytes =
      request.body === null ? new Uint8Array(0) : await readAtMost(request.body.getReader(), MAX_BODY_BYTES);
    if (bytes === null) return tooLarge;
    text = new TextDecoder("utf-8", { fatal: true }).decode(bytes);
  } catch {
    return notJson;
  }
  let body;
  try {
    body = JSON.parse(text);
  } catch {
    return notJson;
  }
  if (body === null || typeof body !== "object" || Array.isArray(body)) {
    return { http: 200, message: "The request body must be a Credentials object." };
  }
  const token = body.token;
  if (typeof token !== "string" || token.length > MAX_PEER_TOKEN_LENGTH || !PRINTABLE.test(token)) {
    return { http: 200, message: "token must be 1 to 255 printable characters with no spaces." };
  }
  const url = usableUrl(body.url);
  if (url === null) {
    return {
      http: 200,
      message:
        "url must be an https address on a named host, with no port, user name or password, " +
        "of at most 255 characters.",
    };
  }
  const roles = Array.isArray(body.roles) ? body.roles.slice(0, MAX_ROLES).map(roleOf) : [];
  const notes = [];
  if (token.length > MAX_TOKEN_LENGTH) notes.push("token longer than 64 characters");
  if (roles.length === 0) notes.push("no roles listed");
  return { value: { token, url, roles }, notes };
}

function ourCredentials(origin, token) {
  return {
    token,
    url: `${origin}${PATHS.versions}`,
    roles: [
      {
        role: PARTY.role,
        party_id: PARTY.party_id,
        country_code: PARTY.country_code,
        business_details: { name: PARTY.name, website: PARTY.website },
      },
    ],
  };
}
const versionsList = (origin) => [{ version: VERSION, url: `${origin}${PATHS.details}` }];
const versionDetails = (origin) => ({
  version: VERSION,
  endpoints: [{ identifier: "credentials", role: "SENDER", url: `${origin}${PATHS.credentials}` }],
});

// Who is asking: "peer" (the connected party, with the token this Worker gave it, or for a
// short time the one before), "setup" (with the owner's setup token until a registration
// retires it, or for a short time after), "retired" (with a setup token already used), or null.
function identify(presented, record, setupHash, now) {
  const match = (hash) => presented.find((p) => sameToken(p.hash, hash));
  const open = (grace) => grace !== null && now < grace.until;
  if (record.state === "registered") {
    const current = match(record.token_c_sha256);
    if (current) return { who: "peer", previous: false, ...current };
    const old = open(record.previous_token_c) ? match(record.previous_token_c.sha256) : undefined;
    if (old) return { who: "peer", previous: true, ...old };
    const retry = open(record.setup_retry) ? match(record.setup_retry.sha256) : undefined;
    if (retry) return { who: "setup", retry: true, ...retry };
  }
  if (setupHash !== null && !record.retired_token_a_sha256.some((h) => sameToken(setupHash, h))) {
    const setup = match(setupHash);
    if (setup) return { who: "setup", retry: false, ...setup };
  }
  for (const hash of record.retired_token_a_sha256) {
    const used = match(hash);
    if (used) return { who: "retired", ...used };
  }
  return null;
}

export class OcpiConnection extends DurableObject {
  constructor(ctx, env) {
    super(ctx, env);
    // Replaced in tests, so they need not wait or depend on the clock.
    this.sleep = wait;
    this.now = () => Date.now();
    this.timeoutMs = CALL_TIMEOUT_MS;
  }

  // The synchronous storage API: with no await between reading and writing the record,
  // nothing else can run in between, whatever the runtime does.
  load() {
    const text = this.ctx.storage.kv.get(STORAGE_KEY);
    return { ...JSON.parse(BLANK), ...(typeof text === "string" ? JSON.parse(text) : {}) };
  }

  save(record) {
    this.ctx.storage.kv.put(STORAGE_KEY, JSON.stringify(record));
  }

  async fetch(request) {
    const url = new URL(request.url);
    const path = routePath(url.pathname);
    if (path === PATHS.connection) return this.handOut(request);
    const job = { ids: answerFor(request), origin: `https://${url.host}`, caller: null, held: null };
    try {
      return await this.ocpiRoute(request, path, job);
    } catch {
      // Nothing about the error is logged or returned. A caller that has been recognised gets
      // HTTP 200, as OCPI asks for every authenticated request.
      if (job.held !== null) this.release(job.held);
      return ocpi(job.ids, job.caller === null ? 500 : 200, 3000, "Unexpected server error.");
    }
  }

  async ocpiRoute(request, path, job) {
    const { ids, origin } = job;
    const method = request.method;
    // Hashing is the only wait before the record is read; from then on, nothing but storage is
    // touched until this request has been answered or has stored its handshake flag.
    const presented = await Promise.all(
      tokenForms(request.headers.get("authorization")).map(async (f) => ({
        ...f,
        hash: await sha256Hex(f.token),
      })),
    );
    const setupHash = setupSecret(this.env.OCPI_TOKEN_A) ? await sha256Hex(this.env.OCPI_TOKEN_A) : null;
    const record = this.load();
    const caller = identify(presented, record, setupHash, this.now());
    if (caller === null) return refused(ids);
    job.caller = caller;
    this.noteContact(record, caller, method, path, ids);
    if (caller.who === "retired") {
      const used = path === PATHS.credentials && method === "POST" && record.state === "registered";
      return used ? usedSetupToken(ids) : refused(ids);
    }
    if (path === PATHS.versions || path === PATHS.details) {
      if (method !== "GET" && method !== "HEAD") {
        return notAllowed(ids, "GET, HEAD", "Only GET and HEAD are allowed.");
      }
      return path === PATHS.versions
        ? ocpi(ids, 200, 1000, "Success", { data: versionsList(origin), headers: PAGED })
        : ocpi(ids, 200, 1000, "Success", { data: versionDetails(origin) });
    }
    if (path !== PATHS.credentials) return ocpi(ids, 404, 2000, "Not found.");
    return this.credentials(request, job, presented, setupHash);
  }

  async credentials(request, job, presented, setupHash) {
    const { ids, origin } = job;
    const method = request.method;
    const peer = job.caller.who === "peer";
    if (method === "GET") {
      return ocpi(ids, 200, 1000, "Success", { data: ourCredentials(origin, job.caller.token) });
    }
    if (method === "POST" && peer) {
      return notAllowed(
        ids,
        "GET, PUT, DELETE",
        "Already registered: use PUT to update the credentials or DELETE to end the connection.",
      );
    }
    if ((method === "PUT" || method === "DELETE") && !peer) {
      return notAllowed(ids, "GET, POST", "This token can only register: use POST.");
    }
    if (method === "DELETE") return this.unregister(job);
    if (method !== "POST" && method !== "PUT") {
      return notAllowed(ids, peer ? "GET, PUT, DELETE" : "GET, POST", "This method is not allowed here.");
    }
    const body = await readCredentials(request);
    // Other requests may have run while the body arrived, so the record is read and the caller
    // recognised again before anything is decided.
    const record = this.load();
    const again = identify(presented, record, setupHash, this.now());
    if (again?.who !== job.caller.who) {
      return again?.who === "retired" && record.state === "registered" ? usedSetupToken(ids) : refused(ids);
    }
    job.caller = again;
    const kind = method === "POST" ? "register" : "update";
    if (body.http === 400) return this.refuseBody(job, kind, 400, body.message);
    if (busy(record, this.now())) return ocpi(ids, 200, 3000, BUSY);
    if (body.value === undefined) return this.refuseBody(job, kind, 200, body.message);
    return this.handshake(kind, request, job, record, body);
  }

  refuseBody(job, kind, httpStatus, message) {
    const record = this.load();
    const outcome = { at: iso(this.now()), kind, status_code: 2001, message, forms_tried: [], notes: [] };
    this.save({ ...record, last_handshake: outcome });
    return ocpi(job.ids, httpStatus, 2001, message);
  }

  async handshake(kind, request, job, record, body) {
    const startedAt = this.now();
    const id = crypto.randomUUID();
    // W1. Cloudflare's output gate should hold the first call to the other party until this is
    // stored (needs checking for the synchronous API).
    this.save({ ...record, handshake: { id, kind, started_at: startedAt } });
    job.held = { id, kind };
    const forms = kind === "register" ? [job.caller.form, other(job.caller.form)] : [record.token_b_encoding];
    const result = await this.readPeer({
      id,
      startedAt,
      token: body.value.token,
      url: body.value.url,
      forms,
      lastCallEndedAt: record.last_call_ended_at,
      correlation: job.ids.correlation,
      signal: request.signal,
    });
    if (result.stopped) {
      job.held = null;
      return ocpi(job.ids, 200, 3000, STOPPED);
    }
    const outcome =
      result.status_code === 1000 && this.late(request.signal, startedAt)
        ? { ...result, status_code: 3001, message: LATE }
        : result;
    // Made before the record is read again, so nothing but storage runs from that read to the write.
    const token = outcome.status_code === 1000 ? newToken() : null;
    const tokenHash = token === null ? null : await sha256Hex(token);
    const fresh = this.load();
    if (fresh.handshake?.id !== id) {
      job.held = null;
      return ocpi(job.ids, 200, 3000, STOPPED);
    }
    const now = this.now();
    const at = iso(now);
    const lastHandshake = {
      at,
      kind,
      status_code: outcome.status_code,
      message: outcome.message,
      forms_tried: outcome.forms_tried,
      notes: [...body.notes, ...(outcome.notes ?? [])],
    };
    const common = {
      ...fresh,
      handshake: null,
      last_call_ended_at: outcome.lastCallEndedAt,
      last_handshake: lastHandshake,
    };
    job.held = null;
    if (outcome.status_code !== 1000) {
      this.save(common); // W4
      return ocpi(job.ids, 200, outcome.status_code, outcome.message);
    }
    const connection = {
      token_b: body.value.token,
      token_b_encoding: outcome.encoding,
      token_c_sha256: tokenHash,
      peer: { ...outcome.peer, roles: body.value.roles },
      updated_at: at,
    };
    if (kind === "register") {
      // W2
      this.save({
        ...common,
        ...connection,
        state: "registered",
        previous_token_c: null,
        setup_retry: { sha256: job.caller.hash, until: now + SETUP_RETRY_GRACE_MS },
        retired_token_a_sha256: retire(fresh.retired_token_a_sha256, job.caller.hash),
        registered_at: at,
        ended_at: null,
      });
    } else {
      // W3
      this.save({
        ...common,
        ...connection,
        previous_token_c: { sha256: job.caller.hash, until: now + PREVIOUS_TOKEN_GRACE_MS },
        setup_retry: null,
      });
    }
    const httpStatus = kind === "register" ? REGISTERED_HTTP_STATUS : 200;
    return ocpi(job.ids, httpStatus, 1000, "Success", { data: ourCredentials(job.origin, token) });
  }

  // Whether the caller may no longer receive the answer: it has hung up (where the runtime
  // tells this Worker), or the handshake has used up its time budget.
  late(signal, startedAt) {
    return signal?.aborted === true || this.now() - startedAt > HANDSHAKE_BUDGET_MS;
  }

  async readPeer({ id, startedAt, token, url, forms, lastCallEndedAt, correlation, signal }) {
    let ended = lastCallEndedAt;
    const tried = [];
    // Waits out the gap since this Worker's last answer from the other party, then checks that
    // this handshake still holds the flag and is within its budget, so an overtaken or late
    // handshake never calls again.
    const call = async (target, form) => {
      if (ended !== null) {
        const ms = ended + GAP_MS - this.now();
        if (ms > 0) await this.sleep(ms);
      }
      if (this.load().handshake?.id !== id) return { stopped: true };
      if (this.late(signal, startedAt)) return { late: true };
      tried.push(form);
      try {
        return await this.callPeer(target, token, form, correlation);
      } finally {
        ended = this.now();
      }
    };
    // On a registration, the first call refused with 401 or 403 is tried once more in the
    // other form, and that form is used from then on.
    let form = forms[0];
    let canSwitch = forms.length > 1;
    const get = async (target) => {
      let answer = await call(target, form);
      if (canSwitch && (answer.httpStatus === 401 || answer.httpStatus === 403)) {
        canSwitch = false;
        form = forms[1];
        answer = await call(target, form);
      }
      return answer;
    };
    const done = (statusCode, message, extra = {}) => ({
      status_code: statusCode,
      message,
      lastCallEndedAt: ended,
      forms_tried: tried,
      ...extra,
    });
    const api = (text) => `Could not use the client's API: ${text}.`;

    const versions = await get(url);
    if (versions.stopped) return versions;
    if (versions.late) return done(3001, LATE);
    if (versions.problem) return done(3001, api(`its versions endpoint ${versions.problem}`));
    if (!Array.isArray(versions.data)) {
      const data = versions.data;
      const details = data !== null && typeof data === "object" && "endpoints" in data;
      const what = details
        ? "the url given is a version details address, not a versions address"
        : "its versions endpoint did not answer with a list of versions";
      return done(3001, api(what));
    }
    const listed = versions.data.find((v) => v?.version === VERSION);
    if (!listed) return done(3002, "The client's versions list has no version 2.2.1.");
    const detailsUrl = usableUrl(listed.url);
    if (!detailsUrl) {
      return done(3001, api("its address for version 2.2.1 is not an https address this Worker will use"));
    }

    const details = await get(detailsUrl);
    if (details.stopped) return details;
    if (details.late) return done(3001, LATE);
    if (details.problem) return done(3001, api(`its 2.2.1 details endpoint ${details.problem}`));
    const data = details.data;
    if (data?.version !== VERSION || !Array.isArray(data.endpoints)) {
      return done(3001, api("its version details are not for version 2.2.1"));
    }
    // The first entry for a module (and role, where given) with an address this Worker will use;
    // "unusable" if there are entries but none has one; null if there are none.
    const find = (identifier, role) => {
      const entries = data.endpoints.filter(
        (e) => e?.identifier === identifier && (role === undefined || e.role === role),
      );
      if (entries.length === 0) return null;
      for (const e of entries) {
        const target = usableUrl(e.url);
        if (target) return target;
      }
      return "unusable";
    };
    const locations = find("locations", "SENDER");
    if (locations === null) return done(3003, "The client's 2.2.1 endpoints lack: locations (SENDER).");
    if (locations === "unusable") {
      return done(
        3003,
        "The client's 2.2.1 endpoints give no address this Worker will use for: locations (SENDER).",
      );
    }
    // Only locations is required. The credentials entry's role "has no function" in OCPI 2.2.1.
    const tariffs = find("tariffs", "SENDER");
    const credentials = find("credentials");
    const notes = [];
    if (tariffs === null) notes.push("no tariffs endpoint");
    if (tariffs === "unusable") notes.push("tariffs endpoint address not usable");
    if (credentials === null) notes.push("no credentials endpoint");
    if (credentials === "unusable") notes.push("credentials endpoint address not usable");
    const kept = (found) => (found === null || found === "unusable" ? null : found);
    return done(1000, "Success", {
      encoding: form,
      notes,
      peer: {
        versions_url: url,
        version: VERSION,
        details_url: detailsUrl,
        credentials_url: kept(credentials),
        locations_url: locations,
        tariffs_url: kept(tariffs),
      },
    });
  }

  // One GET to the other party, built fresh: none of its own request's headers are passed on,
  // no redirect is followed (a redirect would carry the Authorization header to another host),
  // and one timer ends both the request and the reading of the answer.
  async callPeer(target, token, form, correlation) {
    const controller = new AbortController();
    let reader = null;
    const timer = setTimeout(() => {
      controller.abort();
      reader?.cancel().catch(() => {});
    }, this.timeoutMs);
    const failed = () => ({
      problem: controller.signal.aborted ? "did not answer in time" : "could not be reached",
    });
    try {
      let response;
      try {
        response = await fetch(target, {
          method: "GET",
          headers: {
            accept: "application/json",
            authorization: `Token ${form === "base64" ? btoa(token) : token}`,
            "user-agent": USER_AGENT,
            "x-correlation-id": correlation,
            "x-request-id": crypto.randomUUID(),
          },
          redirect: "manual",
          signal: controller.signal,
          cf: { cacheTtl: 0, cacheEverything: false },
        });
      } catch {
        return failed();
      }
      const httpStatus = response.status;
      const discard = () => response.body?.cancel().catch(() => {});
      if (httpStatus >= 300 && httpStatus < 400) {
        discard();
        return { httpStatus, problem: "answered with a redirect, which is not followed" };
      }
      if (httpStatus < 200 || httpStatus >= 300) {
        discard();
        return { httpStatus, problem: `answered HTTP ${httpStatus}` };
      }
      if (Number(response.headers.get("content-length") ?? 0) > MAX_PEER_BODY_BYTES) {
        discard();
        return { httpStatus, problem: "gave too large an answer" };
      }
      let bytes;
      try {
        reader = response.body === null ? null : response.body.getReader();
        bytes = reader === null ? new Uint8Array(0) : await readAtMost(reader, MAX_PEER_BODY_BYTES);
      } catch {
        return { httpStatus, ...failed() };
      }
      // A read stopped by the timer ends as if the answer were complete, so the timer comes first.
      if (controller.signal.aborted) return { httpStatus, problem: "did not answer in time" };
      if (bytes === null) return { httpStatus, problem: "gave too large an answer" };
      let body;
      try {
        body = JSON.parse(new TextDecoder("utf-8", { fatal: true }).decode(bytes));
      } catch {
        return { httpStatus, problem: "did not answer with JSON" };
      }
      if (body === null || typeof body !== "object" || typeof body.status_code !== "number") {
        return { httpStatus, problem: "did not answer with an OCPI response" };
      }
      if (body.status_code !== 1000) return { httpStatus, problem: `answered OCPI status ${body.status_code}` };
      return { httpStatus, data: body.data };
    } finally {
      clearTimeout(timer);
    }
  }

  unregister(job) {
    const record = this.load();
    if (busy(record, this.now())) return ocpi(job.ids, 200, 3000, BUSY);
    const at = iso(this.now());
    // W5. No call to the other party: "Both parties must end any automated communication."
    this.save({
      ...record,
      state: "ended",
      handshake: null,
      token_b: null,
      token_b_encoding: null,
      token_c_sha256: null,
      previous_token_c: null,
      setup_retry: null,
      peer: null,
      ended_at: at,
      updated_at: at,
      last_handshake: { at, kind: "delete", status_code: 1000, message: "Success", forms_tried: [], notes: [] },
    });
    return ocpi(job.ids, 200, 1000, "Success");
  }

  // W0. Notes the operator's call for the owner (at most once a minute per route and method,
  // unless who, form or ids changed), and ends a grace period once the new token has been used.
  noteContact(record, caller, method, path, ids) {
    const now = this.now();
    const next = { ...record, last_contact: { ...record.last_contact } };
    let changed = false;
    const grace = record.previous_token_c !== null || record.setup_retry !== null;
    if (caller.who === "peer" && !caller.previous && grace) {
      next.previous_token_c = null;
      next.setup_retry = null;
      changed = true;
    }
    if (CONTACT_METHODS.includes(method)) {
      const key = `${method} ${path}`;
      const seen = { who: caller.who, form: caller.form, request_ids: ids.given };
      const last = record.last_contact[key];
      const same =
        last !== undefined &&
        last.who === seen.who &&
        last.form === seen.form &&
        last.request_ids === seen.request_ids;
      if (!same || now - Date.parse(last.at) >= CONTACT_EVERY_MS) {
        next.last_contact[key] = { at: iso(now), ...seen };
        changed = true;
      }
    }
    if (changed) this.save(next);
  }

  // After an unexpected error, clears this request's handshake flag if it still holds it.
  release({ id, kind }) {
    try {
      const fresh = this.load();
      if (fresh.handshake?.id === id) {
        const message = "Unexpected server error.";
        const outcome = { at: iso(this.now()), kind, status_code: 3000, message, forms_tried: [], notes: [] };
        this.save({ ...fresh, handshake: null, last_handshake: outcome });
      }
    } catch {
      // The flag lapses by itself after HANDSHAKE_EXPIRY_MS.
    }
  }

  async handOut(request) {
    try {
      if (!(await pullAllowed(request, this.env))) return json(403, { error: "Not allowed." });
      const record = this.load();
      const now = this.now();
      const report = { last_handshake: record.last_handshake, last_contact: record.last_contact };
      if (busy(record, now)) {
        const seconds = Math.max(1, Math.ceil((record.handshake.started_at + HANDSHAKE_EXPIRY_MS - now) / 1000));
        return json(
          409,
          { state: "handshake_in_progress", retry_after_seconds: seconds, handouts: record.handouts, ...report },
          { "retry-after": String(seconds) },
        );
      }
      if (record.state === "ended") {
        return json(200, { state: "ended", ended_at: record.ended_at, handouts: record.handouts, ...report });
      }
      if (record.state !== "registered") {
        return json(200, { state: "unregistered", handouts: record.handouts, ...report });
      }
      const handouts = { count: record.handouts.count + 1, last_at: iso(now) };
      this.save({ ...record, handouts }); // W7
      return json(200, {
        state: "registered",
        token: record.token_b,
        token_encoding: record.token_b_encoding,
        version: record.peer.version,
        locations_url: record.peer.locations_url,
        tariffs_url: record.peer.tariffs_url,
        peer_roles: record.peer.roles,
        registered_at: record.registered_at,
        updated_at: record.updated_at,
        handouts,
        ...report,
      });
    } catch {
      return json(500, { error: "Unexpected server error." });
    }
  }
}

// The one object that holds the connection, found by its neutral name.
function connection(env) {
  return env.CONNECTION.get(env.CONNECTION.idFromName(OBJECT_NAME));
}

export default {
  // Refuses what needs no stored state here, so stray requests do not use the free plan's
  // Durable Object requests; everything else goes to the one object.
  async fetch(request, env) {
    const url = new URL(request.url);
    const path = routePath(url.pathname);
    const ids = answerFor(request);
    if (path === PATHS.connection) {
      if (request.method !== "GET") return json(405, { error: "Only GET is allowed." }, { allow: "GET" });
      if (!(await pullAllowed(request, env))) return json(403, { error: "Not allowed." });
      return connection(env).fetch(request);
    }
    if (path === PATHS.versions || path === PATHS.details) {
      if (request.method !== "GET" && request.method !== "HEAD") {
        return notAllowed(ids, "GET, HEAD", "Only GET and HEAD are allowed.");
      }
    } else if (path !== PATHS.credentials) {
      return ocpi(ids, 404, 2000, "Not found.");
    }
    if (tokenForms(request.headers.get("authorization")).length === 0) return refused(ids);
    return connection(env).fetch(request);
  },
};
