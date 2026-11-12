"""Build live status snapshots for the Phase 3 Worker (docs/PHASE3_PLAN.md, ADR 0015).

    uv run python -m pipeline.live_snapshot --fixtures --out build

Writes build/live/<operator>.json from the recorded fixtures: the status of every EVSE at
every location the map shows, keyed like the map's detail files, with the operator's
attribution and licence. Groundwork only: no workflow runs this yet, it never contacts a
feed and it never sends a snapshot anywhere.

A full fetch gives a whole snapshot (build). Later, a fetch of only the locations that
changed since the last one (OCPI date_from) is laid over the previous snapshot (merge),
so a refresh fetches the changes rather than the whole network.

A status refresh (adapters.statuses, pipeline.refresh) gives a snapshot too
(from_statuses): only for locations the published map already shows (on_map), because a
status is laid over a location the daily fetch published, with its checks, and never
adds one.
"""

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from adapters.ocpi_221 import AdapterResult
from adapters.statuses import StatusResult
from pipeline.health import in_uk
from pipeline.publish import location_key
from pipeline.registry import ROOT, load_registry
from pipeline.run import run_fixtures
from schema.live import LiveEvse, LiveSnapshot
from schema.models import Location
from schema.operator import OperatorConfig


class SnapshotError(Exception):
    """A snapshot cannot be built or merged as asked."""


def _evses(location: Location) -> list[LiveEvse]:
    return [
        LiveEvse(uid=evse.uid, status=evse.status, status_at=evse.status_at)
        for evse in location.evses
    ]


def _check(result: AdapterResult, config: OperatorConfig, *, partial_ok: bool = False) -> None:
    if result.operator_id != config.id:
        raise SnapshotError(f"{result.operator_id}: not the operator {config.id}")
    if not config.enabled or config.licence is None:
        raise SnapshotError(f"{config.id} is not switched on in the registry")
    if not result.complete and not partial_ok:
        # A partial fetch would move fetched_at on and lose the pages it never read.
        raise SnapshotError(f"{config.id}: the fetch did not finish; keep the last snapshot")


def build(
    result: AdapterResult, config: OperatorConfig, *, partial_ok: bool = False
) -> LiveSnapshot:
    """A whole snapshot from a full fetch of one operator. partial_ok is for the trimmed
    fixtures only, which stop after a few pages on purpose."""
    _check(result, config, partial_ok=partial_ok)
    locations: dict[str, list[LiveEvse]] = {}
    for location in sorted(result.locations, key=lambda loc: loc.id):
        if not in_uk(location):
            continue
        key = location_key(location.id)
        if key in locations:
            raise SnapshotError(f"two locations share the key {key}")
        locations[key] = _evses(location)
    return LiveSnapshot(
        operator=config.id,
        fetched_at=result.fetched_at,
        full_fetch_at=result.fetched_at,
        attribution=" ".join(str(config.attribution).split()),
        licence=config.licence.name,
        licence_url=config.licence.url,
        locations=locations,
    )


def merge(previous: LiveSnapshot, changes: AdapterResult, config: OperatorConfig) -> LiveSnapshot:
    """Lay a fetch of changed locations over the previous snapshot.

    A changed location replaces its earlier entry. One the feed sent but that is no longer
    to be published (publish flag false), could not be read, or is now outside the UK is
    removed, so nothing unpublished is ever served. A full fetch still runs daily and
    replaces the whole snapshot, which also drops locations that left the feed.
    """
    _check(changes, config)
    if previous.operator != config.id:
        raise SnapshotError(f"cannot merge {config.id} into {previous.operator}")
    if changes.fetched_at <= previous.fetched_at:
        raise SnapshotError("the changes are not newer than the snapshot")
    locations = dict(previous.locations)
    for record_id in changes.dropped_location_ids:
        locations.pop(location_key(record_id), None)
    for location in changes.locations:
        key = location_key(location.id)
        if in_uk(location):
            locations[key] = _evses(location)
        else:
            locations.pop(key, None)
    return LiveSnapshot(
        operator=config.id,
        fetched_at=changes.fetched_at,
        full_fetch_at=previous.full_fetch_at,
        attribution=" ".join(str(config.attribution).split()),
        licence=config.licence.name,
        licence_url=config.licence.url,
        locations=locations,
    )


@dataclass(frozen=True)
class OnMap:
    """The locations the published map shows, which are the only ones a status refresh
    gives statuses for: each operator's location ids with their detail file keys."""

    generated_at: datetime
    keys: dict[str, dict[str, str]]


def on_map(build_dir: Path) -> OnMap:
    """Read the published map (build_dir/data/locations.geojson)."""
    path = build_dir / "data" / "locations.geojson"
    try:
        layer = json.loads(path.read_bytes())
        generated_at = datetime.fromisoformat(layer["generated_at"])
        keys: dict[str, dict[str, str]] = {}
        for feature in layer["features"]:
            properties = feature["properties"]
            operator, record_id, key = properties["op"], properties["id"], properties["key"]
            if key != location_key(record_id):
                raise SnapshotError(f"{path}: {record_id!r} does not have the key {key}")
            keys.setdefault(operator, {})[record_id] = key
    except FileNotFoundError:
        raise SnapshotError(f"no published map at {path}") from None
    except (KeyError, TypeError, ValueError) as exc:
        raise SnapshotError(f"{path} is not the published map: {exc}") from None
    return OnMap(generated_at=generated_at, keys=keys)


@dataclass(frozen=True)
class Laid:
    """How a status refresh fitted the published map, for the run's report."""

    locations: int
    evses: int
    # In the feed now, not on the map: new since the daily fetch, outside the UK, hidden
    # by a rule of the daily fetch, or published under another party's codes.
    not_on_map: int
    # On the map, not in the feed now.
    not_in_feed: int
    # One OCPI id that two locations on the map share, so it cannot say which it is for.
    ambiguous: int


def _ocpi_id(record_id: str) -> str:
    """The OCPI id in a location id of the form operator:country:party:id."""
    return record_id.split(":", 3)[-1]


def from_statuses(
    result: StatusResult,
    config: OperatorConfig,
    shown: dict[str, str],
    *,
    partial_ok: bool = False,
) -> tuple[LiveSnapshot, Laid]:
    """A whole snapshot from a status refresh of one operator.

    shown is the operator's locations on the published map, by location id (OnMap.keys).
    Only those get a status, so a refresh can never show a location the daily fetch did
    not publish: one whose publish flag is false or missing, one outside the UK, or one
    the owner left off. A location on the map that the feed no longer lists is left out.
    A refresh that did not finish never becomes a snapshot; partial_ok is for the trimmed
    fixtures only, which stop after a few pages on purpose.
    """
    if result.operator_id != config.id:
        raise SnapshotError(f"{result.operator_id}: not the operator {config.id}")
    if not config.enabled or config.licence is None:
        raise SnapshotError(f"{config.id} is not switched on in the registry")
    if config.sent_copy is not None:
        raise SnapshotError(f"{config.id}: a copy the operator sent has no statuses to refresh")
    if not result.complete and not partial_ok:
        raise SnapshotError(f"{config.id}: the refresh did not finish; keep the last snapshot")
    if result.ocpi_ids:
        # Statuses that name a location by its OCPI id alone: match it to the one
        # location on the map with that id, and to none when two share it.
        by_ocpi_id: dict[str, list[str]] = {}
        for record_id in shown:
            by_ocpi_id.setdefault(_ocpi_id(record_id), []).append(record_id)
        matches = {sent: by_ocpi_id.get(sent, []) for sent in result.statuses}
    else:
        matches = {sent: [sent] if sent in shown else [] for sent in result.statuses}
    dropped = set(result.dropped_location_ids)
    locations: dict[str, list[LiveEvse]] = {}
    not_on_map = ambiguous = 0
    for sent, record_ids in sorted(matches.items()):
        if len(record_ids) > 1:
            ambiguous += 1
        elif not record_ids:
            not_on_map += 1
        elif record_ids[0] not in dropped:
            locations[shown[record_ids[0]]] = list(result.statuses[sent])
    snapshot = LiveSnapshot(
        operator=config.id,
        fetched_at=result.fetched_at,
        full_fetch_at=result.fetched_at,
        attribution=" ".join(str(config.attribution).split()),
        licence=config.licence.name,
        licence_url=config.licence.url,
        locations=locations,
    )
    laid = Laid(
        locations=len(locations),
        evses=sum(len(evses) for evses in locations.values()),
        not_on_map=not_on_map,
        not_in_feed=len(shown) - len(locations),
        ambiguous=ambiguous,
    )
    return snapshot, laid


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

    operators = load_registry()
    for result in run_fixtures(operators):
        try:
            snapshot = build(result, operators[result.operator_id], partial_ok=True)
            path = write(snapshot, args.out)
        except SnapshotError as error:
            print(f"{result.operator_id}: {error}", file=sys.stderr)
            return 1
        print(f"{result.operator_id}: {path} ({path.stat().st_size:,} bytes)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
