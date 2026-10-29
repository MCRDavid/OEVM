"""Connekt's data, a copy it sent by email, read by the sent_copy adapter (ADR 0029)."""

import gzip
import hashlib
import json
import re
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest
from pydantic import ValidationError

from adapters.http import FeedError
from adapters.sent_copy import read_response
from pipeline import publish, run, status, transparency
from pipeline.health import in_uk
from pipeline.pricing import describe_tariff
from pipeline.registry import ROOT, RegistryError, load_registry
from schema.operator import OperatorConfig
from schema.published import OperatorStatus
from schema.runlog import RunLog

FIXTURES = Path(__file__).parent / "fixtures" / "connekt"
MADE_AT = datetime(2026, 10, 26, 14, 22, 52, tzinfo=UTC)
WHEN = datetime(2026, 10, 30, 4, 17, tzinfo=UTC)
FILES = "https://github.com/MCRDavid/OEVM/tree/main/tests/fixtures/connekt"


class NoRequests(httpx.BaseTransport):
    """Fails the test if anything tries to reach a network."""

    def handle_request(self, request: httpx.Request) -> httpx.Response:
        raise AssertionError(f"a sent copy made a request to {request.url}")


def fixture_config(config: OperatorConfig | None = None) -> OperatorConfig:
    """Connekt's registry entry, reading the trimmed fixture as run.run_fixtures does."""
    config = config or load_registry()["connekt"]
    files = {
        "locations": "tests/fixtures/connekt/locations.json",
        "tariffs": "tests/fixtures/connekt/tariffs.json",
    }
    return config.model_copy(update={"sent_copy": config.sent_copy.model_copy(update=files)})


def read(config: OperatorConfig | None = None):
    return run.run_operator(fixture_config(config), transport=NoRequests(), sleep=lambda _s: 0)


def raw_records(module: str) -> list[dict]:
    return json.loads((FIXTURES / f"{module}.json").read_text(encoding="utf-8"))["data"]


def test_the_copy_is_read_without_any_request():
    result = read()
    assert result.requests == 0
    assert result.complete
    assert {m: (f.total_reported, len(f.pages)) for m, f in result.modules.items()} == {
        "locations": (6, 0),
        "tariffs": (8, 0),
    }
    assert result.issues == [
        "Read from a copy the operator sent on 2026-10-26, made 2026-10-26 14:22 UTC; no "
        "request was made.",
        "20 charge point statuses in the copy shown as unknown.",
    ]


def test_every_record_is_dated_when_the_copy_was_made_and_marked_as_a_sent_file():
    result = read()
    assert result.fetched_at == MADE_AT
    records = [*result.locations, *result.tariffs]
    assert len(records) == 14
    for record in records:
        assert record.provenance.fetched_at == MADE_AT
        assert record.provenance.method == "operator_static_file"
        assert str(record.provenance.source_url) == FILES
        assert record.provenance.licence == "OGL-3.0"


def test_every_charge_point_status_is_unknown_whatever_the_copy_says():
    sent = Counter(e["status"] for loc in raw_records("locations") for e in loc["evses"])
    assert sent == {"AVAILABLE": 17, "CHARGING": 2, "OUTOFORDER": 1}
    evses = [e for loc in read().locations for e in loc.evses]
    assert len(evses) == 20
    assert {(e.status, e.status_at) for e in evses} == {("unknown", None)}


def test_the_rest_of_each_record_converts_as_sent():
    result = read()
    assert sorted(loc.id for loc in result.locations) == sorted(
        f"connekt:GB:CON:{n}" for n in ("5", "103", "149", "215", "332", "446")
    )
    connectors = [c for loc in result.locations for e in loc.evses for c in e.connectors]
    power = Counter((c.power_type, c.max_kw) for c in connectors)
    assert {kw for kind, kw in power if kind == "dc"} == {40.0, 50.0, 60.0, 120.0}
    assert {(kind, kw) for kind, kw in power if kind != "dc"} == {
        ("ac_1_phase", 7.4),
        ("ac_3_phase", 22.0),
    }
    # The city is passed on as sent, even where Connekt sends the word "undefined".
    cities = Counter(loc.address.city for loc in result.locations)
    assert cities["undefined"] == 2
    assert all(in_uk(loc) for loc in result.locations)
    assert sum(not c.tariff_ids for c in connectors) == 2


def test_prices_add_the_vat_the_copy_states():
    # Tariff 561 is a flat 0.49 and 0.39 per kWh before VAT, with VAT stated as 20.
    tariffs = {t.id: t for t in read().tariffs}
    text = describe_tariff(tariffs["connekt:GB:CON:561"]).text
    assert text == "46.8p per kWh, plus £0.59 per session including VAT"


def received_hashes() -> dict[str, str]:
    """The SHA-256 of each file as received, before gzip, from the copy's README table."""
    readme = (ROOT / "sent_copies" / "connekt" / "README.md").read_text(encoding="utf-8")
    rows = re.findall(r"^\| `2026-10-26-(\w+)\.json\.gz` \|.*\| `([0-9a-f]{64})` \|$", readme, re.M)
    return dict(rows)


def test_the_files_kept_are_exactly_the_ones_connekt_sent():
    config = load_registry()["connekt"]
    copy = config.sent_copy
    assert copy.made_at == MADE_AT and copy.received.isoformat() == "2026-10-26"
    received = received_hashes()
    assert set(received) == {"locations", "tariffs"}
    for module in ("locations", "tariffs"):
        blob = gzip.decompress((ROOT / getattr(copy, module)).read_bytes())
        assert hashlib.sha256(blob).hexdigest() == received[module]
        body = json.loads(blob)
        assert body["status_code"] == 1000
        # made_at is the responses' own timestamp, to the second.
        stamp = datetime.fromisoformat(body["timestamp"].replace("Z", "+00:00"))
        assert stamp.replace(microsecond=0) == MADE_AT


def test_the_whole_copy_maps_every_location_in_the_uk():
    config = load_registry()["connekt"]
    result = run.run_operator(config, transport=NoRequests(), sleep=lambda _s: 0)
    assert len(result.locations) == 362 and len(result.tariffs) == 326
    assert {loc.id.split(":")[1:3] == ["GB", "CON"] for loc in result.locations} == {True}
    assert all(e.status == "unknown" for loc in result.locations for e in loc.evses)
    assert all(in_uk(loc) for loc in result.locations)


def test_a_file_that_is_not_an_ocpi_response_stops_the_run(tmp_path):
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"status_code": 2001, "data": []}), encoding="utf-8")
    with pytest.raises(FeedError, match="status_code 2001"):
        read_response(bad, "locations")
    bad.write_text(json.dumps({"data": {"locations": []}, "status_code": 1000}), "utf-8")
    with pytest.raises(FeedError, match="not an OCPI response with a list"):
        read_response(bad, "locations")
    with pytest.raises(FeedError, match="is missing"):
        read_response(tmp_path / "gone.json.gz", "tariffs")


def test_maps_details_and_manifest_say_the_data_is_a_copy(tmp_path):
    operators = load_registry()
    published = publish.publish([read()], operators, tmp_path, mode="live", generated_at=WHEN)
    entry = published.manifest.operators["connekt"]
    assert entry.fetched_at == MADE_AT and entry.mapped == 6
    note = entry.sent_copy
    assert note.received.isoformat() == "2026-10-26" and note.channel == "email"
    assert note.files_url == "https://github.com/MCRDavid/OEVM/tree/main/sent_copies/connekt"
    assert note.note == (
        "Connekt sent this data by email on 26 October 2026, in files made at 14:22 UTC that "
        "day. This map shows that copy as sent, by the repository owner's decision of 29 "
        "October 2026, while no address to fetch Connekt's data from is known. It is not "
        "updated, so details and prices may have changed since, and charge point status is "
        "not shown."
    )
    assert any(
        "from a copy it sent, made 2026-10-26 14:22 UTC" in line for line in published.report
    )
    layer = json.loads((tmp_path / "data" / "locations.geojson").read_text(encoding="utf-8"))
    for feature in layer["features"]:
        key = feature["properties"]["key"]
        detail = json.loads(
            (tmp_path / "data" / "loc" / key[:2] / f"{key}.json").read_text(encoding="utf-8")
        )
        assert detail["fetched_at"] == "2026-10-26T14:22:52Z"
        assert detail["sent_copy"] == note.model_dump(mode="json")
        # No connector is flagged out of service from a status in the copy.
        assert not any(con["out"] for con in feature["properties"]["cons"])


def test_a_fetched_feed_carries_no_sent_copy_note(tmp_path):
    results = [r for r in run.run_fixtures(load_registry()) if r.operator_id == "fastned"]
    published = publish.publish(
        results, load_registry(), tmp_path, mode="fixtures", generated_at=WHEN
    )
    assert published.manifest.operators["fastned"].sent_copy is None


def test_the_feed_health_page_shows_a_copy_in_yellow_and_says_it_is_not_fetched():
    log = RunLog.model_validate(run.run_log(read(), "live"))
    note = publish.sent_copy_note(load_registry()["connekt"])
    copy = OperatorStatus(name="Connekt", latest=log, history=[], sent_copy=note)
    assert status.colour(copy, MADE_AT) == status.YELLOW
    assert status.result_label(copy) == (
        "Not fetched: the map shows a copy the operator sent on 2026-10-26, made "
        "2026-10-26 14:22 UTC, with charge point status unknown"
    )
    # The same run without the note would be green on the day it was made.
    fetched = OperatorStatus(name="Connekt", latest=log, history=[])
    assert status.colour(fetched, MADE_AT) == status.GREEN


def test_the_transparency_page_says_no_requests_are_made_and_links_the_files():
    page = transparency.render_html(transparency.build(load_registry()))
    assert "No requests are made. The map shows a copy the operator sent by email on " in page
    assert "2026-10-26, made 2026-10-26 14:22 UTC" in page
    assert "sent_copies/connekt/2026-10-26-locations.json.gz" in page
    assert "evidence/connekt/2026-10-26-reply.md" in page


def entry(**changes) -> dict:
    """Connekt's registry file as a dict, with changes."""
    config = load_registry()["connekt"].model_dump(mode="json")
    return config | changes


def test_the_adapter_and_the_owners_decision_go_together():
    copy = entry()["sent_copy"]
    with pytest.raises(ValidationError, match="go together"):
        OperatorConfig.model_validate(entry(sent_copy=None))
    with pytest.raises(ValidationError, match="go together"):
        OperatorConfig.model_validate(entry(adapter="ocpi_221", base_url="https://example.com"))
    moved = copy | {"locations": "sent_copies/other/2026-10-26-locations.json.gz"}
    with pytest.raises(ValidationError, match="must be under sent_copies/connekt/"):
        OperatorConfig.model_validate(entry(sent_copy=moved))
    with pytest.raises(ValidationError, match="no feed URLs"):
        OperatorConfig.model_validate(entry(base_url="https://example.com/ocpi"))
    with pytest.raises(ValidationError, match="String should match pattern"):
        OperatorConfig.model_validate(entry(sent_copy=copy | {"tariffs": "tariffs.json"}))
    with pytest.raises(ValidationError, match="needs a time zone"):
        OperatorConfig.model_validate(entry(sent_copy=copy | {"made_at": "2026-10-26T14:22:52"}))
    with pytest.raises(ValidationError, match="later than the day"):
        OperatorConfig.model_validate(entry(sent_copy=copy | {"made_at": "2026-10-27T09:00:00Z"}))


def test_the_registry_refuses_a_sent_copy_whose_files_are_missing(tmp_path):
    operators = tmp_path / "operators"
    operators.mkdir()
    text = (ROOT / "operators" / "connekt.yaml").read_text(encoding="utf-8")
    (operators / "connekt.yaml").write_text(text, encoding="utf-8")
    evidence = tmp_path / "evidence" / "connekt"
    evidence.mkdir(parents=True)
    (evidence / "2026-10-26-reply.md").write_text("saved reply", encoding="utf-8")
    with pytest.raises(RegistryError) as error:
        load_registry(operators)
    assert "sent_copy file sent_copies/connekt/2026-10-26-locations.json.gz does not exist" in str(
        error.value
    )
