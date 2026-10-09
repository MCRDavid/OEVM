"""Build live status snapshots for the Phase 3 Worker (docs/PHASE3_PLAN.md, ADR 0011).

    uv run python -m pipeline.live_snapshot --fixtures --out build

Writes build/live/<operator>.json from the recorded fixtures: the status of every EVSE at
every location the map shows, keyed like the map's detail files. Groundwork only: no
workflow runs this yet, it never contacts a feed and it never sends a snapshot anywhere.

A full fetch gives a whole snapshot (build). Later, a fetch of only the locations that
changed since the last one (OCPI date_from) is laid over the previous snapshot (merge),
so a refresh needs a few requests rather than the whole network.
"""

import argparse
import sys
from pathlib import Path

from adapters.ocpi_221 import AdapterResult
from pipeline.health import in_uk
from pipeline.publish import location_key
from pipeline.registry import ROOT, load_registry
from pipeline.run import run_fixtures
from schema.live import LiveEvse, LiveSnapshot


class SnapshotError(Exception):
    """A snapshot cannot be built or merged as asked."""


def _statuses(result: AdapterResult) -> dict[str, list[LiveEvse]]:
    """EVSE statuses for the locations the map would show, by location key."""
    out: dict[str, list[LiveEvse]] = {}
    for location in sorted(result.locations, key=lambda loc: loc.id):
        if not in_uk(location):
            continue
        key = location_key(location.id)
        if key in out:
            raise SnapshotError(f"two locations share the key {key}")
        out[key] = [
            LiveEvse(uid=evse.uid, status=evse.status, status_at=evse.status_at)
            for evse in location.evses
        ]
    return out


def build(result: AdapterResult) -> LiveSnapshot:
    """A whole snapshot from a full fetch of one operator."""
    return LiveSnapshot(
        operator=result.operator_id,
        fetched_at=result.fetched_at,
        full_fetch_at=result.fetched_at,
        locations=_statuses(result),
    )


def merge(previous: LiveSnapshot, changes: AdapterResult) -> LiveSnapshot:
    """Lay a fetch of changed locations over the previous snapshot.

    Locations in the changes replace their earlier entry. Locations that have since
    disappeared from the feed, or lost their publish flag, stay until the next full fetch
    replaces the whole snapshot, so a full fetch must still run at least daily.
    """
    if changes.operator_id != previous.operator:
        raise SnapshotError(f"cannot merge {changes.operator_id} into {previous.operator}")
    if changes.fetched_at < previous.fetched_at:
        raise SnapshotError("the changes are older than the snapshot")
    return LiveSnapshot(
        operator=previous.operator,
        fetched_at=changes.fetched_at,
        full_fetch_at=previous.full_fetch_at,
        locations={**previous.locations, **_statuses(changes)},
    )


def write(snapshot: LiveSnapshot, out_dir: Path) -> Path:
    if out_dir.resolve() == (ROOT / "site").resolve():
        raise SnapshotError("write to a build folder, not the committed site/ folder")
    path = out_dir / "live" / f"{snapshot.operator}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(snapshot.model_dump_json(), encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.live_snapshot", description=__doc__)
    parser.add_argument("--fixtures", action="store_true", required=True, help="replay fixtures")
    parser.add_argument("--out", type=Path, required=True, help="build folder (never site/)")
    args = parser.parse_args(argv)

    for result in run_fixtures(load_registry()):
        try:
            path = write(build(result), args.out)
        except SnapshotError as error:
            print(f"{result.operator_id}: {error}", file=sys.stderr)
            return 1
        print(f"{result.operator_id}: {path} ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
