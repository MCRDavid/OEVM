"""Zest's data, a copy it sent by email, read by the sent_copy adapter (ADR 0029).

The adapter's general rules (no request, dated as made, statuses unknown, a file that is
not an OCPI response stops the run) are tested with Connekt's copy in test_connekt.py.
These tests cover what is particular to Zest's copy.
"""

import gzip
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx

from pipeline import publish, run
from pipeline.health import in_uk
from pipeline.pricing import describe_tariff
from pipeline.registry import ROOT, load_registry
from schema.operator import OperatorConfig

FIXTURES = Path(__file__).parent / "fixtures" / "zest"
MADE_AT = datetime(2026, 10, 26, 10, 29, 56, tzinfo=UTC)
WHEN = datetime(2026, 10, 30, 4, 17, tzinfo=UTC)


class NoRequests(httpx.BaseTransport):
    """Fails the test if anything tries to reach a network."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"a sent copy made a request to {request.url}")


def fixture_config() -> OperatorConfig:
    """Zest's registry entry, reading the trimmed fixture as run.run_fixtures does."""
    config = load_registry()["zest"]
    files = {
        "locations": "tests/fixtures/zest/locations.json",
        "tariffs": "tests/fixtures/zest/tariffs.json",
    }
    return config.model_copy(update={"sent_copy": config.sent_copy.model_copy(update=files)})


def read():
    return run.run_operator(fixture_config(), transport=NoRequests(), sleep=lambda _s: 0)


def raw_records(module: str) -> list[dict]:
    return json.loads((FIXTURES / f"{module}.json").read_text(encoding="utf-8"))["data"]


def test_the_copy_is_read_without_any_request_and_dated_as_made():
    result = read()
    assert result.requests == 0
    assert result.fetched_at == MADE_AT
    assert result.issues == [
        "duplicate location record; kept the last copy (4 times)",
        "Read from a copy the operator sent on 2026-10-28, made 2026-10-26 10:29 UTC; no "
        "request was made.",
        "19 charge point statuses in the copy shown as unknown.",
    ]
    for record in [*result.locations, *result.tariffs]:
        assert record.provenance.fetched_at == MADE_AT
        assert record.provenance.method == "operator_static_file"
        assert record.provenance.licence == "CC-BY-4.0"


def test_a_location_sent_twice_keeps_its_later_record():
    sent = Counter(loc["id"] for loc in raw_records("locations"))
    assert {i for i, n in sent.items() if n == 2} == {"1358", "1660", "1918", "1987"}
    pairs = {}
    for loc in raw_records("locations"):
        pairs.setdefault(loc["id"], []).append(loc["last_updated"])
    locations = {loc.id.rsplit(":", 1)[1]: loc for loc in read().locations}
    assert len(locations) == 9
    for location_id in ("1358", "1660", "1918", "1987"):
        first, later = pairs[location_id]
        assert later > first
        kept = locations[location_id].last_updated
        assert kept.isoformat().replace("+00:00", ".000Z") == later


def test_every_charge_point_status_is_unknown_whatever_the_copy_says():
    sent = Counter(e["status"] for loc in raw_records("locations") for e in loc["evses"])
    assert {"AVAILABLE", "CHARGING", "OUTOFORDER", "INOPERATIVE", "UNKNOWN"} == set(sent)
    evses = [e for loc in read().locations for e in loc.evses]
    assert {(e.status, e.status_at) for e in evses} == {("unknown", None)}


def test_prices_follow_the_data_including_the_idle_fee_zest_describes_per_minute():
    tariffs = {t.id: t for t in read().tariffs}
    # Tariff 530: 0.49 per kWh and an idle fee of 0.08 per hour before VAT, VAT stated as 20.
    # Its own text says "£0.10/min"; the price follows the data, as OCPI defines it.
    assert describe_tariff(tariffs["zest:GB:ZST:530"]).text == (
        "58.8p per kWh from 08:00 to 23:00, 58.8p per kWh from 23:00 to 08:00; plus £0.10 per "
        "hour parked from 08:00 to 23:00 after 4 hours including VAT; minimum charge £0.33 "
        "excluding VAT"
    )
    # Tariff 428 sends min_price 0, so no minimum charge is shown.
    assert describe_tariff(tariffs["zest:GB:ZST:428"]).text == "55.2p per kWh including VAT"


def received_hashes() -> dict[str, str]:
    """The SHA-256 of each file as received, before gzip, from the copy's README table."""
    readme = (ROOT / "sent_copies" / "zest" / "README.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| `2026-10-28-(\w+)\.json\.gz` \|.*\| `([0-9a-f]{64})` \|$", readme, re.M)
    return dict(rows)


def test_the_files_kept_are_exactly_the_ones_zest_sent():
    copy = load_registry()["zest"].sent_copy
    assert copy.made_at == MADE_AT and copy.received.isoformat() == "2026-10-28"
    received = received_hashes()
    assert set(received) == {"locations", "tariffs"}
    stamps = {}
    for module in ("locations", "tariffs"):
        blob = gzip.decompress((ROOT / getattr(copy, module)).read_bytes())
        assert hashlib.sha256(blob).hexdigest() == received[module]
        body = json.loads(blob)
        assert body["status_code"] == 1000
        stamps[module] = datetime.fromisoformat(body["timestamp"].replace("Z", "+00:00"))
    # made_at is the locations response's own timestamp, to the second.
    assert stamps["locations"].replace(microsecond=0) == MADE_AT
    assert stamps["tariffs"] < stamps["locations"]


def test_the_whole_copy_maps_every_location_in_the_uk():
    config = load_registry()["zest"]
    result = run.run_operator(config, transport=NoRequests(), sleep=lambda _s: 0)
    assert len(result.locations) == 1963 and len(result.tariffs) == 67
    assert {tuple(loc.id.split(":")[1:3]) for loc in result.locations} == {("GB", "ZST")}
    assert all(e.status == "unknown" for loc in result.locations for e in loc.evses)
    assert all(in_uk(loc) for loc in result.locations)


def test_the_map_says_it_is_a_copy_and_shows_tariff_text_without_tags(tmp_path):
    published = publish.publish([read()], load_registry(), tmp_path, mode="live", generated_at=WHEN)
    entry = published.manifest.operators["zest"]
    assert entry.fetched_at == MADE_AT and entry.mapped == 9
    assert (
        entry.attribution
        == "Contains data from Zest, licensed under CC BY 4.0. Adapted from Zest's data."
    )
    assert entry.sent_copy.note == (
        "Zest sent this data by email on 28 October 2026, in files made on 26 October 2026 "
        "at 10:29 UTC. This map shows that copy as sent, by the repository owner's decision "
        "of 29 October 2026, while no address to fetch Zest's data from is known. It is not "
        "updated, so details and prices may have changed since, and charge point status is "
        "not shown."
    )
    layer = json.loads((tmp_path / "data" / "locations.geojson").read_text(encoding="utf-8"))
    options = []
    for feature in layer["features"]:
        key = feature["properties"]["key"]
        detail = json.loads(
            (tmp_path / "data" / "loc" / key[:2] / f"{key}.json").read_text(encoding="utf-8")
        )
        assert detail["fetched_at"] == "2026-10-26T10:29:56Z"
        assert not any(con["out"] for con in feature["properties"]["cons"])
        options += detail["tariff_options"]
    assert options
    for option in options:
        assert "<" not in option["name"]
        assert option["original_name"].startswith("<div>")
    idle = [o for o in options if o["tariff_id"] == "zest:GB:ZST:530"]
    assert idle and idle[0]["name"] == (
        "A temporary pre-auth is held for sessions. You won't pay more than your session "
        "amount. Idle fees apply between 08:00am - 11.00pm £0.10/min after 4 hours not "
        "charging (grace period). 4 hours grace period applicable all day/night."
    )
