"""Tests for the daily fetch's resilience (ADR 0018): refusals part-way through a run,
rate limit headers, how far a failed fetch got, and keeping an operator's last good copy
on the map when its fetch fails. No test touches the network."""

import json
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from adapters import http
from adapters.http import FeedError, rate_limit_state, server_hint
from adapters.ocpi_221.client import fetch_module
from pipeline import publish, run, status
from pipeline.registry import load_registry
from schema.runlog import RunLog
from tests.test_rate_limits import EXAMPLE, FakeClock, Server, client_for, make_config

URL = f"{EXAMPLE}/locations"
OK = {"status_code": 1000, "data": [{"id": "x"}]}


def ok(**headers) -> httpx.Response:
    return httpx.Response(200, json=OK, headers=headers)


@pytest.fixture(autouse=True)
def fresh_timers():
    http.reset_host_timers()
    yield
    http.reset_host_timers()


def serve(responses, gap=2.0):
    clock = FakeClock()
    server = Server(clock, responses)
    client = client_for(make_config(gap), clock, server)
    return clock, server, client


# Refusals part-way through a run


def test_a_refusal_after_the_host_has_answered_waits_slows_down_and_carries_on():
    _clock, server, client = serve([ok(), httpx.Response(403), ok(), ok()])
    with client:
        client.get(URL)
        assert client.get(URL).status_code == 200
        client.get(URL)
    _first, refused, retried, after = server.arrivals
    assert retried - refused >= http.REFUSAL_COOL_DOWN_SECONDS
    # The gap is wider for the rest of the run, never narrower.
    assert after - retried >= 2.0 * http.REFUSAL_SLOW_DOWN - 1e-9
    assert len(client.events) == 1 and "HTTP 403 part-way" in client.events[0]


def test_a_refusal_to_the_first_request_is_not_retried():
    _clock, server, client = serve([httpx.Response(403), ok()])
    with client:
        assert client.get(URL).status_code == 403
    assert len(server.arrivals) == 1
    assert client.events == []


def test_refusals_are_retried_at_most_twice_per_request():
    responses = [ok()] + [httpx.Response(403)] * 3
    _clock, server, client = serve(responses)
    with client:
        client.get(URL)
        assert client.get(URL).status_code == 403
    assert len(server.arrivals) == 1 + 1 + http.MAX_REFUSAL_RETRIES


def test_a_refusal_honours_the_servers_own_wait():
    _clock, server, client = serve([ok(), httpx.Response(403, headers={"Retry-After": "40"}), ok()])
    with client:
        client.get(URL)
        client.get(URL)
    assert server.arrivals[2] - server.arrivals[1] == pytest.approx(40)


def test_a_refusal_asking_for_too_long_a_wait_stops_the_fetch():
    _clock, server, client = serve([ok(), httpx.Response(403, headers={"Retry-After": "3600"})])
    with client:
        client.get(URL)
        with pytest.raises(FeedError, match="longer than it waits"):
            client.get(URL)
    assert len(server.arrivals) == 2


# Rate limit headers


@pytest.mark.parametrize(
    "headers, expected",
    [
        ({"RateLimit": "limit=10, remaining=0, reset=30"}, (0, 30)),
        ({"RateLimit": '"default";r=0;t=30'}, (0, 30)),
        ({"RateLimit-Remaining": "5", "RateLimit-Reset": "12"}, (5, 12)),
        ({"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "20"}, (0, 20)),
        ({"X-Rate-Limit-Remaining": "1"}, (1, None)),
        (
            {"X-RateLimit-Reset": str(int(datetime(2026, 10, 8, 12, 1, tzinfo=UTC).timestamp()))},
            (None, 60),
        ),
        ({"X-RateLimit-Remaining": "soon"}, (None, None)),
        ({}, (None, None)),
    ],
)
def test_rate_limit_headers_are_read(headers, expected):
    now = datetime(2026, 10, 8, 12, 0, tzinfo=UTC)
    assert rate_limit_state(httpx.Response(200, headers=headers), now) == expected


def test_no_requests_left_holds_the_host_until_the_reset():
    _clock, server, client = serve(
        [ok(**{"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "30"}), ok()]
    )
    with client:
        client.get(URL)
        client.get(URL)
    assert server.arrivals[1] - server.arrivals[0] >= 30 + http.LIMIT_MARGIN_SECONDS


def test_requests_left_keep_the_normal_gap():
    _clock, server, client = serve([ok(**{"RateLimit": "remaining=3, reset=30"}), ok()])
    with client:
        client.get(URL)
        client.get(URL)
    assert server.arrivals[1] - server.arrivals[0] == pytest.approx(2.0)


def test_a_429_with_only_a_reset_time_waits_for_it():
    limited = httpx.Response(429, headers={"RateLimit-Remaining": "0", "RateLimit-Reset": "50"})
    _clock, server, client = serve([limited, ok()])
    with client:
        client.get(URL)
    assert server.arrivals[1] - server.arrivals[0] >= 50


def test_error_messages_say_who_answered():
    response = httpx.Response(
        403, headers={"Server": "cloudflare<script>", "X-RateLimit-Limit": "60"}
    )
    assert (
        server_hint(response) == " (server cloudflarescript; rate limit headers x-ratelimit-limit)"
    )
    assert server_hint(httpx.Response(403)) == ""


# How far a failed fetch got


def test_a_failed_module_says_how_far_it_got():
    page = httpx.Response(
        200,
        json={"status_code": 1000, "data": [{"id": "a"}, {"id": "b"}]},
        headers={"X-Total-Count": "4"},
    )
    _clock, _server, client = serve([page, httpx.Response(404)])
    with client, pytest.raises(FeedError) as caught:
        fetch_module(client, "locations", URL)
    partial = caught.value.partial
    assert (len(partial.pages), len(partial.records), partial.complete) == (1, 2, False)
    assert partial.total_reported == 4


def test_the_failure_log_keeps_the_counts_and_the_kept_copy():
    page = httpx.Response(
        200, json={"status_code": 1000, "data": [{"id": "a"}]}, headers={"X-Total-Count": "2"}
    )
    _clock, _server, client = serve([page, httpx.Response(404)])
    with client, pytest.raises(FeedError) as caught:
        fetch_module(client, "locations", URL)
    when = datetime(2026, 10, 9, 17, 56, tzinfo=UTC)
    log = run.failure_log(
        "chargy",
        "live",
        str(caught.value),
        when,
        modules={"locations": caught.value.partial},
        requests=57,
        kept_copy=(datetime(2026, 10, 9, 11, 20, tzinfo=UTC), 5948),
    )
    parsed = RunLog.model_validate(log)
    assert parsed.requests == 57
    assert parsed.modules["locations"].records == 1
    assert parsed.kept_copy.fetched_at == "2026-10-09T11:20:00Z"
    assert (
        parsed.issues[-1]
        == "The map kept showing the last good copy, fetched 2026-10-09T11:20:00Z."
    )


# Keeping the last good copy


@pytest.fixture(scope="module")
def replayed():
    return {r.operator_id: r for r in run.run_fixtures(load_registry())}


def live_run(monkeypatch, replayed, tmp_path, name, failing=(), previous=None):
    def fake(config, **kwargs):
        if config.id in failing:
            raise FeedError(f"{config.id}: refused by the test")
        return replayed[config.id]

    monkeypatch.setattr(run, "run_operator", fake)
    out, logs = tmp_path / name, tmp_path / f"{name}-logs"
    argv = ["--live", "all", "--publish", str(out), "--log-dir", str(logs)]
    if previous is not None:
        argv += ["--previous", str(previous)]
    return run.main(argv), out, logs


def _layer(out):
    return json.loads((out / "data" / "locations.geojson").read_text())


def test_a_failed_operator_keeps_its_last_good_copy(monkeypatch, replayed, tmp_path, capsys):
    code, before, _ = live_run(monkeypatch, replayed, tmp_path, "before")
    assert code == 0
    code, after, logs = live_run(
        monkeypatch, replayed, tmp_path, "after", failing={"jolt"}, previous=before
    )
    assert code == run.EXIT_KEPT_LAST_GOOD
    assert _layer(after) == _layer(before)
    manifest = json.loads((after / "data" / "manifest.json").read_text())
    old = json.loads((before / "data" / "manifest.json").read_text())
    assert manifest["operators"]["jolt"]["kept_from_previous"] is True
    assert manifest["operators"]["jolt"]["fetched_at"] == old["operators"]["jolt"]["fetched_at"]
    assert not any(e["kept_from_previous"] for i, e in manifest["operators"].items() if i != "jolt")
    for path in (before / "data" / "loc").glob("*/*.json"):
        assert (
            after / "data" / "loc" / path.parent.name / path.name
        ).read_bytes() == path.read_bytes()
    log = RunLog.model_validate_json((logs / "jolt.json").read_text())
    assert log.failed and log.kept_copy is not None
    assert "the map shows the last good copy: jolt" in capsys.readouterr().err


def test_without_a_previous_copy_the_operator_is_left_out(monkeypatch, replayed, tmp_path):
    code, after, logs = live_run(monkeypatch, replayed, tmp_path, "after", failing={"jolt"})
    assert code == run.EXIT_SOME_FAILED
    assert "jolt" not in json.loads((after / "data" / "manifest.json").read_text())["operators"]
    assert RunLog.model_validate_json((logs / "jolt.json").read_text()).kept_copy is None


def test_a_copy_kept_once_is_kept_again_with_its_first_date(monkeypatch, replayed, tmp_path):
    _, first, _ = live_run(monkeypatch, replayed, tmp_path, "first")
    _, second, _ = live_run(monkeypatch, replayed, tmp_path, "second", {"jolt"}, first)
    code, third, _ = live_run(monkeypatch, replayed, tmp_path, "third", {"jolt"}, second)
    assert code == run.EXIT_KEPT_LAST_GOOD
    dates = [
        json.loads((d / "data" / "manifest.json").read_text())["operators"]["jolt"]["fetched_at"]
        for d in (first, second, third)
    ]
    assert len(set(dates)) == 1


def test_an_old_or_replayed_copy_is_not_kept(monkeypatch, replayed, tmp_path):
    _, before, _ = live_run(monkeypatch, replayed, tmp_path, "before")
    config = load_registry()["jolt"]
    fetched = replayed["jolt"].fetched_at
    copy, why = publish.last_good_copy(before, "jolt", config, fetched + timedelta(days=1))
    assert copy is not None and why == ""
    late = fetched + timedelta(days=publish.MAX_KEPT_DAYS, minutes=1)
    copy, why = publish.last_good_copy(before, "jolt", config, late)
    assert copy is None and "more than 7 days old" in why

    publish.publish(
        list(replayed.values()),
        load_registry(),
        tmp_path / "replay",
        mode="fixtures",
        generated_at=fetched,
    )
    copy, why = publish.last_good_copy(tmp_path / "replay", "jolt", config, fetched)
    assert copy is None and "not from a live fetch" in why

    copy, why = publish.last_good_copy(tmp_path / "nothing", "jolt", config, fetched)
    assert copy is None and "missing manifest.json" in why


def test_a_damaged_previous_copy_is_not_kept(monkeypatch, replayed, tmp_path):
    _, before, _ = live_run(monkeypatch, replayed, tmp_path, "before")
    key = next(
        f["properties"]["key"]
        for f in _layer(before)["features"]
        if f["properties"]["op"] == "jolt"
    )
    (before / "data" / "loc" / key[:2] / f"{key}.json").write_text("{}")
    config = load_registry()["jolt"]
    copy, why = publish.last_good_copy(before, "jolt", config, replayed["jolt"].fetched_at)
    assert copy is None and "not valid today" in why


def test_the_feed_health_page_says_the_map_kept_the_last_good_copy():
    when = datetime(2026, 10, 9, 17, 56, tzinfo=UTC)
    log = run.failure_log(
        "chargy",
        "live",
        "https://char.gy/open-ocpi/locations?limit=50&offset=2800 returned HTTP 403",
        when,
        kept_copy=(datetime(2026, 10, 9, 11, 20, tzinfo=UTC), 5948),
    )
    data = status.build(load_registry(), {"chargy": RunLog.model_validate(log)}, None, when)
    label = status.result_label(data.operators["chargy"])
    assert label == (
        "Fetch failed; the map still shows its last good copy, fetched 2026-10-09 11:20 UTC "
        "(5948 locations)"
    )
    assert label in status.render_html(data)
