"""Tests for the ocpi_221 adapter. No test touches the network.

Recorded char.gy responses in tests/fixtures/chargy/ cover real paging and data.
Made-up responses (httpx.MockTransport, example.invalid) cover failures and edge cases.
"""

import json
from datetime import UTC, datetime
from pathlib import Path

import httpx
import pytest

from adapters.http import FeedError, PoliteClient
from adapters.ocpi_221 import fetch
from adapters.ocpi_221.client import fetch_module
from adapters.ocpi_221.normalise import IssueLog, location_from_ocpi, parse_ocpi_datetime
from adapters.replay import ReplayTransport
from pipeline import run
from pipeline.registry import load_registry
from schema.operator import OperatorConfig

CHARGY_FIXTURES = Path(__file__).parent / "fixtures" / "chargy"
NOW = datetime(2026, 10, 7, 22, 40, tzinfo=UTC)
EXAMPLE = "https://example.invalid/ocpi"
# Names of environment variables used as fake secrets in the key tests.
HEADER_ENV_NAME = "EXAMPLE_OPERATOR_TOKEN"
PARAM_ENV_NAME = "EXAMPLE_OPERATOR_KEY"


@pytest.fixture
def chargy() -> OperatorConfig:
    return load_registry()["chargy"]


def make_config(**overrides) -> OperatorConfig:
    data = {
        "id": "example_operator",
        "display_name": "Example Operator",
        "ocpi_country_code": "GB",
        "ocpi_party_id": "EXA",
        "adapter": "ocpi_221",
        "base_url": EXAMPLE,
        "auth": {"method": "none"},
        "rate_limit": {"min_seconds_between_requests": 2},
        "supports_single_location": "unknown",
        "cors": "unknown",
        "engagement": {"status": "unknown"},
        "enabled": False,
    }
    data.update(overrides)
    return OperatorConfig.model_validate(data)


def ocpi_body(data: list) -> dict:
    return {"data": data, "status_code": 1000, "status_message": "Success", "timestamp": "x"}


def raw_location(location_id: str = "LOC1", **overrides) -> dict:
    location = {
        "country_code": "GB",
        "party_id": "EXA",
        "id": location_id,
        "publish": True,
        "address": "1 Example Street",
        "city": "Exampletown",
        "country": "GBR",
        "coordinates": {"latitude": "52.00000", "longitude": "-1.00000"},
        "time_zone": "Europe/London",
        "evses": [
            {
                "uid": "E1",
                "status": "AVAILABLE",
                "last_updated": "2026-10-07T10:00:00Z",
                "connectors": [
                    {
                        "id": "1",
                        "standard": "IEC_62196_T2",
                        "format": "SOCKET",
                        "power_type": "AC_3_PHASE",
                        "max_voltage": 230,
                        "max_amperage": 32,
                        "tariff_ids": ["T1"],
                    }
                ],
            }
        ],
        "last_updated": "2026-10-07T10:00:00Z",
    }
    location.update(overrides)
    return location


class Recorder:
    """Records sleeps, so tests run instantly and can check the delays asked for."""

    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def __call__(self, seconds: float) -> None:
        self.sleeps.append(seconds)


def client_for(config, handler, sleep=None) -> PoliteClient:
    return PoliteClient(
        config, transport=httpx.MockTransport(handler), sleep=sleep or Recorder(), clock=lambda: 0
    )


def serve_pages(pages: dict[str, httpx.Response]):
    """A MockTransport handler serving fixed responses by URL; unknown URLs fail the test."""

    def handler(request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        assert url in pages, f"unexpected request {url}"
        return pages[url]

    return handler


# Replaying the recorded char.gy responses


def test_replays_recorded_chargy_pages(chargy):
    transport = ReplayTransport(CHARGY_FIXTURES)
    with PoliteClient(chargy, transport=transport, sleep=Recorder()) as client:
        result = fetch(chargy, client, page_size=2, max_pages=2, now=NOW)

    assert transport.requested == [
        "https://char.gy/open-ocpi/locations?limit=2",
        "https://char.gy/open-ocpi/locations?limit=2&offset=2",
        "https://char.gy/open-ocpi/tariffs?limit=2",
        "https://char.gy/open-ocpi/tariffs?limit=2&offset=2",
    ]
    assert len(result.locations) == 4
    assert len(result.tariffs) == 3
    assert result.modules["locations"].total_reported == 5946
    assert result.modules["locations"].complete is False  # stopped by max_pages
    assert result.modules["tariffs"].complete is True  # last page has no Link
    assert result.complete is False


def test_date_from_is_sent_and_an_empty_result_is_complete(chargy):
    since = datetime(2026, 10, 7, 21, 0, tzinfo=UTC)
    transport = ReplayTransport(CHARGY_FIXTURES)
    with PoliteClient(chargy, transport=transport, sleep=Recorder()) as client:
        tariffs = fetch_module(
            client, "tariffs", "https://char.gy/open-ocpi/tariffs", date_from=since, page_size=2
        )
        locations = fetch_module(
            client,
            "locations",
            "https://char.gy/open-ocpi/locations",
            date_from=since,
            page_size=2,
            max_pages=1,
        )
    assert tariffs.records == [] and tariffs.complete is True
    assert locations.total_reported == 551
    assert all("date_from=2026-10-07T21:00:00Z" in url for url in transport.requested)


def test_recorded_chargy_data_converts_faithfully(chargy):
    with PoliteClient(chargy, transport=ReplayTransport(CHARGY_FIXTURES), sleep=Recorder()) as c:
        result = fetch(chargy, c, page_size=2, max_pages=2, now=NOW)
    raw = json.loads((CHARGY_FIXTURES / "locations_page1.json").read_text())
    raw_location_0 = raw["response"]["body"]["data"][0]
    raw_connector = raw_location_0["evses"][0]["connectors"][0]

    location = result.locations[0]
    connector = location.evses[0].connectors[0]
    assert location.id == f"chargy:GB:CGY:{raw_location_0['id']}"
    assert location.coordinates.latitude == float(raw_location_0["coordinates"]["latitude"])
    assert connector.standard == raw_connector["standard"]
    expected_kw = round(raw_connector["max_voltage"] * raw_connector["max_amperage"] / 1000, 2)
    assert connector.power_type == "ac_1_phase" and connector.max_kw == expected_kw
    assert location.provenance.source_url == "https://char.gy/open-ocpi/locations"
    assert location.provenance.licence == "OGL-3.0"
    assert location.provenance.fetched_at == NOW

    # char.gy uses "WORKING", which is not an OCPI status, so it must not be guessed.
    assert raw_location_0["evses"][0]["status"] == "WORKING"
    assert location.evses[0].status == "unknown"
    assert any("'WORKING' is not an OCPI 2.2.1 value" in issue for issue in result.issues)

    # Every tariff a connector refers to is one of the fetched tariffs, with the same id form.
    tariff_ids = {t.id for t in result.tariffs}
    assert set(connector.tariff_ids) <= tariff_ids


def test_recorded_chargy_tariffs_keep_what_was_published(chargy):
    with PoliteClient(chargy, transport=ReplayTransport(CHARGY_FIXTURES), sleep=Recorder()) as c:
        result = fetch(chargy, c, page_size=2, max_pages=2, now=NOW)
    currencies = sorted(t.currency for t in result.tariffs)
    assert currencies == ["EUR", "GBP", "USD"]  # recorded as published, never "corrected"
    timed = next(t for t in result.tariffs if len(t.elements) == 3)
    assert timed.price_state == "priced"
    assert timed.elements[1].restrictions.day_of_week[0] == "monday"
    assert all(c.vat is None for e in timed.elements for c in e.price_components)


# Paging edge cases


def test_offset_is_used_when_there_is_no_link_header():
    config = make_config()
    url = f"{EXAMPLE}/locations"
    pages = {
        url: httpx.Response(200, headers={"X-Total-Count": "3"}, json=ocpi_body([{}, {}])),
        f"{url}?offset=2": httpx.Response(
            200, headers={"X-Total-Count": "3"}, json=ocpi_body([{}])
        ),
    }
    with client_for(config, serve_pages(pages)) as client:
        result = fetch_module(client, "locations", url)
    assert len(result.records) == 3 and result.complete


def test_a_next_link_to_another_site_is_refused():
    config = make_config()
    url = f"{EXAMPLE}/locations"
    link = '<https://elsewhere.invalid/locations?offset=1>; rel="next"'
    pages = {url: httpx.Response(200, headers={"Link": link}, json=ocpi_body([{}]))}
    with client_for(config, serve_pages(pages)) as client, pytest.raises(FeedError, match="leaves"):
        fetch_module(client, "locations", url)


def test_a_link_back_to_the_same_page_does_not_loop_forever():
    config = make_config()
    url = f"{EXAMPLE}/locations"
    pages = {
        url: httpx.Response(200, headers={"Link": f'<{url}>; rel="next"'}, json=ocpi_body([{}]))
    }
    with client_for(config, serve_pages(pages)) as client, pytest.raises(FeedError, match="paging"):
        fetch_module(client, "locations", url)


@pytest.mark.parametrize(
    ("response", "message"),
    [
        (httpx.Response(404, json={}), "HTTP 404"),
        (httpx.Response(200, content=b"<html>"), "did not return JSON"),
        (httpx.Response(200, json=[1, 2]), "OCPI response object"),
        (
            httpx.Response(200, json={"status_code": 2001, "status_message": "Invalid"}),
            "OCPI status 2001",
        ),
        (httpx.Response(200, json={"status_code": 1000, "data": {}}), "no list of records"),
    ],
    ids=["http-404", "not-json", "not-ocpi", "ocpi-error", "data-not-a-list"],
)
def test_bad_responses_raise_feed_errors(response, message):
    config = make_config()
    url = f"{EXAMPLE}/locations"
    with (
        client_for(config, serve_pages({url: response})) as client,
        pytest.raises(FeedError, match=message),
    ):
        fetch_module(client, "locations", url)


# Politeness and retries


def test_requests_are_spaced_by_the_registry_delay():
    config = make_config(rate_limit={"min_seconds_between_requests": 7})
    sleeps = Recorder()
    with client_for(config, lambda r: httpx.Response(200, json=ocpi_body([])), sleeps) as client:
        client.get(f"{EXAMPLE}/a")
        client.get(f"{EXAMPLE}/b")
    assert sleeps.sleeps == [7]


def test_temporary_failures_are_retried_with_backoff_and_retry_after():
    config = make_config(rate_limit={"min_seconds_between_requests": 1})
    responses = iter(
        [
            httpx.Response(503),
            httpx.Response(429, headers={"Retry-After": "30"}),
            httpx.Response(200, json=ocpi_body([])),
        ]
    )
    sleeps = Recorder()
    with client_for(config, lambda r: next(responses), sleeps) as client:
        assert client.get(f"{EXAMPLE}/a").status_code == 200
    retry_waits = [s for s in sleeps.sleeps if s > 1]
    assert retry_waits == [5.0, 30.0]


def test_retries_give_up_with_a_clear_error():
    config = make_config()
    with (
        client_for(config, lambda r: httpx.Response(500)) as client,
        pytest.raises(FeedError, match="after 4 attempts: HTTP 500"),
    ):
        client.get(f"{EXAMPLE}/a")


def test_redirects_are_not_followed():
    config = make_config()
    redirect = httpx.Response(302, headers={"Location": "https://elsewhere.invalid/"})
    with client_for(config, lambda r: redirect) as client:
        assert client.get(f"{EXAMPLE}/a").status_code == 302


# Keys


def test_header_key_comes_from_the_environment(monkeypatch):
    config = make_config(
        auth={"method": "header", "name": "x-api-key", "secret_name": HEADER_ENV_NAME}
    )
    monkeypatch.setenv(HEADER_ENV_NAME, "test-value-123")
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, json=ocpi_body([]))

    with client_for(config, handler) as client:
        client.get(f"{EXAMPLE}/a")
    assert seen["x-api-key"] == "test-value-123"


def test_header_scheme_is_sent_before_the_key(monkeypatch):
    config = make_config(
        auth={
            "method": "header",
            "name": "Authorization",
            "scheme": "Token",
            "secret_name": HEADER_ENV_NAME,
        }
    )
    monkeypatch.setenv(HEADER_ENV_NAME, "test-value-789")
    seen = {}

    def handler(request):
        seen.update(request.headers)
        return httpx.Response(200, json=ocpi_body([]))

    with client_for(config, handler) as client:
        client.get(f"{EXAMPLE}/a")
    assert seen["authorization"] == "Token test-value-789"


def test_missing_key_names_the_secret_without_a_value(monkeypatch):
    config = make_config(
        auth={"method": "header", "name": "x-api-key", "secret_name": HEADER_ENV_NAME}
    )
    monkeypatch.delenv(HEADER_ENV_NAME, raising=False)
    with pytest.raises(FeedError, match="EXAMPLE_OPERATOR_TOKEN is not set"):
        client_for(config, lambda r: httpx.Response(200))


def test_query_param_key_is_sent_but_never_recorded(monkeypatch):
    config = make_config(
        auth={"method": "query_param", "name": "apiKey", "secret_name": PARAM_ENV_NAME}
    )
    monkeypatch.setenv(PARAM_ENV_NAME, "test-value-456")
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(500)

    with client_for(config, handler) as client, pytest.raises(FeedError) as error:
        client.get(f"{EXAMPLE}/locations")
    assert "apiKey=test-value-456" in requested[0]
    assert "test-value-456" not in str(error.value)

    pages = {f"{EXAMPLE}/locations?apiKey=test-value-456": httpx.Response(200, json=ocpi_body([]))}
    with client_for(config, serve_pages(pages)) as client:
        result = fetch_module(client, "locations", f"{EXAMPLE}/locations")
    assert result.pages[0].url == f"{EXAMPLE}/locations"  # the key is added only when sending


def test_an_echoed_key_is_removed_from_saved_pages_issues_and_errors(monkeypatch, tmp_path):
    config = make_config(
        auth={"method": "query_param", "name": "apiKey", "secret_name": PARAM_ENV_NAME},
        licence={"name": "OGL-3.0", "basis": "test", "checked": "2026-10-07"},
    )
    echoed = "test-value/echo+1"  # has characters that change when URL-encoded
    monkeypatch.setenv(PARAM_ENV_NAME, echoed)
    encoded = "test-value%2Fecho%2B1"
    echo = f"{EXAMPLE}/locations?apiKey={encoded}&offset=1"
    location = raw_location("A", address=f"Key {echoed} here")

    def handler(request):
        if request.url.path.endswith("/tariffs"):
            return httpx.Response(200, json=ocpi_body([]))
        if request.url.params.get("offset"):
            body = ocpi_body([]) | {"status_code": 2001, "status_message": f"bad key {echoed}"}
            return httpx.Response(200, json=body)
        return httpx.Response(
            200,
            json=ocpi_body([location, {"id": echoed, "publish": True}]),
            headers={"Link": f'<{echo}>; rel="next"', "X-Total-Count": "3"},
        )

    with client_for(config, handler) as client, pytest.raises(FeedError) as error:
        fetch(config, client, now=NOW)
    assert echoed not in str(error.value) and "bad key REDACTED" in str(error.value)

    with client_for(config, handler) as client:
        result = fetch(config, client, now=NOW, max_pages=1)
    run.save_raw(result, tmp_path)
    saved = (tmp_path / "locations_page1.json").read_text()
    assert "REDACTED" in saved
    assert echoed not in saved and encoded not in saved
    assert not [issue for issue in result.issues if echoed in issue]
    assert [issue for issue in result.issues if "location 'REDACTED' skipped" in issue]
    assert result.locations[0].address.street == "Key REDACTED here"


def test_a_key_is_never_sent_over_plain_http(monkeypatch):
    config = make_config(
        auth={"method": "header", "name": "x-api-key", "secret_name": HEADER_ENV_NAME}
    )
    monkeypatch.setenv(HEADER_ENV_NAME, "test-value-321")
    sent = []
    with (
        client_for(config, lambda r: sent.append(r) or httpx.Response(200)) as client,
        pytest.raises(FeedError, match="not sending a key over plain http"),
    ):
        client.get("http://example.invalid/ocpi/locations")
    assert sent == []


# Converting records


def run_with_locations(records: list[dict]):
    config = make_config(licence={"name": "OGL-3.0", "basis": "test", "checked": "2026-10-07"})
    pages = {
        f"{EXAMPLE}/locations": httpx.Response(200, json=ocpi_body(records)),
        f"{EXAMPLE}/tariffs": httpx.Response(200, json=ocpi_body([])),
    }
    with client_for(config, serve_pages(pages)) as client:
        return fetch(config, client, now=NOW)


def test_locations_not_allowed_to_be_published_are_never_kept():
    result = run_with_locations(
        [raw_location("A"), raw_location("B", publish=False), raw_location("C", publish=None)]
    )
    assert [loc.id for loc in result.locations] == ["example_operator:GB:EXA:A"]
    assert "location not kept: publish is false" in result.issues
    assert "location not kept: publish flag missing" in result.issues


def test_a_broken_record_is_skipped_and_the_rest_kept():
    broken = raw_location("BAD")
    del broken["coordinates"]
    result = run_with_locations([broken, raw_location("GOOD")])
    assert [loc.id.rsplit(":", 1)[1] for loc in result.locations] == ["GOOD"]
    assert "location 'BAD' skipped: missing field 'coordinates'" in result.issues


def test_duplicate_records_keep_the_last_copy():
    result = run_with_locations([raw_location("A", name="old"), raw_location("A", name="new")])
    assert [loc.name for loc in result.locations] == ["new"]
    assert "duplicate location record; kept the last copy" in result.issues


def test_three_phase_power_and_stated_power():
    issues = IssueLog()
    config = make_config()
    location = location_from_ocpi(
        raw_location(), config, source_url=EXAMPLE, fetched_at=NOW, issues=issues
    )
    assert location.evses[0].connectors[0].max_kw == 22.08  # 230 V x 32 A x 3 phases

    stated = raw_location()
    stated["evses"][0]["connectors"][0]["max_electric_power"] = 11000
    location = location_from_ocpi(stated, config, source_url=EXAMPLE, fetched_at=NOW, issues=issues)
    assert location.evses[0].connectors[0].max_kw == 11.0


def test_two_phase_power_is_not_guessed():
    issues = IssueLog()
    raw = raw_location()
    raw["evses"][0]["connectors"][0]["power_type"] = "AC_2_PHASE"
    location = location_from_ocpi(
        raw, make_config(), source_url=EXAMPLE, fetched_at=NOW, issues=issues
    )
    assert location.evses[0].connectors[0].max_kw is None
    assert issues.lines() == ["connector power not calculated for power_type 'ac_2_phase'"]


def test_values_that_are_not_ocpi_become_unknown():
    issues = IssueLog()
    raw = raw_location(country="GB", opening_times={"twentyfourseven": False})
    raw["evses"][0]["status"] = "WORKING"
    location = location_from_ocpi(
        raw, make_config(), source_url=EXAMPLE, fetched_at=NOW, issues=issues
    )
    assert location.address.country is None
    assert location.opening_hours is None
    assert location.evses[0].status == "unknown"
    assert len(issues.lines()) == 3


def test_timestamps_without_a_zone_are_utc():
    assert parse_ocpi_datetime("2026-10-07T10:00:00") == datetime(2026, 10, 7, 10, tzinfo=UTC)
    assert parse_ocpi_datetime("2026-10-07T10:00:00Z") == datetime(2026, 10, 7, 10, tzinfo=UTC)
    assert parse_ocpi_datetime(None) is None


# The command line


def test_fixtures_mode_runs_offline(capsys):
    assert run.main(["--fixtures"]) == 0
    assert "chargy: fetched" in capsys.readouterr().out


def test_live_mode_refuses_operators_that_are_not_enabled(capsys):
    assert run.main(["--live", "gridserve"]) == 1
    assert "not enabled" in capsys.readouterr().err


def test_live_mode_rejects_unknown_operators(capsys):
    assert run.main(["--live", "nobody"]) == 1
    assert "no operator 'nobody'" in capsys.readouterr().err


def test_a_failed_live_run_writes_a_failure_log(tmp_path, monkeypatch, capsys):
    def fail(*args, **kwargs):
        raise FeedError("gave up on https://char.gy/open-ocpi/locations: HTTP 503")

    monkeypatch.setattr(run, "run_operator", fail)
    assert run.main(["--live", "chargy", "--log-dir", str(tmp_path)]) == 1
    log = json.loads((tmp_path / "chargy.json").read_text())
    assert log["failed"] is True and log["complete"] is False
    assert log["issues"] == ["Run failed: gave up on https://char.gy/open-ocpi/locations: HTTP 503"]
    assert "HTTP 503" in capsys.readouterr().err


def test_live_all_fetches_every_enabled_operator_in_turn(tmp_path, monkeypatch):
    fetched = []

    def fake(config, **kwargs):
        fetched.append(config.id)
        raise FeedError(f"{config.id}: stopped by the test")

    monkeypatch.setattr(run, "run_operator", fake)
    assert run.main(["--live", "all", "--log-dir", str(tmp_path)]) == 1
    enabled = sorted(i for i, c in load_registry().items() if c.enabled)
    assert fetched == enabled
    assert sorted(p.stem for p in tmp_path.glob("*.json")) == enabled


def test_live_all_publishes_the_rest_when_one_operator_fails(tmp_path, monkeypatch, capsys):
    replayed = {r.operator_id: r for r in run.run_fixtures(load_registry())}

    def fake(config, **kwargs):
        if config.id == "jolt":
            raise FeedError("gave up on the Jolt feed: HTTP 503")
        return replayed[config.id]

    monkeypatch.setattr(run, "run_operator", fake)
    logs, out = tmp_path / "logs", tmp_path / "build"
    code = run.main(["--live", "all", "--log-dir", str(logs), "--publish", str(out)])
    assert code == run.EXIT_SOME_FAILED
    assert json.loads((logs / "jolt.json").read_text())["failed"] is True
    manifest = json.loads((out / "data" / "manifest.json").read_text())
    assert "jolt" not in manifest["operators"]
    assert set(manifest["operators"]) == set(replayed) - {"jolt"}
    assert "left out: jolt" in capsys.readouterr().err
