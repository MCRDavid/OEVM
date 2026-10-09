// OEVM live status, a Cloudflare Worker for Phase 3 (docs/PHASE3_PLAN.md, ADR 0015).
//
// Groundwork only: not deployed, and the map does not call it yet.
//
// It never reads an operator's feed. The pipeline fetches statuses with the same polite
// client, rate limits and normalisers as the daily run, builds one snapshot per operator
// (pipeline/live_snapshot.py, schema/live.py) and sends it here. This Worker keeps the
// latest snapshot in Workers KV and answers the map's question about one location:
// - PUT /snapshot/<operator>: store a snapshot. Needs the shared token in the
//   X-Live-Token header (a Worker secret named LIVE_TOKEN, and a GitHub Actions secret).
// - GET /snapshot/<operator>: the stored snapshot, with the same token, so the next
//   refresh can lay changes over it.
// - GET /live/<operator>/<location key>: the EVSE statuses of one location and when they
//   were fetched. Open to the map's own address only (SITE_ORIGIN), cached for 60 seconds.
// Nothing about a request is stored or logged, and visitors' requests never reach an
// operator.

export const OPERATORS = ["chargy", "geniepoint", "jolt"];
export const MAX_SNAPSHOT_BYTES = 5 * 1024 * 1024;
export const CACHE_SECONDS = 60;
const KEY = /^[0-9a-f]{16}$/;

function plain(status, text, extra = {}) {
  return new Response(text, { status, headers: { "content-type": "text/plain; charset=utf-8", ...extra } });
}

function json(status, body, extra = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "content-type": "application/json; charset=utf-8", ...extra },
  });
}

// Compares two strings in time that does not depend on where they first differ.
// The same as in relay/worker.js; each Worker is deployed from its own folder.
export function sameToken(given, expected) {
  if (typeof given !== "string" || typeof expected !== "string" || expected === "") return false;
  const a = new TextEncoder().encode(given);
  const b = new TextEncoder().encode(expected);
  let difference = a.length ^ b.length;
  for (let i = 0; i < b.length; i += 1) difference |= (a[i] ?? 0) ^ b[i];
  return difference === 0;
}

// Checks the parts of a snapshot this Worker relies on, without walking every location,
// so a large snapshot stays within the free plan's CPU time. The pipeline validates the
// whole file against schema/live.py before sending it.
export function checkSnapshot(snapshot, operator) {
  if (snapshot === null || typeof snapshot !== "object") return "not a JSON object";
  if (snapshot.schema_version !== 1) return "unknown schema_version";
  if (snapshot.operator !== operator) return "operator does not match the address";
  if (typeof snapshot.fetched_at !== "string" || Number.isNaN(Date.parse(snapshot.fetched_at))) {
    return "fetched_at is not a date";
  }
  if (typeof snapshot.attribution !== "string" || !snapshot.attribution) return "no attribution";
  if (typeof snapshot.licence !== "string" || !snapshot.licence) return "no licence";
  if (snapshot.locations === null || typeof snapshot.locations !== "object") return "no locations";
  return null;
}

// The parsed snapshot for each operator, kept while this Worker instance lives, so most
// requests do not parse the whole snapshot again.
const parsed = new Map();

async function snapshotFor(env, operator) {
  const { value, metadata } = await env.SNAPSHOTS.getWithMetadata(`snapshot:${operator}`, {
    type: "text",
    cacheTtl: CACHE_SECONDS,
  });
  if (value === null) return null;
  const version = metadata?.fetched_at ?? "";
  const kept = parsed.get(operator);
  if (kept && kept.version === version) return kept.snapshot;
  const snapshot = JSON.parse(value);
  parsed.set(operator, { version, snapshot });
  return snapshot;
}

// Every /live/ answer varies by Origin, so a cache never hands an answer made for another
// page (without the CORS header) to the map.
function corsHeaders(env, request) {
  const origin = request.headers.get("origin");
  if (!origin || origin !== env.SITE_ORIGIN) return { vary: "origin" };
  return { "access-control-allow-origin": origin, vary: "origin" };
}

async function live(request, env, operator, key) {
  const cors = corsHeaders(env, request);
  if (!KEY.test(key)) return plain(404, "Not a location key.", cors);
  const snapshot = await snapshotFor(env, operator);
  if (!snapshot) return plain(404, "No snapshot for this operator yet.", cors);
  const evses = snapshot.locations[key];
  if (!evses) return plain(404, "This location is not in the snapshot.", cors);
  return json(
    200,
    {
      operator,
      location_key: key,
      fetched_at: snapshot.fetched_at,
      source: "snapshot",
      attribution: snapshot.attribution,
      licence: snapshot.licence,
      licence_url: snapshot.licence_url ?? null,
      evses,
    },
    { ...cors, "cache-control": `public, max-age=${CACHE_SECONDS}` },
  );
}

async function store(request, env, operator) {
  const length = Number(request.headers.get("content-length") ?? NaN);
  if (!Number.isFinite(length) || length > MAX_SNAPSHOT_BYTES) {
    return plain(413, `A snapshot must state its length and be at most ${MAX_SNAPSHOT_BYTES} bytes.`);
  }
  const text = await request.text();
  if (new TextEncoder().encode(text).length > MAX_SNAPSHOT_BYTES) return plain(413, "Too large.");
  let snapshot;
  try {
    snapshot = JSON.parse(text);
  } catch {
    return plain(400, "Not JSON.");
  }
  const problem = checkSnapshot(snapshot, operator);
  if (problem) return plain(400, `Not a snapshot: ${problem}.`);
  await env.SNAPSHOTS.put(`snapshot:${operator}`, text, { metadata: { fetched_at: snapshot.fetched_at } });
  parsed.delete(operator);
  return new Response(null, { status: 204 });
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    const parts = url.pathname.split("/").filter(Boolean);
    const operator = parts[1];

    if (parts[0] === "live" && parts.length === 3 && OPERATORS.includes(operator)) {
      if (request.method !== "GET") return plain(405, "Only GET is allowed.", { vary: "origin" });
      return live(request, env, operator, parts[2]);
    }

    if (parts[0] === "snapshot" && parts.length === 2 && OPERATORS.includes(operator)) {
      if (!sameToken(request.headers.get("x-live-token"), env.LIVE_TOKEN)) return plain(401, "Not allowed.");
      if (request.method === "PUT") return store(request, env, operator);
      if (request.method === "GET") {
        const text = await env.SNAPSHOTS.get(`snapshot:${operator}`, { type: "text" });
        if (text === null) return plain(404, "No snapshot for this operator yet.");
        return new Response(text, {
          headers: { "content-type": "application/json; charset=utf-8", "cache-control": "no-store" },
        });
      }
      return plain(405, "Only GET and PUT are allowed.");
    }

    return plain(404, "Not found.");
  },
};
