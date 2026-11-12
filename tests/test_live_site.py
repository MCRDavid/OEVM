"""The status files the site serves between daily fetches (pipeline/live_site.py, ADR 0032).

Built from the recorded fixtures only; nothing here touches the network.
"""

import json
import shutil
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from pipeline import build_site, live_site, live_snapshot, publish, refresh, run
from pipeline.live_snapshot import SnapshotError
from pipeline.registry import ROOT, load_registry
from schema.live import LiveEvse, LiveIndex, LiveShard, LiveSnapshot

OPERATORS = load_registry()
MAP_TIME = datetime(2026, 11, 12, 4, 17, tzinfo=UTC)
REFRESHED = MAP_TIME + timedelta(hours=5)
PACKED = REFRESHED + timedelta(minutes=10)


@pytest.fixture(scope="module")
def published(tmp_path_factory):
    """Map files as a daily fetch at MAP_TIME would leave them, and a refresh at REFRESHED."""
    folder = tmp_path_factory.mktemp("published")
    results = [replace(result, fetched_at=MAP_TIME) for result in run.run_fixtures(OPERATORS)]
    publish.publish(results, OPERATORS, folder / "map", mode="fixtures", generated_at=MAP_TIME)
    arguments = ["--fixtures", "--map", str(folder / "map"), "--out", str(folder / "refresh")]
    assert refresh.main(arguments, now=REFRESHED) == 0
    return folder


@pytest.fixture
def build(published, tmp_path):
    """A copy of the map files that a test may write status files into."""
    shutil.copytree(published / "map", tmp_path / "build")
    return tmp_path / "build"


@pytest.fixture
def snapshots(published):
    found, unread = live_site.read_snapshots(published / "refresh")
    assert unread == {} and len(found) >= 23
    return found


def shards(build) -> dict[str, LiveShard]:
    folder = build / "data" / "live"
    return {
        path.stem: LiveShard.model_validate_json(path.read_bytes())
        for path in folder.glob("*.json")
        if path.name != "index.json"
    }


def index_of(build) -> LiveIndex:
    return LiveIndex.model_validate_json((build / "data" / "live" / "index.json").read_bytes())


def test_every_shard_is_written_and_a_location_is_in_the_one_its_key_starts_with(build, snapshots):
    index = live_site.pack(snapshots, OPERATORS, build, generated_at=PACKED)
    files = shards(build)
    assert sorted(files) == live_site.SHARDS and len(files) == 256
    assert index == index_of(build) and index.left_out == {}
    assert index.generated_at == PACKED and index.map_generated_at == MAP_TIME
    shown = live_snapshot.on_map(build)
    served = {}
    for shard, file in files.items():
        assert file.generated_at == PACKED
        for key, location in file.locations.items():
            assert key.startswith(shard)
            # The same folder as the location's detail file.
            assert (build / "data" / "loc" / shard / f"{key}.json").exists()
            assert location.fetched_at == REFRESHED
            served[key] = location
    for snapshot in snapshots:
        entry = index.operators[snapshot.operator]
        assert entry.fetched_at == REFRESHED
        assert entry.locations == len(snapshot.locations) > 0
        assert entry.evses == sum(len(evses) for evses in snapshot.locations.values())
        config = OPERATORS[snapshot.operator]
        assert entry.attribution == " ".join(str(config.attribution).split())
        assert (entry.licence, entry.licence_url) == (config.licence.name, config.licence.url)
        for key, evses in snapshot.locations.items():
            assert key in shown.keys[snapshot.operator].values()
            assert served[key].operator == snapshot.operator and served[key].evses == evses
    assert len(served) == sum(entry.locations for entry in index.operators.values())


def test_statuses_no_newer_than_the_map_are_not_served(build, snapshots):
    """After a daily fetch the detail files' own statuses stand until the next refresh."""
    stale = [
        snapshot.model_copy(update={"fetched_at": MAP_TIME, "full_fetch_at": MAP_TIME})
        if snapshot.operator in ("aldi", "jolt")
        else snapshot
        for snapshot in snapshots
    ]
    older = MAP_TIME - timedelta(hours=1)
    stale = [
        s.model_copy(update={"fetched_at": older, "full_fetch_at": older})
        if s.operator == "roam"
        else s
        for s in stale
    ]
    index = live_site.pack(stale, OPERATORS, build, generated_at=PACKED)
    assert index.left_out == dict.fromkeys(("aldi", "jolt", "roam"), live_site.NOT_NEWER)
    assert not {"aldi", "jolt", "roam"} & set(index.operators)
    served = {loc.operator for file in shards(build).values() for loc in file.locations.values()}
    assert served == set(index.operators) and "geniepoint" in served


def test_an_operator_whose_fetch_failed_keeps_statuses_newer_than_its_kept_copy(build, snapshots):
    """The map's copy of a failed operator keeps its older fetch time (ADR 0018), so a
    refresh read after that copy is still the newest there is."""
    path = build / "data" / "manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    kept_at = (MAP_TIME - timedelta(days=2)).isoformat().replace("+00:00", "Z")
    manifest["operators"]["jolt"] |= {"fetched_at": kept_at, "kept_from_previous": True}
    path.write_text(json.dumps(manifest), encoding="utf-8")
    between = MAP_TIME - timedelta(days=1)
    jolt = next(s for s in snapshots if s.operator == "jolt")
    jolt = jolt.model_copy(update={"fetched_at": between, "full_fetch_at": between})
    index = live_site.pack([jolt], OPERATORS, build, generated_at=PACKED)
    assert index.operators["jolt"].fetched_at == between


def test_only_operators_and_locations_on_the_map_are_served(build, snapshots):
    aldi = next(s for s in snapshots if s.operator == "aldi")
    stray = "0123456789abcdef"
    evses = [LiveEvse(uid="E1", status="available", status_at=REFRESHED)]
    assert stray not in aldi.locations
    with_stray = aldi.model_copy(update={"locations": aldi.locations | {stray: evses}})
    only_stray = next(s for s in snapshots if s.operator == "jolt").model_copy(
        update={"locations": {stray: evses}}
    )
    # Gridserve is in the registry and not on the map; Zest is on the map as a sent copy.
    assert not OPERATORS["gridserve"].enabled and OPERATORS["zest"].sent_copy is not None

    def made_up(operator_id: str) -> LiveSnapshot:
        return aldi.model_copy(update={"operator": operator_id})

    index = live_site.pack(
        [with_stray, only_stray, made_up("gridserve"), made_up("zest"), made_up("no_such")],
        OPERATORS,
        build,
        generated_at=PACKED,
    )
    assert set(index.operators) == {"aldi"}
    assert index.operators["aldi"].locations == len(aldi.locations)
    assert index.left_out == {
        "gridserve": "not switched on in the registry",
        "jolt": "none of its locations are on the map",
        "no_such": "not switched on in the registry",
        "zest": "a copy the operator sent has no statuses to refresh",
    }
    assert all(stray not in file.locations for file in shards(build).values())

    off = OPERATORS | {"aldi": OPERATORS["aldi"].model_copy(update={"enabled": False})}
    index = live_site.pack([aldi], off, build, generated_at=PACKED)
    assert index.operators == {} and index.left_out == {"aldi": "not switched on in the registry"}


def test_an_operator_no_longer_on_the_map_is_left_out(build, snapshots):
    path = build / "data" / "manifest.json"
    manifest = json.loads(path.read_text("utf-8"))
    del manifest["operators"]["jolt"]
    path.write_text(json.dumps(manifest), encoding="utf-8")
    jolt = next(s for s in snapshots if s.operator == "jolt")
    index = live_site.pack([jolt], OPERATORS, build, generated_at=PACKED)
    assert index.operators == {} and index.left_out == {"jolt": "not on the map"}


def test_a_snapshot_that_cannot_be_read_is_left_out_and_named(published, build, tmp_path, capsys):
    live = tmp_path / "refresh"
    shutil.copytree(published / "refresh", live)
    (live / "live" / "jolt.json").write_text("{not json", encoding="utf-8")
    aldi = json.loads((live / "live" / "aldi.json").read_text("utf-8"))
    (live / "live" / "roam.json").write_text(json.dumps(aldi), encoding="utf-8")
    assert live_site.main(["--map", str(build), "--live", str(live)], now=PACKED) == 0
    index = index_of(build)
    assert index.left_out["jolt"].startswith("could not be read: ")
    assert index.left_out["roam"] == "could not be read: it names the operator aldi"
    assert "aldi" in index.operators and not {"jolt", "roam"} & set(index.operators)
    out = capsys.readouterr().out
    assert "jolt: left out, could not be read" in out
    # The run's own record is not a snapshot.
    assert "refresh" not in index.left_out and "refresh" not in index.operators


def test_old_status_files_never_outlive_a_new_packing(build, snapshots):
    live_site.pack(snapshots, OPERATORS, build, generated_at=PACKED)
    assert any(file.locations for file in shards(build).values())
    later = PACKED + timedelta(hours=1)
    assert live_site.main(["--map", str(build)], now=later) == 0
    files = shards(build)
    assert len(files) == 256 and all(not file.locations for file in files.values())
    assert all(file.generated_at == later for file in files.values())
    assert index_of(build).operators == {}


def test_the_site_build_adds_empty_status_files_only_where_there_are_none(build, snapshots):
    assert live_site.ensure(build, generated_at=PACKED)
    assert len(shards(build)) == 256 and index_of(build).operators == {}
    assert not live_site.ensure(build, generated_at=PACKED)

    live_site.pack(snapshots, OPERATORS, build, generated_at=PACKED)
    before = index_of(build)
    assert not live_site.ensure(build)
    assert index_of(build) == before and before.operators


def test_a_build_without_map_files_gets_no_status_files(tmp_path):
    assert not live_site.ensure(tmp_path)
    assert not (tmp_path / "data").exists()
    with pytest.raises(SnapshotError, match="no published map"):
        live_site.pack([], OPERATORS, tmp_path, generated_at=PACKED)
    assert live_site.main(["--map", str(tmp_path)]) == 1


def test_status_files_are_never_written_into_the_committed_site(snapshots):
    with pytest.raises(SnapshotError, match="not the committed site"):
        live_site.pack(snapshots, OPERATORS, ROOT / "site", generated_at=PACKED)
    assert not (ROOT / "site" / "data" / "live").exists()


def test_build_site_calls_for_the_status_files(monkeypatch, build):
    """pipeline.build_site gives every built site its status files."""
    calls = []
    monkeypatch.setattr(live_site, "ensure", lambda out: calls.append(out) or True)
    monkeypatch.setattr(
        build_site, "_package", lambda name: {"version": build_site.MAPLIBRE_VERSION}
    )
    monkeypatch.setattr(build_site.shutil, "copy2", lambda *args: None)
    monkeypatch.setattr(build_site, "third_party_notices", lambda: "")
    lines = build_site.build(build)
    assert calls == [build]
    assert lines[-1].startswith("added empty status files")
