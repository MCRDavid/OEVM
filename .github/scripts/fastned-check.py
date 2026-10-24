"""One-off check of Fastned's UK Open Data API (temporary; removed before the PR is ready).

Reads the locations endpoint once with the project's polite client and the key from the
FASTNED_API_KEY secret, and prints every response header and a summary of the body. Prints
only what the feed sends; never the key.
"""

from collections import Counter

from adapters.http import PoliteClient
from pipeline.registry import OPERATORS_DIR, load_operator_file

config = load_operator_file(OPERATORS_DIR / "fastned.yaml")

with PoliteClient(config) as client:
    response = client.get(config.endpoints["locations"].url)
    print(f"HTTP {response.status_code} {response.request.url}")
    for name, value in response.headers.items():
        print(f"  {name}: {value}")
    body = response.json()
    if isinstance(body, dict):
        records = body.get("data") or []
        print("top-level keys:", list(body))
        print("status_code:", body.get("status_code"), body.get("status_message"))
    else:
        records = body
        print("top-level type:", type(body).__name__)
    print("records on this page:", len(records))
    parties = Counter((r.get("country_code"), r.get("party_id")) for r in records)
    print("country_code/party_id:", parties)
    print("publish:", Counter(r.get("publish") for r in records))
    print("countries:", Counter(r.get("country") for r in records))
