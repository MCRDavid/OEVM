"""Temporary, removed before any pull request: Monta's AFIR price endpoints on more UK EVSEs.

Requests a token, reads up to 6 pages of 100 sites from the open data list and picks up to
8 EVSEs that are not REMOVED, from different sites and party ids, sites with inline tariffs
first. Asks GET /api/v1/afir/charge-points/{evseId}/status for each with the evse_id as it
is, and for two of them percent-encoded and without separators too. Then asks the AFIR list
and bulk status endpoints once each with country GB. Prints status codes, id shapes (digits
as 9, letters as A, after the country and party prefix), field names, codes, prices and
rate limit headers only: never an id, name, address or token.
"""

import json
import re
from urllib.parse import quote

from adapters.http import PoliteClient, with_params
from pipeline.registry import load_registry

API = "https://public-api.monta.com/api/v1"
CODE_FIELDS = {
    "currency",
    "applicablecurrency",
    "status",
    "ratepolicy",
    "type",
    "pricetype",
    "unit",
    "dimension",
    "vat",
    "country",
    "code",
    "errorcode",
}
LIMIT_HEADER = re.compile(r"rate|retry|limit", re.IGNORECASE)
SEEN_HEADERS: dict[str, str] = {}


def shape(value: object, depth: int = 0, key: str = "") -> object:
    """Field names and value types, with numbers (prices) and code fields kept."""
    if isinstance(value, dict) and depth < 6:
        return {k: shape(item, depth + 1, k) for k, item in value.items()}
    if isinstance(value, list) and depth < 6:
        if not value:
            return []
        more = ["..."] if len(value) > 1 else []
        return [shape(value[0], depth + 1, key), *more]
    if isinstance(value, bool) or value is None or isinstance(value, int | float):
        return value
    if isinstance(value, str) and key.lower() in CODE_FIELDS and len(value) <= 30:
        return value
    return type(value).__name__


def id_shape(evse_id: str) -> str:
    parts = evse_id.split("*")
    if len(parts) >= 3:
        rest = "*".join(parts[2:])
        return f"{parts[0]}*{parts[1]}*" + re.sub(r"[A-Za-z]", "A", re.sub(r"\d", "9", rest))
    return re.sub(r"[A-Za-z]", "A", re.sub(r"\d", "9", evse_id))


def note_headers(response) -> None:
    for name, value in response.headers.items():
        if LIMIT_HEADER.search(name):
            SEEN_HEADERS[name.lower()] = value


def show(label: str, response, secret: str = "") -> None:
    note_headers(response)
    print(f"{label}: HTTP {response.status_code}")
    try:
        body = response.json()
    except ValueError:
        print("  not JSON")
        return
    if response.status_code != 200 and isinstance(body, dict):
        message = str(body.get("message") or body.get("readableMessage") or "")
        if secret:
            message = message.replace(secret, "<id>")
        print("  error fields:", sorted(body), "| message:", message[:160])
        return
    print(" ", json.dumps(shape(body), indent=2).replace("\n", "\n  "))


def main() -> None:
    config = load_registry()["monta"]
    with PoliteClient(config) as client:
        client.request_token(
            id_field="clientId",
            secret_field="clientSecret",  # pragma: allowlist secret
            token_field="accessToken",
        )
        sites, after = [], None
        for _ in range(6):
            params = {"per_page": "100", "group_by_location": "true"}
            if after is not None:
                params["after"] = str(after)
            page = client.get(with_params(f"{API}/open-data/locations", params))
            note_headers(page)
            if page.status_code != 200:
                print("open data page: HTTP", page.status_code)
                break
            body = page.json()
            sites += body["data"]
            pagination = body["meta"]["pagination"]
            if not pagination.get("has_more"):
                break
            after = pagination["after"]
        print("sites read:", len(sites))
        candidates = []
        for site in sites:
            evses = [e for e in site.get("evses") or [] if e.get("status") != "REMOVED"]
            if not evses or not evses[0].get("evse_id"):
                continue
            has_tariffs = any(e.get("tariffs") for e in evses)
            candidates.append((not has_tariffs, site.get("party_id"), evses[0], has_tariffs))
        candidates.sort(key=lambda c: c[0])
        chosen, parties = [], {}
        for _, party, evse, has_tariffs in candidates:
            if parties.get(party, 0) >= 3:
                continue
            parties[party] = parties.get(party, 0) + 1
            chosen.append((party, evse, has_tariffs))
            if len(chosen) == 8:
                break
        print("sites with an EVSE that is not REMOVED:", len(candidates))
        for n, (party, evse, has_tariffs) in enumerate(chosen, 1):
            evse_id = str(evse["evse_id"])
            print(
                f"\nEVSE {n}: party {party}, id shape {id_shape(evse_id)}, "
                f"status {evse.get('status')}, inline tariffs {has_tariffs}"
            )
            show("  as is", client.get(f"{API}/afir/charge-points/{evse_id}/status"), evse_id)
            if n <= 2:
                show(
                    "  percent-encoded",
                    client.get(f"{API}/afir/charge-points/{quote(evse_id, safe='')}/status"),
                    evse_id,
                )
                bare = evse_id.replace("*", "")
                show(
                    "  without separators",
                    client.get(f"{API}/afir/charge-points/{bare}/status"),
                    bare,
                )
        print()
        show(
            "AFIR list, country GB",
            client.get(with_params(f"{API}/afir/charge-points", {"country": "GB"})),
        )
        show(
            "AFIR bulk status, country GB",
            client.get(with_params(f"{API}/afir/charge-points/status", {"country": "GB"})),
        )
        print("\nrequests made:", client.requests_made)
        print("rate limit headers seen:", SEEN_HEADERS or "none")


if __name__ == "__main__":
    main()
