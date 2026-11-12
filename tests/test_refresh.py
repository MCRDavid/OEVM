"""Status refreshes between the daily fetches (pipeline/refresh.py, adapters/statuses.py).

No test touches the network: recorded responses are replayed (tests/fixtures) and made-up
ones come from httpx.MockTransport. The statuses fixtures were recorded on 10 November 2026.
"""

import json
from collections import Counter
from datetime import UTC, datetime, timedelta

import httpx
import pytest

from adapters import eco_movement, statuses
from adapters.http import FeedError, PoliteClient, required_gap
from adapters.ocpi_221.normalise import IssueLog
from adapters.replay import ReplayTransport
from pipeline import live_snapshot, publish, refresh, run
from pipeline.live_snapshot import SnapshotError, from_statuses
from pipeline.publish import location_key
from pipeline.registry import ROOT, load_registry
from schema.live import LiveEvse, LiveSnapshot, RefreshEntry, RefreshLog
from schema.operator import LIMIT_MARGIN_SECONDS, MIN_SECONDS_BETWEEN_REQUESTS

OPERATORS = load_registry()
FIXTURES = ROOT / "tests" / "fixtures"
FULL = {r.operator_id: r for r in run.run_fixtures(OPERATORS)}
REFRESHED = refresh.refresh_fixtures(OPERATORS)
ECO = sorted(i for i, c in OPERATORS.items() if c.adapter == "eco_movement_pcpr")
STATUSES = "https://open-chargepoints.com/api/statuses/"
NOW = datetime(2026, 11, 10, 9, 0, tzinfo=UTC)
FAKE_TOKEN = "made-up-token-for-tests"


class FakeClock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        assert seconds >= 0
        self.now += seconds


def statuses_body(data: list) -> dict:
    return {"timestamp": "x", "status_code": 1000, "status_message": "Success", "data": data}


def record(location_id: str, *evses: dict) -> dict:
    return {"id": location_id, "last_updated": "2026-11-10T08:00:00Z", "evses": list(evses)}


def evse(uid: str, status: str = "AVAILABLE", at: str | None = "2026-11-10T08:30:00Z") -> dict:
    return {"uid": uid, "status": status, "last_updated": at, "evse_id": uid}


def shown_for(operator_id: str) -> dict[str, str]:
    """The operator's fixture locations as the published map would list them."""
    return {
        location.id: location_key(location.id)
        for location in FULL[operator_id].locations
        if live_snapshot.in_uk(location)
    }


def replay(operator_id: str) -> tuple[statuses.StatusResult, ReplayTransport]:
    transport = ReplayTransport(FIXTURES / operator_id)
    manifest = json.loads((FIXTURES / operator_id / "manifest.json").read_text("utf-8"))
    result = refresh.refresh_operator(
        OPERATORS[operator_id].model_copy(update={"relay": None}),
        transport=transport,
        sleep=lambda _seconds: None,
        key=run.FIXTURE_KEY,
        page_size=manifest.get("page_size"),
        max_pages=manifest.get("max_pages"),
    )
    return result, transport


# Eco-Movement's statuses endpoint


def test_every_eco_movement_file_records_the_statuses_endpoint_with_its_slash_and_limit():
    assert len(ECO) >= 23
    for operator_id in ECO:
        config = OPERATORS[operator_id]
        assert config.endpoints["statuses"].url == STATUSES, operator_id
        limits = [limit for limit in config.rate_limit.limits if limit.endpoint == "statuses"]
        assert [(limit.requests, limit.per_seconds) for limit in limits] == [(1, 30)], operator_id


@pytest.mark.parametrize("operator_id", ["aldi", "wccc_edgbaston"])
def test_a_network_is_asked_for_its_statuses_alone_in_one_request(operator_id):
    result, transport = replay(operator_id)
    assert transport.requested == [STATUSES]
    assert result.requests == 1 and result.complete and result.ocpi_ids
    recorded = json.loads((FIXTURES / operator_id / "statuses_page1.json").read_text("utf-8"))
    sent = recorded["response"]["body"]["data"]
    assert set(result.statuses) == {r["id"] for r in sent}
    assert sum(len(e) for e in result.statuses.values()) == sum(len(r["evses"]) for r in sent)


def test_the_token_goes_in_the_header_and_never_in_the_result():
    seen = []

    def server(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), request.headers["authorization"]))
        return httpx.Response(200, json=statuses_body([record("L1", evse("E1"))]))

    with PoliteClient(
        OPERATORS["aldi"], transport=httpx.MockTransport(server), key=FAKE_TOKEN
    ) as client:
        result = eco_movement.fetch_statuses(OPERATORS["aldi"], client, now=NOW)
    assert seen == [(STATUSES, f"Token {FAKE_TOKEN}")]
    assert FAKE_TOKEN not in json.dumps([p.to_exchange() for p in result.modules["statuses"].pages])
    assert result.statuses == {
        "L1": [
            LiveEvse(
                uid="E1", status="available", status_at=datetime(2026, 11, 10, 8, 30, tzinfo=UTC)
            )
        ]
    }


def test_recorded_statuses_are_read_like_the_daily_fetch_reads_them():
    result, _ = replay("aldi")
    counts = Counter(e.status for evses in result.statuses.values() for e in evses)
    assert counts == {"available": 17, "unknown": 2, "out_of_order": 1}
    full = {loc.id.split(":", 3)[-1]: loc for loc in FULL["aldi"].locations}
    assert set(result.statuses) == set(full)
    for location_id, evses in result.statuses.items():
        assert {e.uid for e in evses} == {e.uid for e in full[location_id].evses}


def test_a_status_that_cannot_be_read_is_unknown_and_never_guessed():
    issues = IssueLog()
    read = statuses.from_status_records(
        [
            record("L1", evse("E1", "WORKING"), evse("E2", "CHARGING", at=None), evse("")),
            {"last_updated": "2026-11-10T08:00:00Z", "evses": [evse("E9")]},
            record("L2", evse("E3", "OUTOFORDER", at="0000-00-00T00:00:00Z")),
            "not a record",
        ],
        OPERATORS["aldi"],
        issues,
    )
    at = datetime(2026, 11, 10, 8, 0, tzinfo=UTC)
    assert read == {
        # Not an OCPI status, and no decision in the operator file: unknown.
        "L1": [
            LiveEvse(uid="E1", status="unknown", status_at=at + timedelta(minutes=30)),
            # No time of its own: the location's time stands in, as in the daily fetch.
            LiveEvse(uid="E2", status="charging", status_at=at),
        ],
        "L2": [LiveEvse(uid="E3", status="out_of_order", status_at=at)],
    }
    text = " ".join(issues.lines())
    assert "'WORKING' is not an OCPI 2.2.1 value; recorded as unknown" in text
    assert "it has no uid" in text and "it has no location id (2 times)" in text


def test_the_owners_readings_and_exclusions_apply_to_statuses_too():
    chargy = OPERATORS["chargy"]  # WORKING and FAULTED read by the owner's decision
    read = statuses.from_status_records(
        [record("L1", evse("E1", "WORKING"), evse("E2", "FAULTED"))], chargy, IssueLog()
    )
    assert [e.status for e in read["L1"]] == ["working", "out_of_order"]

    roam = OPERATORS["roam"]
    decision = roam.excluded_locations
    assert decision is not None
    part = next((item for item in decision.locations if item.evse_uids), None)
    if part is None:
        part = decision.locations[0].model_copy(update={"evse_uids": ["E1"]})
        decision = decision.model_copy(update={"locations": [part]})
        roam = roam.model_copy(update={"excluded_locations": decision})
    kept = evse("kept-uid")
    read = statuses.from_status_records(
        [record(part.id, kept, *(evse(uid) for uid in part.evse_uids))], roam, IssueLog()
    )
    assert [e.uid for e in read[part.id]] == ["kept-uid"]


def test_a_second_request_for_statuses_waits_out_the_published_limit():
    """If the endpoint ever pages its answer, the next page keeps "1 request per 30
    seconds" for the token, plus the margin."""
    clock = FakeClock()
    arrivals = []
    pages = [
        httpx.Response(
            200,
            json=statuses_body([record("L1", evse("E1"))]),
            headers={"x-total-count": "2", "link": f'<{STATUSES}?offset=1>; rel="next"'},
        ),
        httpx.Response(
            200, json=statuses_body([record("L2", evse("E2"))]), headers={"x-total-count": "2"}
        ),
    ]

    def server(request: httpx.Request) -> httpx.Response:
        arrivals.append(clock())
        return pages.pop(0)

    config = OPERATORS["ubitricity"]
    with PoliteClient(
        config,
        transport=httpx.MockTransport(server),
        sleep=clock.sleep,
        clock=clock,
        key=FAKE_TOKEN,
    ) as client:
        result = eco_movement.fetch_statuses(config, client, now=NOW)
    assert set(result.statuses) == {"L1", "L2"} and result.complete
    assert arrivals[1] - arrivals[0] >= 30 + LIMIT_MARGIN_SECONDS


def test_the_daily_fetch_refuses_to_stand_in_for_a_status_refresh():
    with (
        PoliteClient(OPERATORS["aldi"], key=FAKE_TOKEN) as client,
        pytest.raises(FeedError, match="statuses endpoint"),
    ):
        eco_movement.fetch(OPERATORS["aldi"], client, statuses_only=True)


# Feeds with no statuses endpoint: the locations module alone

OTHERS = sorted(i for i in REFRESHED if OPERATORS[i].adapter != "eco_movement_pcpr")


def test_every_fixture_operator_with_a_feed_is_refreshed_and_no_sent_copy_is():
    live = {i for i in FULL if OPERATORS[i].sent_copy is None}
    eco_without_recording = {
        i for i in live if i in ECO and not (FIXTURES / i / "statuses_page1.json").exists()
    }
    assert set(REFRESHED) == live - eco_without_recording
    assert {"aldi", "wccc_edgbaston"} <= set(REFRESHED)
    for operator_id in ("connekt", "zest"):
        assert not refresh.refreshable(OPERATORS[operator_id])
        with pytest.raises(FeedError, match="cannot be refreshed"):
            refresh.refresh_operator(OPERATORS[operator_id])


@pytest.mark.parametrize("operator_id", OTHERS)
def test_a_refresh_reads_no_tariff(operator_id):
    result, transport = replay(operator_id)
    config = OPERATORS[operator_id]
    tariff_urls = {pair.tariffs.url for pair in config.more_endpoints}
    if "tariffs" in config.endpoints:
        tariff_urls.add(config.endpoints["tariffs"].url)
    location_urls = {pair.locations.url for pair in config.more_endpoints}
    location_urls.add(config.endpoints["locations"].url)
    for url in transport.requested:
        place = url.split("?")[0]
        if place in location_urls:
            continue  # one address may answer both modules (response_envelope by_module)
        assert not any(place.startswith(tariffs.split("?")[0]) for tariffs in tariff_urls), url
    assert set(result.modules) == {"locations"}
    assert result.requests <= FULL[operator_id].requests


@pytest.mark.parametrize("operator_id", OTHERS)
def test_a_refresh_reads_each_status_exactly_as_the_daily_fetch_does(operator_id):
    full = FULL[operator_id]
    assert REFRESHED[operator_id].statuses == {
        location.id: [
            LiveEvse(uid=e.uid, status=e.status, status_at=e.status_at) for e in location.evses
        ]
        for location in full.locations
    }
    assert REFRESHED[operator_id].dropped_location_ids == full.dropped_location_ids


def test_a_status_refresh_is_never_published_as_map_files(tmp_path):
    config = OPERATORS["geniepoint"].model_copy(update={"relay": None})
    with PoliteClient(
        config, transport=ReplayTransport(FIXTURES / "geniepoint"), sleep=lambda _s: None
    ) as client:
        result = run.ADAPTERS["ocpi_221"](config, client, statuses_only=True)
    assert result.statuses_only and result.tariffs == [] and result.locations
    with pytest.raises(publish.PublishError, match="never published"):
        publish.publish([result], OPERATORS, tmp_path, mode="fixtures", generated_at=NOW)
    assert not FULL["geniepoint"].statuses_only


# Laying statuses over the published map


def test_only_locations_on_the_map_get_a_status():
    result = REFRESHED["wccc_edgbaston"]
    assert len(result.statuses) == 2  # both of the network's locations, as recorded
    shown = shown_for("wccc_edgbaston")
    assert len(shown) == 1  # the fixtures keep one of them
    snapshot, laid = from_statuses(result, OPERATORS["wccc_edgbaston"], shown)
    assert set(snapshot.locations) == set(shown.values())
    assert (laid.locations, laid.evses, laid.not_on_map, laid.not_in_feed) == (1, 6, 1, 0)
    assert snapshot.fetched_at == snapshot.full_fetch_at == result.fetched_at
    config = OPERATORS["wccc_edgbaston"]
    assert snapshot.attribution == " ".join(str(config.attribution).split())
    assert (snapshot.licence, snapshot.licence_url) == (config.licence.name, config.licence.url)


@pytest.mark.parametrize("operator_id", sorted(REFRESHED))
def test_a_refresh_gives_every_mapped_location_of_the_fixtures_a_status(operator_id):
    shown = shown_for(operator_id)
    snapshot, laid = from_statuses(
        REFRESHED[operator_id], OPERATORS[operator_id], shown, partial_ok=True
    )
    assert set(snapshot.locations) == set(shown.values())
    assert laid.not_in_feed == 0 and laid.ambiguous == 0
    LiveSnapshot.model_validate_json(snapshot.model_dump_json())


def test_an_id_two_locations_on_the_map_share_gets_no_status():
    result = REFRESHED["aldi"]
    shown = shown_for("aldi")
    first = next(iter(shown))
    twin = first.replace(":GB:GFX:", ":GB:XXX:")
    assert twin != first
    shown = shown | {twin: location_key(twin)}
    snapshot, laid = from_statuses(result, OPERATORS["aldi"], shown)
    assert laid.ambiguous == 1 and laid.locations == 2
    assert shown[first] not in snapshot.locations and shown[twin] not in snapshot.locations


def test_a_location_the_feed_withdraws_is_left_out_at_once():
    result = REFRESHED["geniepoint"]
    shown = shown_for("geniepoint")
    gone = next(iter(shown))
    withdrawn = statuses.StatusResult(
        operator_id=result.operator_id,
        fetched_at=result.fetched_at,
        modules=result.modules,
        statuses=result.statuses,
        dropped_location_ids=[gone],
    )
    snapshot, laid = from_statuses(withdrawn, OPERATORS["geniepoint"], shown)
    assert shown[gone] not in snapshot.locations
    assert laid.locations == len(shown) - 1


def test_a_refresh_that_did_not_finish_or_is_not_allowed_never_becomes_a_snapshot():
    chargy = REFRESHED["chargy"]  # the fixtures stop after two pages
    assert not chargy.complete
    with pytest.raises(SnapshotError, match="did not finish"):
        from_statuses(chargy, OPERATORS["chargy"], shown_for("chargy"))
    with pytest.raises(SnapshotError, match="not the operator"):
        from_statuses(REFRESHED["aldi"], OPERATORS["jolt"], {})
    off = OPERATORS["aldi"].model_copy(update={"enabled": False})
    with pytest.raises(SnapshotError, match="not switched on"):
        from_statuses(REFRESHED["aldi"], off, shown_for("aldi"))
    copy = statuses.StatusResult(operator_id="zest", fetched_at=NOW, modules={})
    with pytest.raises(SnapshotError, match="copy the operator sent"):
        from_statuses(copy, OPERATORS["zest"], {})


# Keeping each host's gap across runs


def test_a_hosts_cool_down_is_never_less_than_any_recorded_limit_needs():
    configs = [c for c in OPERATORS.values() if refresh.refreshable(c)]
    assert len(configs) >= 44
    for members in run.host_groups(configs):
        wait = refresh.cool_down(members)
        assert wait >= MIN_SECONDS_BETWEEN_REQUESTS
        for config in members:
            assert wait >= config.rate_limit.min_seconds_between_requests
            for limit in config.rate_limit.limits:
                assert wait >= limit.min_interval + LIMIT_MARGIN_SECONDS, config.id
    assert refresh.cool_down([OPERATORS["roam"]]) == required_gap(OPERATORS["roam"]) == 721


def test_a_host_asked_too_recently_is_not_asked_again():
    configs = [OPERATORS[i] for i in ("roam", "chargy", "aldi", "ubitricity", "three_ti")]
    daily = NOW - timedelta(seconds=20)
    waiting = refresh.too_soon(configs, now=NOW, last_contact={}, daily_finished=daily)
    # 20 seconds after the daily fetch: char.gy's 6 seconds have passed, the others' gaps not.
    assert set(waiting) == {"roam", "aldi", "ubitricity", "three_ti"}
    assert waiting["three_ti"] == daily + timedelta(seconds=31)
    assert waiting["roam"] == daily + timedelta(seconds=721)
    assert waiting["aldi"] == waiting["ubitricity"] == daily + timedelta(seconds=125)

    # An hour later nobody waits, unless a refresh of that host finished moments ago:
    # one operator's last contact holds back every operator on its host.
    later = NOW + timedelta(hours=1)
    assert refresh.too_soon(configs, now=later, last_contact={}, daily_finished=daily) == {}
    recent = {"ubitricity": later - timedelta(seconds=100)}
    waiting = refresh.too_soon(configs, now=later, last_contact=recent, daily_finished=daily)
    assert set(waiting) == {"aldi", "ubitricity"}
    assert refresh.too_soon(configs, now=later, last_contact={}, daily_finished=None) == {}

    # It holds the host back even when it is not part of this run.
    alone = [OPERATORS["aldi"]]
    assert refresh.too_soon(alone, now=later, last_contact=recent, daily_finished=None) == {}
    waiting = refresh.too_soon(
        alone,
        now=later,
        last_contact=recent,
        daily_finished=None,
        sharing=list(OPERATORS.values()),
    )
    assert waiting == {"aldi": recent["ubitricity"] + timedelta(seconds=125)}


# The command


@pytest.fixture(scope="module")
def map_dir(tmp_path_factory):
    """Map files published from the fixtures, as the daily fetch would leave them."""
    out = tmp_path_factory.mktemp("map")
    results = list(FULL.values())
    publish.publish(results, OPERATORS, out, mode="fixtures", generated_at=NOW)
    return out


def test_the_command_writes_a_snapshot_for_each_operator_and_a_record(map_dir, tmp_path, capsys):
    assert refresh.main(["--fixtures", "--map", str(map_dir), "--out", str(tmp_path)], now=NOW) == 0
    log = RefreshLog.model_validate_json((tmp_path / "live" / "refresh.json").read_bytes())
    assert set(log.operators) == set(REFRESHED)
    assert log.map_generated_at == NOW and log.generated_at == NOW
    shown = live_snapshot.on_map(map_dir)
    for operator_id, entry in log.operators.items():
        snapshot = LiveSnapshot.model_validate_json(
            (tmp_path / "live" / f"{operator_id}.json").read_bytes()
        )
        assert entry.refreshed and entry.note is None and entry.last_contact_at == NOW
        assert set(snapshot.locations) <= set(shown.keys[operator_id].values())
        assert entry.locations == len(snapshot.locations) > 0
    assert not (tmp_path / "live" / "zest.json").exists()
    assert "of 23 refreshed" in capsys.readouterr().out or len(REFRESHED) != 23


def test_the_command_never_writes_into_the_committed_site(map_dir):
    assert refresh.main(["--fixtures", "--map", str(map_dir), "--out", str(ROOT / "site")]) == 1
    assert not (ROOT / "site" / "live").exists()


def test_the_command_needs_the_published_map(tmp_path, capsys):
    assert refresh.main(["--fixtures", "--map", str(tmp_path), "--out", str(tmp_path)]) == 1
    assert "no published map" in capsys.readouterr().err


def test_a_failed_or_waiting_operator_keeps_its_last_snapshot(map_dir, tmp_path, monkeypatch):
    last, out = tmp_path / "last", tmp_path / "out"
    earlier = NOW - timedelta(hours=1)
    assert refresh.main(["--fixtures", "--map", str(map_dir), "--out", str(last)], now=earlier) == 0
    # The last refresh of Aldi's host finished moments ago, so that host waits.
    log_path = last / "live" / "refresh.json"
    log = RefreshLog.model_validate_json(log_path.read_bytes())
    moments_ago = NOW - timedelta(seconds=30)
    log.operators["aldi"] = log.operators["aldi"].model_copy(
        update={"last_contact_at": moments_ago}
    )
    log_path.write_text(log.model_dump_json(), encoding="utf-8")

    asked = []

    def fake_live(configs, *, max_pages=None):
        asked.extend(config.id for config in configs)
        outcomes = {}
        for config in configs:
            if config.id == "jolt":
                error = FeedError("jolt: the feed returned HTTP 503")
                error.requests = 4
                outcomes[config.id] = error
            elif config.id in REFRESHED:
                outcomes[config.id] = REFRESHED[config.id]
        return outcomes

    monkeypatch.setattr(refresh, "refresh_live", fake_live)
    monkeypatch.setattr(
        live_snapshot,
        "from_statuses",
        lambda result, config, shown, partial_ok=False: from_statuses(
            result, config, shown, partial_ok=True
        ),
    )
    code = refresh.main(
        ["--live", "all", "--map", str(map_dir), "--out", str(out), "--previous", str(last)],
        now=NOW,
    )
    assert code == refresh.EXIT_SOME_FAILED
    # Nobody on Aldi's host was asked, and no sent copy was.
    assert not set(asked) & set(ECO) and not {"connekt", "zest"} & set(asked)
    assert "jolt" in asked and "geniepoint" in asked

    new = RefreshLog.model_validate_json((out / "live" / "refresh.json").read_bytes())
    aldi, jolt, genie = (new.operators[i] for i in ("aldi", "jolt", "geniepoint"))
    assert not aldi.refreshed and "gap had not passed" in aldi.note
    assert aldi.last_contact_at == moments_ago and aldi.fetched_at == earlier
    assert not jolt.refreshed and jolt.note == "failed: jolt: the feed returned HTTP 503"
    assert jolt.requests == 4 and jolt.last_contact_at == NOW and jolt.fetched_at == earlier
    assert genie.refreshed and genie.last_contact_at == NOW
    for operator_id in ("aldi", "jolt"):
        kept = LiveSnapshot.model_validate_json((out / "live" / f"{operator_id}.json").read_bytes())
        before = LiveSnapshot.model_validate_json(
            (last / "live" / f"{operator_id}.json").read_bytes()
        )
        assert kept == before


def test_an_operator_left_out_of_a_run_keeps_its_snapshot_and_its_last_contact(
    map_dir, tmp_path, monkeypatch
):
    last, out = tmp_path / "last", tmp_path / "out"
    earlier = NOW - timedelta(hours=1)
    assert refresh.main(["--fixtures", "--map", str(map_dir), "--out", str(last)], now=earlier) == 0
    monkeypatch.setattr(
        refresh, "refresh_live", lambda configs, max_pages=None: {"aldi": REFRESHED["aldi"]}
    )
    code = refresh.main(
        ["--live", "aldi", "--map", str(map_dir), "--out", str(out), "--previous", str(last)],
        now=NOW,
    )
    assert code == 0
    new = RefreshLog.model_validate_json((out / "live" / "refresh.json").read_bytes())
    assert set(new.operators) == set(REFRESHED)
    assert new.operators["aldi"].refreshed and new.operators["aldi"].last_contact_at == NOW
    for operator_id in ("wccc_edgbaston", "jolt"):
        entry = new.operators[operator_id]
        assert not entry.refreshed and entry.note == "not asked: not part of this run"
        assert entry.last_contact_at == earlier and entry.fetched_at == earlier
        assert (out / "live" / f"{operator_id}.json").read_bytes() == (
            last / "live" / f"{operator_id}.json"
        ).read_bytes()

    # The next run still knows when that host was last asked.
    waiting = refresh.too_soon(
        [OPERATORS["wccc_edgbaston"]],
        now=NOW + timedelta(seconds=60),
        last_contact={i: e.last_contact_at for i, e in new.operators.items()},
        daily_finished=None,
        sharing=list(OPERATORS.values()),
    )
    assert waiting == {"wccc_edgbaston": NOW + timedelta(seconds=125)}


def test_a_refresh_entry_says_when_there_is_no_snapshot_at_all():
    entry = RefreshEntry(fetched_at=None, last_contact_at=None, refreshed=False, note="failed: x")
    assert entry.locations == 0 and entry.requests is None
