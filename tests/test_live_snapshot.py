"""Live status snapshots for the Phase 3 Worker (pipeline/live_snapshot.py, ADR 0011)."""

import json
import re
from dataclasses import replace
from datetime import timedelta
from pathlib import Path

import pytest

from pipeline import live_snapshot
from pipeline.health import in_uk
from pipeline.live_snapshot import SnapshotError, build, merge
from pipeline.publish import OUT_OF_SERVICE, location_key
from pipeline.registry import ROOT, load_registry
from pipeline.run import run_fixtures
from schema.live import LiveSnapshot

OPERATORS = load_registry()
RESULTS = {r.operator_id: r for r in run_fixtures(OPERATORS)}


@pytest.mark.parametrize("operator_id", sorted(RESULTS))
def test_a_snapshot_has_every_mapped_location_under_its_detail_file_key(operator_id):
    result = RESULTS[operator_id]
    snapshot = build(result)
    mapped = {location_key(loc.id): loc for loc in result.locations if in_uk(loc)}
    assert snapshot.operator == operator_id
    assert snapshot.fetched_at == snapshot.full_fetch_at == result.fetched_at
    assert set(snapshot.locations) == set(mapped)
    for key, evses in snapshot.locations.items():
        assert [(e.uid, e.status, e.status_at) for e in evses] == [
            (e.uid, e.status, e.status_at) for e in mapped[key].evses
        ]


def test_a_snapshot_round_trips_through_its_published_form(tmp_path):
    snapshot = build(RESULTS["geniepoint"])
    path = live_snapshot.write(snapshot, tmp_path)
    assert path == tmp_path / "live" / "geniepoint.json"
    assert LiveSnapshot.model_validate_json(path.read_text(encoding="utf-8")) == snapshot


def test_changes_replace_their_locations_and_keep_the_rest():
    full = RESULTS["chargy"]
    previous = build(full)
    changed = full.locations[0]
    evse = changed.evses[0].model_copy(update={"status": "charging"})
    later = full.fetched_at + timedelta(minutes=30)
    changes = replace(
        full, fetched_at=later, locations=[changed.model_copy(update={"evses": [evse]})]
    )
    merged = merge(previous, changes)
    key = location_key(changed.id)
    assert merged.fetched_at == later
    assert merged.full_fetch_at == previous.full_fetch_at
    assert [e.status for e in merged.locations[key]] == ["charging"]
    assert {k: v for k, v in merged.locations.items() if k != key} == {
        k: v for k, v in previous.locations.items() if k != key
    }


def test_changes_from_another_operator_or_from_earlier_are_refused():
    previous = build(RESULTS["chargy"])
    with pytest.raises(SnapshotError, match="cannot merge"):
        merge(previous, RESULTS["jolt"])
    earlier = replace(RESULTS["chargy"], fetched_at=previous.fetched_at - timedelta(seconds=1))
    with pytest.raises(SnapshotError, match="older"):
        merge(previous, earlier)


def test_snapshots_are_never_written_into_the_committed_site():
    with pytest.raises(SnapshotError, match="site/"):
        live_snapshot.write(build(RESULTS["jolt"]), ROOT / "site")


def test_the_command_writes_one_file_per_fixture_operator(tmp_path, capsys):
    assert live_snapshot.main(["--fixtures", "--out", str(tmp_path)]) == 0
    written = sorted(p.stem for p in Path(tmp_path, "live").glob("*.json"))
    assert written == sorted(RESULTS)
    for name in written:
        json.loads((tmp_path / "live" / f"{name}.json").read_text(encoding="utf-8"))


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
