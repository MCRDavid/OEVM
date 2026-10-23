"""Temporary, removed before the pull request: one try of Monta's single-EVSE AFIR endpoint.

Requests a token, reads one page of 10 sites from the open data list, picks the first EVSE
that is not REMOVED, and asks GET /api/v1/afir/charge-points/{evseId}/status for it, once
with the EVSE's evse_id and once with its uid. Prints status codes, field names, value
types and prices only: never an id, name, address or token.
"""

import json
from urllib.parse import quote

from adapters.http import PoliteClient, with_params
from pipeline.registry import load_registry

API = "https://public-api.monta.com/api/v1"


# Strings printed as they are: codes, never ids, names or addresses.
CODE_FIELDS = {"currency", "status", "ratepolicy", "type", "unit", "dimension", "vat"}


def shape(value: object, depth: int = 0, key: str = "") -> object:
    """Field names and value types, with numbers (prices) and code fields kept."""
    if isinstance(value, dict) and depth < 5:
        return {k: shape(item, depth + 1, k) for k, item in value.items()}
    if isinstance(value, list) and depth < 5:
        return [shape(value[0], depth + 1, key)] if value else []
    if isinstance(value, bool) or value is None or isinstance(value, int | float):
        return value
    if isinstance(value, str) and key.lower() in CODE_FIELDS and len(value) <= 20:
        return value
    return type(value).__name__


def main() -> None:
    config = load_registry()["monta"]
    with PoliteClient(config) as client:
        client.request_token(
            id_field="clientId",
            secret_field="clientSecret",  # pragma: allowlist secret
            token_field="accessToken",
        )
        page = client.get(
            with_params(
                f"{API}/open-data/locations", {"per_page": "10", "group_by_location": "true"}
            )
        )
        print("open data page:", page.status_code)
        evse = next(
            e
            for site in page.json()["data"]
            for e in site.get("evses") or []
            if e.get("status") != "REMOVED"
        )
        print("chosen EVSE has evse_id:", bool(evse.get("evse_id")), "uid:", bool(evse.get("uid")))
        for label, value in (("evse_id", evse.get("evse_id")), ("uid", evse.get("uid"))):
            if not value:
                continue
            response = client.get(f"{API}/afir/charge-points/{quote(str(value), safe='')}/status")
            print(f"AFIR status by {label}: HTTP {response.status_code}")
            try:
                body = response.json()
            except ValueError:
                print("  not JSON")
                continue
            print(" ", json.dumps(shape(body), indent=2).replace("\n", "\n  "))


if __name__ == "__main__":
    main()
