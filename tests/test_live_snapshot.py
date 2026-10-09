"""Live status snapshots for the Phase 3 Worker (pipeline/live_snapshot.py, ADR 0011)."""

import json
import re
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from adapters.ocpi_221 import AdapterResult, convert_records
from adapters.ocpi_221.normalise import IssueLog, location_record_id
from pipeline import live_snapshot
from pipeline.health import in_uk
from pipeline.live_snapshot import SnapshotError, build, merge
from pipeline.publish import OUT_OF_SERVICE, location_key
from pipeline.registry import ROOT, load_registry
from pipeline.run import run_fixtures
from schema.live import LiveSnapshot

OPERATORS = load_registry()
RESULTS = {r.operator_id: r for r in run_fixtures(OPERATORS)}
CHARGY_PAGE = ROOT / "tests" / "fixtures" / "chargy" / "locations_page1.json"


def snapshot_of(operator_id: str) -> LiveSnapshot:
    # The char.gy fixtures stop after two pages on purpose, so they count as partial.
    return build(RESULTS[operator_id], OPERATORS[operator_id], partial_ok=True)


def raw_chargy_location() -> dict:
    return json.loads(CHARGY_PAGE.read_text(encoding="utf-8"))["response"]["body"]["data"][0]


def changes_from(raw_locations: list[dict], *, after: LiveSnapshot) -> AdapterResult:
    """What a fetch of changes would give: the records converted as the adapter does."""
    full = RESULTS["chargy"]
    result = AdapterResult(
        operator_id="chargy",
        fetched_at=after.fetched_at + timedelta(minutes=60),
        modules={name: replace(m, complete=True) for name, m in full.modules.items()},
    )
    convert_records(
        OPERATORS["chargy"], result, locations=raw_locations, tariffs=[], issues=IssueLog()
    )
    return result


@pytest.mark.parametrize("operator_id", sorted(RESULTS))
def test_a_snapshot_has_every_mapped_location_under_its_detail_file_key(operator_id):
    result = RESULTS[operator_id]
    snapshot = snapshot_of(operator_id)
    mapped = {location_key(loc.id): loc for loc in result.locations if in_uk(loc)}
    assert snapshot.operator == operator_id
    assert snapshot.fetched_at == snapshot.full_fetch_at == result.fetched_at
    assert set(snapshot.locations) == set(mapped)
    for key, evses in snapshot.locations.items():
        assert [(e.uid, e.status, e.status_at) for e in evses] == [
            (e.uid, e.status, e.status_at) for e in mapped[key].evses
        ]


@pytest.mark.parametrize("operator_id", sorted(RESULTS))
def test_a_snapshot_carries_the_operators_attribution_and_licence(operator_id):
    config = OPERATORS[operator_id]
    snapshot = snapshot_of(operator_id)
    assert snapshot.attribution == " ".join(str(config.attribution).split())
    assert snapshot.licence == config.licence.name
    assert snapshot.licence_url == config.licence.url


def test_a_fetch_that_did_not_finish_never_becomes_a_snapshot():
    assert not RESULTS["chargy"].complete
    with pytest.raises(SnapshotError, match="did not finish"):
        build(RESULTS["chargy"], OPERATORS["chargy"])
    assert RESULTS["geniepoint"].complete
    build(RESULTS["geniepoint"], OPERATORS["geniepoint"])


def test_only_switched_on_operators_get_a_snapshot():
    off = OPERATORS["geniepoint"].model_copy(update={"enabled": False})
    with pytest.raises(SnapshotError, match="not switched on"):
        build(RESULTS["geniepoint"], off)
    with pytest.raises(SnapshotError, match="not the operator"):
        build(RESULTS["jolt"], OPERATORS["geniepoint"])


def test_a_snapshot_round_trips_through_its_published_form(tmp_path):
    snapshot = snapshot_of("geniepoint")
    path = live_snapshot.write(snapshot, tmp_path)
    assert path == tmp_path / "live" / "geniepoint.json"
    assert LiveSnapshot.model_validate_json(path.read_text(encoding="utf-8")) == snapshot


def test_the_record_id_for_a_dropped_location_matches_the_kept_one():
    raw = raw_chargy_location()
    kept = changes_from([raw], after=snapshot_of("chargy")).locations[0]
    assert location_record_id(raw, OPERATORS["chargy"]) == kept.id
    assert location_record_id({"publish": True}, OPERATORS["chargy"]) is None


def test_changes_replace_their_locations_and_keep_the_rest():
    previous = snapshot_of("chargy")
    raw = raw_chargy_location()
    raw["evses"][0]["status"] = "CHARGING"
    merged = merge(previous, changes_from([raw], after=previous), OPERATORS["chargy"])
    key = location_key(location_record_id(raw, OPERATORS["chargy"]))
    assert merged.fetched_at == previous.fetched_at + timedelta(minutes=60)
    assert merged.full_fetch_at == previous.full_fetch_at
    assert [e.status for e in merged.locations[key]] == ["charging"]
    assert {k: v for k, v in merged.locations.items() if k != key} == {
        k: v for k, v in previous.locations.items() if k != key
    }


def test_a_location_whose_publish_flag_turns_false_is_removed_at_once():
    previous = snapshot_of("chargy")
    raw = {**raw_chargy_location(), "publish": False}
    key = location_key(location_record_id(raw, OPERATORS["chargy"]))
    assert key in previous.locations
    changes = changes_from([raw], after=previous)
    assert changes.locations == []
    merged = merge(previous, changes, OPERATORS["chargy"])
    assert key not in merged.locations
    assert len(merged.locations) == len(previous.locations) - 1


def test_a_location_that_can_no_longer_be_read_or_mapped_is_removed():
    previous = snapshot_of("chargy")
    unreadable = {**raw_chargy_location(), "coordinates": None}
    key = location_key(location_record_id(unreadable, OPERATORS["chargy"]))
    merged = merge(previous, changes_from([unreadable], after=previous), OPERATORS["chargy"])
    assert key not in merged.locations

    abroad = raw_chargy_location()
    abroad["coordinates"] = {"latitude": "48.8566", "longitude": "2.3522"}  # Paris
    merged = merge(previous, changes_from([abroad], after=previous), OPERATORS["chargy"])
    assert key not in merged.locations


def test_changes_that_are_partial_older_or_from_another_operator_are_refused():
    previous = snapshot_of("chargy")
    changes = changes_from([raw_chargy_location()], after=previous)
    with pytest.raises(SnapshotError, match="did not finish"):
        merge(previous, replace(changes, modules=RESULTS["chargy"].modules), OPERATORS["chargy"])
    with pytest.raises(SnapshotError, match="not newer"):
        merge(previous, replace(changes, fetched_at=previous.fetched_at), OPERATORS["chargy"])
    with pytest.raises(SnapshotError, match="cannot merge"):
        merge(snapshot_of("jolt"), changes, OPERATORS["chargy"])


def test_snapshots_are_never_written_into_the_committed_site():
    with pytest.raises(SnapshotError, match="site/"):
        live_snapshot.write(snapshot_of("jolt"), ROOT / "site")


def test_the_command_writes_one_file_per_fixture_operator(tmp_path):
    assert live_snapshot.main(["--fixtures", "--out", str(tmp_path)]) == 0
    written = sorted(p.stem for p in Path(tmp_path, "live").glob("*.json"))
    assert written == sorted(RESULTS)
    for name in written:
        LiveSnapshot.model_validate_json((tmp_path / "live" / f"{name}.json").read_text("utf-8"))


def test_the_worker_serves_only_operators_switched_on_in_the_registry():
    source = (ROOT / "proxy" / "worker.js").read_text(encoding="utf-8")
    listed = re.search(r"export const OPERATORS = \[([^\]]*)\]", source)
    assert listed, "proxy/worker.js must list its operators in OPERATORS"
    for operator_id in re.findall(r'"([a-z0-9_]+)"', listed.group(1)):
        assert OPERATORS[operator_id].enabled, f"{operator_id} is not switched on"


def test_the_worker_never_fetches_from_operators():
    source = (ROOT / "proxy" / "worker.js").read_text(encoding="utf-8")
    assert "fetch(" not in source.replace("async fetch(request, env)", "")


def test_the_details_screen_groups_out_of_service_like_the_map_filter():
    """live.js's "out" group must match the statuses the "Hide out of service" filter uses."""
    source = (ROOT / "site" / "assets" / "js" / "live.js").read_text(encoding="utf-8")
    out = re.search(r"out: \{[^}]*statuses: \[([^\]]*)\]", source)
    assert out, "site/assets/js/live.js must list the out group's statuses"
    assert set(re.findall(r'"([a-z_]+)"', out.group(1))) == OUT_OF_SERVICE
