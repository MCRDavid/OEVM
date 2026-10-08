"""Tests for the Jolt adapter (adapters/jolt.py). No test touches the network.

Recorded Jolt responses in tests/fixtures/jolt/ cover the real format and its quirks.
Made-up responses (httpx.MockTransport) cover failures and edge cases.
"""

import copy
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from adapters import jolt
from adapters.http import FeedError, PoliteClient
from adapters.ocpi_221.normalise import IssueLog, publish_allowed
from adapters.replay import ReplayTransport
from pipeline import run
from pipeline.pricing import describe_tariff
from pipeline.registry import load_registry
from schema.operator import OperatorConfig

FIXTURES = Path(__file__).parent / "fixtures" / "jolt"
NOW = datetime(2026, 10, 8, 7, 48, 32, tzinfo=UTC)
LOCATIONS = "https://api.joltcharge.com/v1/uk/public/locations"
TARIFFS = "https://api.joltcharge.com/v1/uk/public/tariffs/"
FAKE = "test-value-jolt"  # made-up key; real keys come from the environment


class Recorder:
    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def config(**update) -> OperatorConfig:
    return load_registry()["jolt"].model_copy(update=update)


def recorded(name: str) -> dict:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))["response"]["body"]


def replay(cfg: OperatorConfig | None = None, **kwargs):
    cfg = cfg or config()
    transport = ReplayTransport(FIXTURES)
    with PoliteClient(cfg, transport=transport, sleep=Recorder(), clock=lambda: 0, key=FAKE) as c:
        return jolt.fetch(cfg, c, now=NOW, **kwargs), transport


def serve(locations: object, tariffs: dict[str, object] | None = None, **headers):
    """A handler serving a locations body and tariff bodies by id; unknown ids get 404."""
    tariffs = {"4": recorded("tariff_4.json")} if tariffs is None else tariffs
    seen: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(str(request.url))
        assert request.url.params["apiKey"] == FAKE
        if request.url.path.endswith("/locations"):
            return httpx.Response(200, json=locations, headers=headers)
        tariff_id = request.url.path.rsplit("/", 1)[1]
        if tariff_id in tariffs:
            return httpx.Response(200, json=tariffs[tariff_id])
        return httpx.Response(404, json={"message": "Not Found"})

    handler.seen = seen
    return handler


def run_with(handler, cfg: OperatorConfig | None = None, sleep=None, **kwargs):
    cfg = cfg or config()
    transport = httpx.MockTransport(handler)
    with PoliteClient(
        cfg, transport=transport, sleep=sleep or Recorder(), clock=lambda: 0, key=FAKE
    ) as client:
        return jolt.fetch(cfg, client, now=NOW, **kwargs)


def one_location(**overrides) -> dict:
    location = copy.deepcopy(recorded("locations.json")["locations"][0])
    location.update(overrides)
    return location


# Replaying the recorded responses


def test_recorded_responses_are_fetched_in_order():
    result, transport = replay()
    assert transport.requested == [
        LOCATIONS + "?apiKey=REDACTED",
        *(f"{TARIFFS}{t}?apiKey=REDACTED" for t in ("13", "14", "25", "4", "5")),
    ]
    assert result.complete and result.requests == 0  # requests is set by run_operator
    assert len(result.modules["locations"].pages) == 1
    assert len(result.modules["tariffs"].pages) == 5


def test_recorded_locations_convert_faithfully():
    result, _ = replay()
    by_name = {location.name: location for location in result.locations}
    assert sorted(by_name) == ["BAR004", "BAR070", "BAR114", "IONITY Nottingham VH"]

    bar004 = by_name["BAR004"]
    assert bar004.id == "jolt:GB:JLT:BAR004"  # the name stands in for the missing id
    assert bar004.last_updated is None
    first, second = bar004.evses
    assert (first.uid, first.evse_id, first.status) == ("143", None, "available")
    assert first.status_at == NOW  # dated with the time it was fetched
    assert second.status == "unknown"  # 'preparing' is not an OCPI 2.2.1 status
    assert first.connectors[0].standard == "CHADEMO"
    assert second.connectors[0].standard == "IEC_62196_T2_COMBO"  # published as CCS2
    assert first.connectors[0].id == "143"
    assert first.connectors[0].max_kw == 25.0  # from max_electric_power, not 0 A
    assert first.connectors[0].tariff_ids == [f"jolt:GB:JLT:{t}" for t in ("4", "5", "13", "14")]

    assert all(not evse.connectors for evse in by_name["BAR070"].evses)
    assert {evse.status for evse in by_name["BAR114"].evses} == {"inoperative", "charging"}
    ionity = by_name["IONITY Nottingham VH"]
    assert ionity.time_zone is None
    assert any(not c.tariff_ids for e in ionity.evses for c in e.connectors)
    assert all(location.operator.name == "Jolt" for location in result.locations)


def test_recorded_tariffs_show_pounds_and_pence_including_vat():
    result, _ = replay()
    shown = {tariff.id: describe_tariff(tariff).text for tariff in result.tariffs}
    assert shown == {
        "jolt:GB:JLT:4": "49.2p per kWh including VAT",
        "jolt:GB:JLT:5": "49.2p per kWh including VAT",
        "jolt:GB:JLT:14": "49.2p per kWh including VAT",
        "jolt:GB:JLT:25": "88.8p per kWh including VAT",
    }
    alt_text = {tariff.id: tariff.alt_text for tariff in result.tariffs}
    assert alt_text["jolt:GB:JLT:4"] == "Contactless / Ad-hoc"
    assert all(tariff.min_price == 0 for tariff in result.tariffs)


def test_recorded_quirks_are_logged():
    result, _ = replay()
    assert result.issues == [
        "EVSE status 'preparing' is not an OCPI 2.2.1 value; recorded as unknown",
        "location has no publish flag; kept under the decision recorded in the operator file "
        "(4 times)",
        "tariff '13' skipped: price: Input should be a valid number",
    ]


# The publish flag


def test_without_the_owners_decision_no_location_is_kept():
    result, _ = replay(config(missing_publish_flag=None))
    assert result.locations == []
    assert "location not kept: publish flag missing (4 times)" in result.issues


def test_publish_false_is_respected_even_with_the_decision():
    handler = serve({"locations": [one_location(publish=False), one_location(name="B2")]})
    result = run_with(handler)
    assert [location.name for location in result.locations] == ["B2"]
    assert "location not kept: publish is false" in result.issues


@pytest.mark.parametrize(
    ("publish", "decided", "kept", "issue"),
    [
        (True, False, True, None),
        (False, True, False, "location not kept: publish is false"),
        (None, False, False, "location not kept: publish flag missing"),
        (None, True, True, "location has no publish flag; kept under the decision"),
        ("yes", True, False, "location not kept: publish flag 'yes' is not true or false"),
    ],
)
def test_publish_rule(publish, decided, kept, issue):
    cfg = config() if decided else config(missing_publish_flag=None)
    issues = IssueLog()
    raw = {} if publish is None else {"publish": publish}
    assert publish_allowed(raw, cfg, issues) is kept
    lines = issues.lines()
    assert (lines == []) if issue is None else lines[0].startswith(issue)


# Failures and edge cases


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(503), "HTTP 503"),
        (httpx.Response(401, json={"message": "Unauthorized"}), "HTTP 401"),
        (httpx.Response(200, content=b"<html>"), "did not return JSON"),
        (httpx.Response(200, json=[]), "no list of locations"),
        (httpx.Response(200, json={"locations": {}}), "no list of locations"),
    ],
    ids=["server-error", "unauthorised", "not-json", "list", "locations-not-a-list"],
)
def test_bad_location_responses_raise_feed_errors(response, message):
    def handler(request):
        return response

    with pytest.raises(FeedError, match=message):
        run_with(handler, sleep=lambda _s: None)


def test_a_next_page_link_stops_the_run():
    handler = serve({"locations": []}, Link=f'<{LOCATIONS}?page=2>; rel="next"')
    with pytest.raises(FeedError, match="next page link"):
        run_with(handler)


def test_a_missing_tariff_is_logged_and_marks_the_run_incomplete():
    location = one_location()  # refers to tariffs 4, 5, 13 and 14; only 4 is served
    result = run_with(serve({"locations": [location]}))
    assert [tariff.id for tariff in result.tariffs] == ["jolt:GB:JLT:4"]
    assert "tariff '5' not used: HTTP 404" in result.issues
    assert not result.modules["tariffs"].complete and not result.complete


def test_a_tariff_that_is_not_an_object_is_logged():
    location = one_location()
    location["evses"][0]["connectors"][0]["tariff_ids"] = ["4"]
    location["evses"][1]["connectors"][0]["tariff_ids"] = ["4"]
    result = run_with(serve({"locations": [location]}, {"4": ["not", "a", "tariff"]}))
    assert result.tariffs == []
    assert "tariff '4' not used: not a tariff object" in result.issues


def test_tariff_ids_with_unexpected_characters_are_never_requested():
    location = one_location()
    location["evses"][0]["connectors"][0]["tariff_ids"] = ["../locations", "a/b", "4"]
    location["evses"][1]["connectors"][0]["tariff_ids"] = []
    handler = serve({"locations": [location]})
    result = run_with(handler)
    assert handler.seen[1:] == [f"{TARIFFS}4?apiKey={FAKE}"]
    assert "tariff id '../locations' not fetched: unexpected characters" in result.issues
    assert "tariff id 'a/b' not fetched: unexpected characters" in result.issues


def test_the_number_of_tariff_requests_is_capped(monkeypatch):
    monkeypatch.setattr(jolt, "MAX_TARIFFS", 2)
    handler = serve({"locations": [one_location()]})
    result = run_with(handler)
    assert len(handler.seen) == 3  # locations, then two tariffs
    assert "2 tariff ids not fetched: more than 2" in result.issues
    assert not result.modules["tariffs"].complete


def test_max_pages_limits_tariff_requests():
    handler = serve({"locations": [one_location()]})
    result = run_with(handler, max_pages=1)
    assert len(handler.seen) == 2
    assert not result.complete


@pytest.mark.parametrize(
    "kwargs", [{"date_from": NOW}, {"page_size": 10}], ids=["date-from", "page-size"]
)
def test_options_jolt_does_not_offer_are_refused(kwargs):
    with pytest.raises(FeedError, match="no date_from or page size"):
        run_with(serve({"locations": []}), **kwargs)


@pytest.mark.parametrize(
    ("record", "message"),
    [
        ({**one_location(), "name": None}, "location skipped: location has no usable id"),
        ("not a location", "location skipped:"),
        ({**one_location(), "evses": ["not an evse"]}, "location skipped:"),
    ],
    ids=["no-name", "not-an-object", "evse-not-an-object"],
)
def test_unusable_locations_are_skipped_and_the_rest_kept(record, message):
    result = run_with(serve({"locations": [record, one_location(name="GOOD")]}))
    assert [location.name for location in result.locations] == ["GOOD"]
    assert any(issue.startswith(message) for issue in result.issues)


@pytest.mark.parametrize(
    ("field", "value", "skipped"),
    [
        ("min_price", 0, False),
        ("min_price", {"excl_vat": 1.0, "incl_vat": 1.2}, False),
        ("min_price", 1.5, True),
        ("max_price", 30, True),
        ("max_price", 0, False),
        ("min_price", True, True),
    ],
)
def test_plain_number_prices_are_used_only_when_zero(field, value, skipped):
    tariff = {**recorded("tariff_4.json"), field: value}
    location = one_location()
    for evse in location["evses"]:
        evse["connectors"][0]["tariff_ids"] = ["4"]
    result = run_with(serve({"locations": [location]}, {"4": tariff}))
    assert (result.tariffs == []) is skipped
    if skipped:
        assert any("does not say whether it includes VAT" in i for i in result.issues)


def test_requests_are_spaced_by_the_registry_gap():
    sleep = Recorder()
    run_with(serve({"locations": [one_location()]}), sleep=sleep)
    gap = config().rate_limit.min_seconds_between_requests
    assert len(sleep.sleeps) == 4 and all(s >= gap for s in sleep.sleeps)


def test_an_echoed_key_is_removed_from_saved_pages_and_records(tmp_path):
    location = one_location(address=f"Echo {FAKE}")
    result = run_with(serve({"locations": [location]}, {}, Link=""))
    run.save_raw(result, tmp_path)
    saved = " ".join(path.read_text() for path in tmp_path.glob("*.json"))
    assert FAKE not in saved
    assert result.locations[0].address.street == "Echo REDACTED"


# The command line and the registry


def test_fixtures_replay_without_a_real_key(monkeypatch, capsys):
    monkeypatch.delenv("JOLT_API_KEY", raising=False)
    assert run.main(["--fixtures"]) == 0
    assert "jolt: fetched" in capsys.readouterr().out


def test_a_live_run_without_the_secret_names_it(monkeypatch, capsys):
    monkeypatch.delenv("JOLT_API_KEY", raising=False)
    assert run.main(["--live", "jolt"]) == 1
    assert "JOLT_API_KEY is not set" in capsys.readouterr().err


def test_an_operator_without_a_custom_adapter_is_refused():
    other = config(id="example_operator")
    with pytest.raises(FeedError, match="custom adapter is not built yet"):
        run.run_operator(other, transport=httpx.MockTransport(lambda r: httpx.Response(500)))


def test_jolt_records_the_decision_and_its_findings():
    cfg = config()
    assert cfg.enabled and cfg.adapter == "custom"
    assert cfg.missing_publish_flag is not None
    assert cfg.missing_publish_flag.evidence_url.startswith("https://support.joltcharge.com/")
    assert any("publish flag" in finding.summary for finding in cfg.findings)


# Findings from the review on 2026-10-08


def test_a_failing_tariff_does_not_lose_the_locations():
    def handler(request):
        if request.url.path.endswith("/locations"):
            return httpx.Response(200, json={"locations": [one_location()]})
        if request.url.path.endswith("/5"):
            return httpx.Response(503)
        return httpx.Response(200, json=recorded("tariff_4.json"))

    result = run_with(handler)
    assert [location.name for location in result.locations] == ["BAR004"]
    assert any(i.startswith("tariff '5' not used: gave up") for i in result.issues)
    assert not result.modules["tariffs"].complete


def test_a_plain_string_where_ocpi_has_an_object_is_logged_not_fatal():
    tariff = {**recorded("tariff_4.json"), "tariff_alt_text": "Contactless / Ad-hoc"}
    broken = one_location(name="B2", operator="Jolt")
    location = one_location()
    for evse in location["evses"]:
        evse["connectors"][0]["tariff_ids"] = ["4"]
    result = run_with(serve({"locations": [location, broken]}, {"4": tariff}))
    assert [loc.name for loc in result.locations] == ["BAR004"]
    assert any(i.startswith("location 'B2' skipped") for i in result.issues)
    assert result.tariffs[0].alt_text == "Contactless / Ad-hoc"


def test_a_numeric_location_id_is_used_as_text():
    result = run_with(serve({"locations": [one_location(id=1000)]}))
    assert result.locations[0].id == "jolt:GB:JLT:1000"


def test_max_price_zero_means_no_maximum():
    tariff = {**recorded("tariff_4.json"), "max_price": 0}
    location = one_location()
    for evse in location["evses"]:
        evse["connectors"][0]["tariff_ids"] = ["4"]
    result = run_with(serve({"locations": [location]}, {"4": tariff}))
    assert result.tariffs[0].max_price is None
    assert result.tariffs[0].min_price == 0


def test_each_tariff_records_the_url_it_came_from():
    result, _ = replay()
    sources = {t.id: t.provenance.source_url for t in result.tariffs}
    assert sources["jolt:GB:JLT:4"] == TARIFFS + "4"
    assert all("{" not in url for url in sources.values())


def test_a_feed_reporting_more_locations_than_it_sent_stops_the_run():
    handler = serve({"locations": [one_location()]}, **{"X-Total-Count": "72"})
    with pytest.raises(FeedError, match="reports 72 locations but sent 1"):
        run_with(handler)


@pytest.mark.parametrize(
    ("evse_id", "kept"), [("143", None), (143, None), ("GB*JLT*E143", "GB*JLT*E143")]
)
def test_only_emi3_shaped_evse_ids_are_kept(evse_id, kept):
    location = one_location()
    location["evses"][0]["evse_id"] = evse_id
    result = run_with(serve({"locations": [location]}))
    first = result.locations[0].evses[0]
    assert first.evse_id == kept
    assert first.uid == str(evse_id)


def test_null_tariff_ids_are_dropped_not_requested():
    location = one_location()
    location["evses"][0]["connectors"][0]["tariff_ids"] = ["4", None]
    location["evses"][1]["connectors"][0]["tariff_ids"] = []
    handler = serve({"locations": [location]})
    result = run_with(handler)
    assert handler.seen[1:] == [f"{TARIFFS}4?apiKey={FAKE}"]
    assert result.locations[0].evses[0].connectors[0].tariff_ids == ["jolt:GB:JLT:4"]
    assert "tariff id None not used: not an id" in result.issues
