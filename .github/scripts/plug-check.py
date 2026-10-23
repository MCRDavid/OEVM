"""One-off check of PLUG Charging's OCPI feed (temporary; removed before the PR is ready).

Reads the versions endpoint, the 2.2.1 version details and one small page each of
locations and tariffs, with the project's polite client and the key from the
PLUG_CHARGING_TOKEN secret. Prints only what the feed sends; never the key.
"""

import json
from collections import Counter

from adapters.http import PoliteClient
from pipeline.registry import OPERATORS_DIR, load_operator_file

config = load_operator_file(OPERATORS_DIR / "plug_charging.yaml")
PAGE_HEADERS = ("content-type", "x-total-count", "x-limit", "link")


def show(response):
    print(f"HTTP {response.status_code} {response.request.url}")
    for name in PAGE_HEADERS:
        if name in response.headers:
            print(f"  {name}: {response.headers[name]}")


with PoliteClient(config) as client:
    versions = client.get(config.endpoints["versions"].url)
    show(versions)
    print(json.dumps(versions.json(), indent=1))
    url = next(v["url"] for v in versions.json()["data"] if v["version"] == "2.2.1")

    details = client.get(url)
    show(details)
    print(json.dumps(details.json(), indent=1))
    modules = {e["identifier"]: e["url"] for e in details.json()["data"]["endpoints"]}

    for module in ("locations", "tariffs"):
        if module not in modules:
            print(f"no {module} module")
            continue
        page = client.get(f"{modules[module]}?offset=0&limit=10")
        show(page)
        body = page.json()
        records = body.get("data") or []
        print(
            f"{module}: {len(records)} records on this page; status_code {body.get('status_code')}"
        )
        if module == "locations":
            print(
                "  country_code/party_id:",
                Counter((r.get("country_code"), r.get("party_id")) for r in records),
            )
            print("  publish:", Counter(r.get("publish") for r in records))
            print("  countries:", Counter(r.get("country") for r in records))
        print(f"----- {module} page start -----")
        print(json.dumps(body))
        print(f"----- {module} page end -----")
