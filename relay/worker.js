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
// It also has a timer (ADR 0024): at the times in wrangler.toml ([triggers] crons) it asks
// GitHub to start the Fetch daily workflow, because GitHub's own schedule starts it late or
// not at all when GitHub is busy. The timer only starts the workflow; it never contacts an
// operator. It uses a second Worker secret, GITHUB_DISPATCH_TOKEN: a fine-grained GitHub
// token for this repository only, with Actions read and write and nothing else.
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

// The workflow the timer starts, on main, and the input that tells it the timer started it,
// so it can skip the fetch if today's has already run (pipeline/daily_runs.py).
export const DISPATCH_URL =
  "https://api.github.com/repos/MCRDavid/OEVM/actions/workflows/fetch-daily.yml/dispatches";
export const DISPATCH_BODY = { ref: "main", inputs: { started_by: "timer" } };
// GitHub may be briefly unavailable: try up to three times, a minute apart. A refusal such
// as a wrong or expired token is not retried.
const ATTEMPTS = 3;
const RETRY_AFTER_MS = 60_000;
const RETRIED = new Set([429, 500, 502, 503, 504]);

const wait = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

// Asks GitHub to start Fetch daily. Throws if it could not, so the failure shows in the
// Worker's Cron Events; the message never includes the token.
export async function startDailyFetch(env, { sleep = wait } = {}) {
  const token = env.GITHUB_DISPATCH_TOKEN;
  if (typeof token !== "string" || token === "") {
    throw new Error("GITHUB_DISPATCH_TOKEN is not set, so Fetch daily was not started.");
  }
  let problem = "";
  for (let attempt = 1; attempt <= ATTEMPTS; attempt += 1) {
    if (attempt > 1) await sleep(RETRY_AFTER_MS);
    let response;
    try {
      response = await fetch(DISPATCH_URL, {
        method: "POST",
        headers: {
          accept: "application/vnd.github+json",
          authorization: `Bearer ${token}`,
          "content-type": "application/json",
          "user-agent": "OEVM relay timer (+https://github.com/MCRDavid/OEVM)",
          "x-github-api-version": "2022-11-28",
        },
        body: JSON.stringify(DISPATCH_BODY),
      });
    } catch {
      problem = "GitHub could not be reached";
      continue;
    }
    if (response.ok) return attempt;
    problem = `GitHub answered HTTP ${response.status}`;
    if (!RETRIED.has(response.status)) break;
  }
  throw new Error(`Fetch daily was not started: ${problem}.`);
}

export default {
  // Awaited rather than left to waitUntil, so a failure marks the invocation as failed in
  // the Worker's Cron Events. Waiting between tries uses no CPU time.
  async scheduled(controller, env) {
    await startDailyFetch(env);
  },

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
