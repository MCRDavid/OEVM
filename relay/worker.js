// OEVM relay, a Cloudflare Worker (see docs/adr/0010-relay-for-refused-feeds.md).
//
// Fetches only the operator feed files listed in ROUTES, on behalf of the daily run,
// whose requests the operator's server refuses. It is not a general proxy:
// - every other path, and every method but GET, is refused;
// - a request must carry the shared token in the X-Relay-Token header (a Worker secret
//   named RELAY_TOKEN, and a GitHub Actions secret on the project's side);
// - the project's own User-Agent is passed on unchanged, so the operator can still see
//   who is asking, and nothing else from the request is forwarded;
// - the answer is passed back as it came, with only the headers OCPI paging needs, and is
//   never cached.
//
// Cloudflare deploys this folder from main through its Git integration (wrangler.toml and
// docs/GITHUB_SETTINGS.md, section 10), so the deployed Worker is always this file.

export const ROUTES = {
  "/geniepoint/locations": "https://opendata.geniepoint.co.uk/locations",
  "/geniepoint/tariffs": "https://opendata.geniepoint.co.uk/tariffs",
};

// Retry-After matters: the daily run waits as long as the operator asks before trying again.
const PASSED_BACK = ["content-type", "x-total-count", "x-limit", "link", "retry-after", "last-modified", "etag"];

function plain(status, text) {
  return new Response(text, { status, headers: { "content-type": "text/plain; charset=utf-8" } });
}

// Compares two strings in time that does not depend on where they first differ.
export function sameToken(given, expected) {
  if (typeof given !== "string" || typeof expected !== "string" || expected === "") return false;
  const a = new TextEncoder().encode(given);
  const b = new TextEncoder().encode(expected);
  let difference = a.length ^ b.length;
  for (let i = 0; i < b.length; i += 1) difference |= (a[i] ?? 0) ^ b[i];
  return difference === 0;
}

export default {
  async fetch(request, env) {
    if (request.method !== "GET") return plain(405, "Only GET is allowed.");
    if (!sameToken(request.headers.get("x-relay-token"), env.RELAY_TOKEN)) {
      return plain(401, "Not allowed.");
    }
    const url = new URL(request.url);
    const target = ROUTES[url.pathname];
    if (!target) return plain(404, "Not a relayed feed.");

    const upstream = new URL(target);
    upstream.search = url.search; // OCPI paging parameters such as offset and limit
    let response;
    try {
      response = await fetch(upstream, {
        method: "GET",
        headers: {
          "user-agent": request.headers.get("user-agent") || "OEVM relay",
          accept: request.headers.get("accept") || "application/json",
        },
        redirect: "manual",
        cf: { cacheTtl: 0, cacheEverything: false },
      });
    } catch {
      return plain(502, "The operator's server could not be reached.");
    }
    const headers = new Headers({ "cache-control": "no-store" });
    for (const name of PASSED_BACK) {
      const value = response.headers.get(name);
      if (value) headers.set(name, value);
    }
    return new Response(response.body, { status: response.status, headers });
  },
};
