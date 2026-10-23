"""One-off check of Monta's UK open data feed with the project's own token. Counts only.

Run in GitHub Actions (.github/workflows/monta-check.yml), where the secrets
MONTA_CLIENT_ID and MONTA_CLIENT_SECRET exist, then removed. It asks whether a token from the
owner's Monta application can read the feed for every UK charger Monta publishes, not just
the owner's own account, and how many locations look like home or private chargers.

Prints counts and OCPI codes only: never a name, address, owner, id, coordinate or key.
Keeps at least 7 seconds between requests (Monta: 10 requests a minute, plus 1 second).
"""

import base64
import json
import os
import re
import sys
import time
from collections import Counter

import httpx

from adapters.http import USER_AGENT
from pipeline.access import private_words
from pipeline.geography import place_in_uk

API = "https://public-api.monta.com/api/v1"
GAP_SECONDS = 7.0
MAX_PAGES = 600
SIZES = (100, 10, 1)
CODE = re.compile(r"[A-Za-z0-9_\-]{1,40}")
SCOPES = {"all", "charge-points", "charge-transactions", "control-charging"}
BUSINESS = re.compile(
    r"\b(ltd|limited|plc|llp|llc|inc|aps|gmbh|council|borough|nhs|trust|university|college|"
    r"school|academy|church|hotel|inn|pub|arms|club|garage|motors?|farm|estate|holdings|"
    r"group|services|company|co\.|centre|center|park|hall|homes|housing|association|"
    r"partnership|society|lodge|cottages?|caravan|leisure|golf|restaurant|cafe|store|"
    r"shop|retail|properties|property|developments?|management|energy|charging|ev)\b",
    re.IGNORECASE,
)
STARTS_WITH_NUMBER = re.compile(r"^\s*\d")

secrets = [os.environ.get("MONTA_CLIENT_ID", ""), os.environ.get("MONTA_CLIENT_SECRET", "")]
last_finished = 0.0


def clean(text: object, limit: int = 200) -> str:
    """text with any secret removed, cut short, for an error message."""
    text = str(text)
    for secret in secrets:
        if secret:
            text = text.replace(secret, "REDACTED")
    return text[:limit]


def code(value: object) -> str:
    """An OCPI code as printed: itself if it looks like a code, otherwise "other"."""
    if value is None:
        return "missing"
    if isinstance(value, bool):
        return str(value).lower()
    if isinstance(value, str) and CODE.fullmatch(value):
        return value
    return "other"


def wait_turn() -> None:
    global last_finished
    pause = last_finished + GAP_SECONDS - time.monotonic()
    if pause > 0:
        time.sleep(pause)


def send(client: httpx.Client, method: str, url: str, **kwargs) -> httpx.Response:
    global last_finished
    wait_turn()
    try:
        return client.request(method, url, **kwargs)
    finally:
        last_finished = time.monotonic()


def error_text(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return clean(response.text)
    if isinstance(body, dict):
        keep = {k: body[k] for k in ("message", "error", "errorCode", "code") if k in body}
        return clean(json.dumps(keep))
    return "not an object"


def main() -> int:
    if not all(secrets):
        print("MONTA_CLIENT_ID or MONTA_CLIENT_SECRET is not set")
        return 1
    summary: dict = {}
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
    with httpx.Client(headers=headers, timeout=60, follow_redirects=False) as client:
        response = send(
            client,
            "POST",
            f"{API}/auth/token",
            json={"clientId": secrets[0], "clientSecret": secrets[1]},
        )
        summary["token_http_status"] = response.status_code
        if response.status_code not in (200, 201):
            summary["token_error"] = error_text(response)
            return report(summary, 1)
        body = response.json()
        token = body.get("accessToken") if isinstance(body, dict) else None
        if not token:
            summary["token_error"] = "no accessToken in the reply"
            return report(summary, 1)
        print(f"::add-mask::{token}")
        secrets.append(token)
        summary["token_reply_fields"] = sorted(body)
        scope = body.get("scope")
        scopes = scope if isinstance(scope, list) else [scope]
        summary["token_scope"] = [s if s in SCOPES else "other" for s in scopes if s]

        counts = {
            name: Counter()
            for name in (
                "country",
                "country_code",
                "party_id",
                "publish",
                "parking_type",
                "parking_restrictions",
                "evse_status",
                "connector_standard",
                "power_type",
                "party_id_of_active_locations",
                "year_last_updated_of_evses_not_removed",
            )
        }
        totals = Counter()
        operators: Counter = Counter()
        after = None
        pages = 0
        complete = False
        rate_headers: dict = {}
        # The first run (22 Oct 2026) got HTTP 500 for per_page 1000 with group_by_location.
        # Try smaller pages, then without grouping, and keep the first that works.
        variants = [
            {"per_page": "100", "group_by_location": "true"},
            {"per_page": "100"},
            {"per_page": "10"},
        ]
        tried = []
        base = None
        for variant in variants:
            response = send(
                client,
                "GET",
                f"{API}/open-data/locations",
                params=variant,
                headers={"Authorization": f"Bearer {token}"},
            )
            entry = {"params": variant, "http_status": response.status_code}
            if response.status_code != 200:
                entry["error"] = error_text(response)
            tried.append(entry)
            if response.status_code == 200:
                base = variant
                break
        summary["first_page_attempts"] = tried
        if base is None:
            return report(summary, 0)
        first = response
        level = streak = 0
        shapes: dict = {}
        cursor_forms: Counter = Counter()
        while pages < MAX_PAGES:
            if pages == 0:
                response = first
                rate_headers = {
                    k: clean(v, 40) for k, v in response.headers.items() if "ratelimit" in k.lower()
                }
            else:
                # Runs 2 and 3 got HTTP 500 part-way, and pages of 10 often worked where
                # pages of 100 failed. Drop to 10, then 1, after a failure; go back up a
                # size after 5 pages that work. A failure at size 1 ends the run.
                while True:
                    params = dict(base, after=after, per_page=str(SIZES[level]))
                    note_cursor(after, totals, cursor_forms)
                    response = send(
                        client,
                        "GET",
                        f"{API}/open-data/locations",
                        params=params,
                        headers={"Authorization": f"Bearer {token}"},
                    )
                    if response.status_code == 200:
                        totals[f"pages_of_{SIZES[level]}_read"] += 1
                        streak += 1
                        break
                    totals[f"http_{response.status_code}_answers_at_size_{SIZES[level]}"] += 1
                    streak = 0
                    if level == len(SIZES) - 1:
                        break
                    level += 1
            if response.status_code != 200:
                summary["stopped_at_page"] = pages + 1
                summary["stop_http_status"] = response.status_code
                summary["stop_error"] = error_text(response)
                break
            pages += 1
            body = response.json()
            records = body.get("data") if isinstance(body, dict) else body
            if not isinstance(records, list):
                summary["stop_error"] = "no list of locations in the reply"
                break
            for location in records:
                count(location, counts, totals, operators)
                if len(shapes) < 20_000:
                    note_shape(location, "", shapes)
            if level and streak >= 5:
                level -= 1
                streak = 0
            meta = body.get("meta", {}) if isinstance(body, dict) else {}
            pagination = meta.get("pagination", {}) if isinstance(meta, dict) else {}
            after = pagination.get("after")
            if not pagination.get("has_more") or not after or not records:
                complete = True
                break
        summary["pages_read"] = pages
        summary["read_to_the_end"] = complete
        summary["rate_limit_headers"] = rate_headers
        summary["totals"] = dict(sorted(totals.items()))
        summary["distinct_operator_names"] = len(operators)
        summary["locations_whose_operator_is_Monta_ApS"] = operators.get("monta aps", 0)
        # Operator names are businesses' names; print only those on 5 or more locations.
        summary["operator_names_on_5_or_more"] = {
            clean(n, 60): c for n, c in operators.most_common() if c >= 5
        }
        summary["counts"] = {name: dict(c.most_common()) for name, c in counts.items()}
        summary["cursor_forms"] = dict(cursor_forms.most_common())
        # Field paths and the kinds of value seen, never the values: to build a made-up
        # fixture in the same shape.
        summary["record_shape"] = {path: sorted(kinds) for path, kinds in sorted(shapes.items())}
    return report(summary, 0)


def note_cursor(after: object, totals: Counter, forms: Counter) -> None:
    """The form of a paging cursor, never its value: length, characters, and, if it is
    base64 for JSON, the JSON's keys and kinds of value."""
    if not isinstance(after, str):
        forms["not text"] += 1
        return
    kind = (
        "digits"
        if after.isdigit()
        else "hex"
        if re.fullmatch(r"[0-9a-fA-F-]+", after)
        else "base64-like"
        if re.fullmatch(r"[A-Za-z0-9+/=_-]+", after)
        else "other"
    )
    form = f"{kind}, {len(after)} characters"
    if kind == "base64-like":
        try:
            padded = after + "=" * (-len(after) % 4)
            decoded = base64.urlsafe_b64decode(padded.replace("+", "-").replace("/", "_"))
            value = json.loads(decoded)
            if isinstance(value, dict):
                form += ", base64 JSON " + ",".join(
                    f"{k}:{type(v).__name__}" for k, v in sorted(value.items())
                )
            else:
                form += f", base64 JSON {type(value).__name__}"
        except (ValueError, UnicodeDecodeError):
            pass
    forms[form] += 1


def note_shape(value: object, path: str, shapes: dict) -> None:
    """Record each field path in value and the kind of value found there."""
    if isinstance(value, dict):
        shapes.setdefault(path or ".", set()).add("object")
        for key, item in value.items():
            name = key if CODE.fullmatch(str(key)) else "other"
            note_shape(item, f"{path}.{name}", shapes)
    elif isinstance(value, list):
        shapes.setdefault(path, set()).add("list" if value else "empty list")
        for item in value:
            note_shape(item, f"{path}[]", shapes)
    else:
        shapes.setdefault(path, set()).add(type(value).__name__)


def count(location: object, counts: dict, totals: Counter, operators: Counter) -> None:
    totals["locations"] += 1
    if not isinstance(location, dict):
        totals["locations_not_objects"] += 1
        return
    for field in ("country", "country_code", "party_id", "publish", "parking_type"):
        counts[field][code(location.get(field))] += 1
    for restriction in location.get("parking_restrictions") or []:
        counts["parking_restrictions"][code(restriction)] += 1
    operator = (location.get("operator") or {}).get("name")
    if isinstance(operator, str):
        operators[operator.strip().lower()] += 1
    published = location.get("publish") is True

    owner = (location.get("owner") or {}).get("name")
    address = " ".join(
        str(location.get(f) or "") for f in ("address", "city", "postal_code")
    ).lower()
    if not isinstance(owner, str) or not owner.strip():
        totals["owner_missing"] += 1
    elif BUSINESS.search(owner):
        totals["owner_business_like"] += 1
    else:
        totals["owner_other"] += 1
        if owner.strip().lower() in address:
            totals["owner_name_part_of_address"] += 1
    name = location.get("name")
    if isinstance(name, str) and STARTS_WITH_NUMBER.match(name):
        totals["name_starts_with_a_number"] += 1
    if isinstance(name, str) and private_words(name):
        totals["name_marks_it_private"] += 1

    coordinates = location.get("coordinates") or {}
    try:
        in_uk = place_in_uk(
            float(coordinates.get("latitude")),
            float(coordinates.get("longitude")),
            location.get("postal_code"),
        )
    except (TypeError, ValueError):
        totals["coordinates_unreadable"] += 1
        in_uk = False
    if in_uk:
        totals["in_uk"] += 1

    evses = location.get("evses") or []
    active = [e for e in evses if isinstance(e, dict) and e.get("status") != "REMOVED"]
    totals["evses"] += len(evses)
    totals["evses_not_removed"] += len(active)
    for evse in active:
        updated = evse.get("last_updated")
        year = updated[:4] if isinstance(updated, str) and updated[:4].isdigit() else None
        counts["year_last_updated_of_evses_not_removed"][code(year)] += 1
    if active:
        totals["locations_with_an_evse_not_removed"] += 1
        counts["party_id_of_active_locations"][code(location.get("party_id"))] += 1
        if published and in_uk:
            totals["mappable_publish_true_in_uk_with_an_evse_not_removed"] += 1
            if not isinstance(owner, str) or not owner.strip():
                totals["mappable_owner_missing"] += 1
            elif BUSINESS.search(owner):
                totals["mappable_owner_business_like"] += 1
            else:
                totals["mappable_owner_other"] += 1
                if owner.strip().lower() in address:
                    totals["mappable_owner_name_part_of_address"] += 1
            if isinstance(name, str) and STARTS_WITH_NUMBER.match(name):
                totals["mappable_name_starts_with_a_number"] += 1
            if isinstance(name, str) and private_words(name):
                totals["mappable_name_marks_it_private"] += 1
            same = isinstance(name, str) and isinstance(owner, str) and owner.strip()
            if same and owner.strip().lower() == name.strip().lower():
                totals["mappable_name_is_the_owner_name"] += 1
            if location.get("parking_type") == "ON_DRIVEWAY":
                totals["mappable_on_driveway"] += 1
    any_tariff_object = False
    for evse in evses:
        if not isinstance(evse, dict):
            continue
        counts["evse_status"][code(evse.get("status"))] += 1
        if evse.get("tariffs"):
            any_tariff_object = True
        for connector in evse.get("connectors") or []:
            if not isinstance(connector, dict):
                continue
            totals["connectors"] += 1
            counts["connector_standard"][code(connector.get("standard"))] += 1
            counts["power_type"][code(connector.get("power_type"))] += 1
            if connector.get("tariff_ids"):
                totals["connectors_naming_a_tariff"] += 1
    if any_tariff_object or location.get("tariffs"):
        totals["locations_with_tariff_objects"] += 1


def report(summary: dict, status: int) -> int:
    text = clean(json.dumps(summary, indent=2, sort_keys=True), limit=100_000)
    print(text)
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if path:
        with open(path, "a", encoding="utf-8") as handle:
            handle.write("## Monta token check (counts only)\n\n```json\n" + text + "\n```\n")
    return status


if __name__ == "__main__":
    sys.exit(main())
