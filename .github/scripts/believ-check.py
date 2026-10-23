"""Temporary: one run of Believ's documented API calls (removed again after the run).

Exactly as Believ's documentation describes: a client_credentials token request to
https://api.believ.com/oauth/token, then one GET of /1.0/evses/{label} with the
documentation's own example label. Both go through PoliteClient with Believ's registry
entry, so they are 865 s apart and never retried. Prints the status, rate limit headers and
the answer's fields; the client id, secret and token are never printed.
"""

import json
import sys
from datetime import UTC, datetime

from adapters.http import FeedError, PoliteClient
from pipeline.registry import load_registry

EVSE_URL = "https://api.believ.com/1.0/evses/A1190"  # the documentation's example label
HEADERS = (
    "content-type",
    "x-ratelimit-limit",
    "x-ratelimit-remaining",
    "x-ratelimit-reset",
    "retry-after",
    "access-control-allow-origin",
    "cache-control",
)
ALL_ERRORS = frozenset(range(400, 600))


def say(text: str) -> None:
    print(f"{datetime.now(UTC):%H:%M:%S} {text}", flush=True)


def main() -> int:
    config = load_registry()["believ"]
    with PoliteClient(config, max_retries=0) as client:
        say(f"gap between requests: {client.min_interval:g} s")
        client_id, secret = client._client_credentials
        body = {"grant_type": "client_credentials", "client_id": client_id, "client_secret": secret}
        try:
            reply = client._request(
                "POST", config.auth.token_url, body=body, return_at_once=ALL_ERRORS
            )
        except FeedError as exc:
            say(f"token request failed: {exc}")
            return 1
        try:
            answer = reply.json()
        except ValueError:
            answer = {}
        if not isinstance(answer, dict):
            answer = {}
        say(f"token request: HTTP {reply.status_code}, fields {sorted(answer)}")
        token = answer.get("access_token")
        if not isinstance(token, str) or not token:
            say("no access token; stopping")
            return 1
        client._secrets = (*client._secrets, token)
        client._client.headers["Authorization"] = f"Bearer {token}"
        say(f"token_type {answer.get('token_type')}, expires_in {answer.get('expires_in')}")
        try:
            response = client.get(EVSE_URL, return_at_once=ALL_ERRORS)
        except FeedError as exc:
            say(f"EVSE request failed: {exc}")
            return 1
        kept = {h: response.headers[h] for h in HEADERS if h in response.headers}
        say(f"EVSE request: HTTP {response.status_code} {kept}")
        try:
            text = json.dumps(client.redact(response.json()), ensure_ascii=False, indent=1)
        except ValueError:
            text = str(client.redact(response.text))
        print(text[:6000], flush=True)
        say(f"done: {client.requests_made} requests")
    return 0


if __name__ == "__main__":
    sys.exit(main())
