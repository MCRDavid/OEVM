"""The status files the site serves between daily fetches (ADR 0032).

    uv run python -m pipeline.live_site --map build [--live DIR]

Reads the snapshots a status refresh wrote (DIR/live/<operator>.json, pipeline.refresh)
and writes, under build/data/live/:

- <shard>.json, for each of the 256 two-character beginnings of a location key: the
  statuses of the locations whose key starts with it (schema.live.LiveShard). The
  details screen reads the one file for the charger that was opened. Every file is
  written, empty or not, so the page never asks for one that is missing.
- index.json: which operators' statuses are in the files, when each was read, and its
  attribution and licence (schema.live.LiveIndex).

Rules:
- Only statuses newer than the map files are served. An operator's snapshot is left out
  when it was not read after that operator's data on the map (data/manifest.json), so
  after each daily fetch the detail files' own statuses stand until the next refresh.
- Only locations the map shows, and only operators that are on the map, switched on in
  the registry and fetched from a feed. A copy an operator sent has no statuses (ADR 0029).
- A snapshot that cannot be read is left out and named in index.json; the site is still
  built, with the statuses of the daily fetch.
- Without --live, or with no snapshot newer than the map, the files are written empty.
- Never writes into the committed site/ folder.
"""

import argparse
import shutil
import sys
from datetime import UTC, datetime
from pathlib import Path

from pydantic import ValidationError

from pipeline import live_snapshot
from pipeline.live_snapshot import OnMap, SnapshotError
from pipeline.publish import _dump, _validated
from pipeline.registry import ROOT, RegistryError, load_registry
from schema.live import LiveIndex, LiveIndexEntry, LiveLocation, LiveShard, LiveSnapshot
from schema.operator import OperatorConfig
from schema.published import Manifest

# The first two characters of a location key, as for data/loc/<shard>/<key>.json.
SHARDS = [f"{number:02x}" for number in range(256)]
NOT_NEWER = "not read since this operator's data on the map"


def _manifest(build_dir: Path) -> Manifest:
    path = build_dir / "data" / "manifest.json"
    try:
        return Manifest.model_validate_json(path.read_bytes())
    except FileNotFoundError:
        raise SnapshotError(f"no published map at {path}") from None
    except ValidationError as exc:
        raise SnapshotError(f"{path} is not the map's manifest: {exc}") from None


def read_snapshots(live_dir: Path | None) -> tuple[list[LiveSnapshot], dict[str, str]]:
    """The snapshots in live_dir/live, and the files that could not be read, by operator."""
    snapshots: list[LiveSnapshot] = []
    unread: dict[str, str] = {}
    if live_dir is None:
        return snapshots, unread
    for path in sorted((live_dir / "live").glob("*.json")):
        if path.name == "refresh.json":
            continue
        try:
            snapshot = LiveSnapshot.model_validate_json(path.read_bytes())
        except ValidationError as exc:
            unread[path.stem] = f"could not be read: {str(exc).splitlines()[0]}"
            continue
        if snapshot.operator != path.stem:
            unread[path.stem] = f"could not be read: it names the operator {snapshot.operator}"
            continue
        snapshots.append(snapshot)
    return snapshots, unread


def pack(
    snapshots: list[LiveSnapshot],
    operators: dict[str, OperatorConfig],
    build_dir: Path,
    *,
    generated_at: datetime,
    unread: dict[str, str] | None = None,
) -> LiveIndex:
    """Write the status files for the map files in build_dir, and return their index."""
    if build_dir.resolve() == (ROOT / "site").resolve():
        raise SnapshotError("write to a build folder, not the committed site/ folder")
    shown: OnMap = live_snapshot.on_map(build_dir)
    manifest = _manifest(build_dir)
    shards: dict[str, dict[str, LiveLocation]] = {shard: {} for shard in SHARDS}
    entries: dict[str, LiveIndexEntry] = {}
    left_out = dict(unread or {})
    for snapshot in sorted(snapshots, key=lambda s: s.operator):
        operator_id = snapshot.operator
        config = operators.get(operator_id)
        on_map = manifest.operators.get(operator_id)
        keys = set(shown.keys.get(operator_id, {}).values())
        if config is None or not config.enabled or config.licence is None:
            left_out[operator_id] = "not switched on in the registry"
        elif config.sent_copy is not None:
            left_out[operator_id] = "a copy the operator sent has no statuses to refresh"
        elif on_map is None or not keys:
            left_out[operator_id] = "not on the map"
        elif snapshot.fetched_at <= on_map.fetched_at:
            left_out[operator_id] = NOT_NEWER
        else:
            kept = {key: evses for key, evses in snapshot.locations.items() if key in keys}
            if not kept:
                left_out[operator_id] = "none of its locations are on the map"
                continue
            for key, evses in kept.items():
                shards[key[:2]][key] = LiveLocation(
                    operator=operator_id, fetched_at=snapshot.fetched_at, evses=evses
                )
            entries[operator_id] = LiveIndexEntry(
                fetched_at=snapshot.fetched_at,
                locations=len(kept),
                evses=sum(len(evses) for evses in kept.values()),
                # Today's words from the registry, as the map files use.
                attribution=" ".join(str(config.attribution).split()),
                licence=config.licence.name,
                licence_url=config.licence.url,
            )
    index = LiveIndex(
        generated_at=generated_at,
        map_generated_at=shown.generated_at,
        operators=entries,
        left_out=dict(sorted(left_out.items())),
    )
    blobs = {
        f"{shard}.json": _validated(
            LiveShard, _dump(LiveShard(generated_at=generated_at, locations=locations))
        )
        for shard, locations in shards.items()
    }
    blobs["index.json"] = _validated(LiveIndex, _dump(index, indent=1))
    folder = build_dir / "data" / "live"
    shutil.rmtree(folder, ignore_errors=True)  # no status outlives the files it came with
    folder.mkdir(parents=True)
    for name, blob in blobs.items():
        (folder / name).write_bytes(blob)
    return index


def ensure(build_dir: Path, *, generated_at: datetime | None = None) -> bool:
    """Write empty status files where a build has map files and no status files, so the
    page finds every file it asks for. Returns whether it wrote them."""
    data = build_dir / "data"
    if (data / "live" / "index.json").exists() or not (data / "locations.geojson").exists():
        return False
    pack([], {}, build_dir, generated_at=generated_at or datetime.now(UTC).replace(microsecond=0))
    return True


def main(argv: list[str] | None = None, *, now: datetime | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m pipeline.live_site", description=__doc__)
    parser.add_argument("--map", type=Path, required=True, help="build folder with DIR/data")
    parser.add_argument("--live", type=Path, help="a status refresh's files (DIR/live)")
    args = parser.parse_args(argv)
    try:
        snapshots, unread = read_snapshots(args.live)
        index = pack(
            snapshots,
            load_registry(),
            args.map,
            generated_at=now or datetime.now(UTC).replace(microsecond=0),
            unread=unread,
        )
    except (SnapshotError, RegistryError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    for operator_id, entry in index.operators.items():
        print(
            f"{operator_id}: {entry.locations:,} locations, {entry.evses:,} EVSEs, "
            f"read {entry.fetched_at:%Y-%m-%d %H:%M:%S} UTC"
        )
    for operator_id, reason in index.left_out.items():
        print(f"{operator_id}: left out, {reason}")
    print(f"{len(index.operators)} operators' statuses in {args.map / 'data' / 'live'}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
