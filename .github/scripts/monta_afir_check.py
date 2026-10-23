"""Temporary, removed before any pull request: Monta's AFIR price endpoints, control test.

Requests a token, reads the first page of Monta's AFIR list and bulk status endpoints for
country DK, and asks the single-EVSE status endpoint for two Danish EVSE ids found there, as
they are and without separators. Prints status codes, id shapes (digits as 9, letters as A,
after the country and party prefix), field names, codes, prices and rate limit headers only:
never an id, name, address or token.
"""

import json
import re

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


EVSE_ID = re.compile(r"^[A-Z]{2}\*?[A-Z0-9]{3}\*?E[A-Z0-9*]+$")


def evse_ids(value: object, found: list[str]) -> list[str]:
    """Strings shaped like an eMI3 EVSE id, in the order met."""
    if isinstance(value, dict):
        for item in value.values():
            evse_ids(item, found)
    elif isinstance(value, list):
        for item in value:
            evse_ids(item, found)
    elif isinstance(value, str) and EVSE_ID.match(value) and value not in found:
        found.append(value)
    return found


def main() -> None:
    """Control test: does the single-EVSE endpoint answer for Danish EVSEs from Monta's own
    AFIR lists? If it does, the endpoint works and UK EVSEs are outside it."""
    config = load_registry()["monta"]
    with PoliteClient(config) as client:
        client.request_token(
            id_field="clientId",
            secret_field="clientSecret",  # pragma: allowlist secret
            token_field="accessToken",
        )
        ids: list[str] = []
        for label, path in (
            ("AFIR list, country DK", "afir/charge-points"),
            ("AFIR bulk status, country DK", "afir/charge-points/status"),
        ):
            response = client.get(with_params(f"{API}/{path}", {"country": "DK"}))
            note_headers(response)
            print(f"{label}: HTTP {response.status_code}")
            if response.status_code != 200:
                show("  ", response)
                continue
            body = response.json()
            found = evse_ids(body, [])
            print("  top-level fields:", sorted(body) if isinstance(body, dict) else type(body))
            print(
                "  EVSE-id-shaped strings:",
                len(found),
                "shapes:",
                sorted({id_shape(i) for i in found})[:5],
            )
            text = json.dumps(shape(body), indent=2)
            print("  shape (first item of each list):")
            print("  " + "\n  ".join(text.splitlines()[:80]))
            ids += [i for i in found if i not in ids]
        for n, evse_id in enumerate(ids[:2], 1):
            print(f"\nDanish EVSE {n}: id shape {id_shape(evse_id)}")
            show("  as is", client.get(f"{API}/afir/charge-points/{evse_id}/status"), evse_id)
            bare = evse_id.replace("*", "")
            if bare != evse_id:
                show(
                    "  without separators",
                    client.get(f"{API}/afir/charge-points/{bare}/status"),
                    bare,
                )
        print("\nrequests made:", client.requests_made)
        print("rate limit headers seen:", SEEN_HEADERS or "none")


if __name__ == "__main__":
    main()
