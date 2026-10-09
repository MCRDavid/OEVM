"""Merge operator results and publish the files the map loads (blueprint task 7).

    uv run python -m pipeline.run --fixtures --publish build

writes, under build/data/:

- locations.geojson: one slim point per location, for the map and its filters. It holds
  no live status, because a daily snapshot would look current when it is not.
- loc/<shard>/<key>.json: everything about one location, its tariffs and the price of
  each connector as worded by pipeline/pricing.py. EVSE statuses carry their dates.
- manifest.json: when each operator was fetched, attribution, counts and file sizes.

Rules:
- Only operators switched on in the registry are published (their terms have been read).
- Locations whose coordinates fall outside the UK are left off the map and counted, never
  moved: operator data is not corrected.
- Every file is validated against schema/published.py before it is written.
- The committed site/ folder is never written to; the deploy step copies site/ and adds
  this output.
"""

import gzip
import hashlib
import json
import shutil
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from adapters.ocpi_221 import AdapterResult
from pipeline.health import in_uk
from pipeline.pricing import location_summary
from pipeline.registry import ROOT
from pipeline.tariffs import ConnectorPrice, TariffOption, price_locations, site_tariffs
from schema.models import Connector, Location
from schema.operator import OperatorConfig
from schema.published import (
    ConnectorPriceOut,
    ConnectorSummary,
    FileEntry,
    LocationDetail,
    Manifest,
    MapFeature,
    MapLayer,
    MapProperties,
    OperatorEntry,
    PointGeometry,
    TariffOptionOut,
)

LICENCE_NOTE = (
    "Charge point data belongs to each operator and is used in line with the Open "
    "Government Licence v3.0, with the attribution statements listed here. This project's "
    "Apache-2.0 licence covers its code only. Check prices and availability at the charger."
)


class PublishError(Exception):
    """The results cannot be published as they are."""


@dataclass
class Published:
    manifest: Manifest
    report: list[str]


def location_key(location_id: str) -> str:
    """A short, file-safe name for a location's detail file. Ids may contain spaces."""
    return hashlib.sha256(location_id.encode("utf-8")).hexdigest()[:16]


def _pence(amount: Decimal) -> float:
    return float((amount * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


MAP_PRICE = {"free_confirmed": "free", "priced": "priced", "unknown": "unknown"}


def _sortable(value: float | None) -> float:
    """None sorts before every real value and never equals one."""
    return -1.0 if value is None else value


def _connector_summary(connector: Connector, price: ConnectorPrice) -> ConnectorSummary:
    with_vat = price.state == "priced" and price.includes_vat and price.energy_high is not None
    return ConnectorSummary(
        std=connector.standard,
        kw=connector.max_kw,
        price=MAP_PRICE[price.state],
        ppk=_pence(price.energy_high) if with_vat else None,
    )


def map_properties(location: Location, prices: list[ConnectorPrice], key: str) -> MapProperties:
    """The slim properties of one location. prices holds one entry per connector, in the
    order price_locations gives them."""
    connectors = [c for evse in location.evses for c in evse.connectors]
    if len(prices) != len(connectors):
        raise PublishError(f"{location.id}: expected a price for each connector")
    powers = [c.max_kw for c in connectors if c.max_kw is not None]
    states = {p.state for p in prices}
    summaries = {
        (s.std, _sortable(s.kw), s.price, _sortable(s.ppk)): s
        for s in (_connector_summary(c, p) for c, p in zip(connectors, prices, strict=True))
    }
    return MapProperties(
        id=location.id,
        key=key,
        op=location.provenance.source_id,
        name=location.name,
        kw=max(powers) if powers else None,
        plugs=sorted({c.standard for c in connectors}),
        evses=len(location.evses),
        price=(
            "free"
            if states == {"free_confirmed"}
            else ("priced" if "priced" in states else "unknown")
        ),
        pt=location_summary(prices),
        cons=[summaries[k] for k in sorted(summaries)],
    )


def _price_out(price: ConnectorPrice) -> ConnectorPriceOut:
    return ConnectorPriceOut(
        evse_uid=price.evse_uid,
        connector_id=price.connector_id,
        state=price.state,
        text=price.text,
        reason=price.reason,
        indicative=price.indicative,
        tariff_ids=price.tariff_ids,
        unresolved_ids=price.unresolved_ids,
    )


def _option_out(option: TariffOption) -> TariffOptionOut:
    low, high = option.energy_low, option.energy_high
    return TariffOptionOut(
        tariff_id=option.tariff_id,
        name=option.name,
        kind=option.kind,
        state=option.state,
        text=option.text,
        reason=option.reason,
        varies=option.varies,
        connectors=option.connectors,
        ppk_low=None if low is None else _pence(low),
        ppk_high=None if high is None else _pence(high),
        includes_vat=option.includes_vat if low is not None else None,
    )


def _dump(model, *, indent: int | None = None) -> bytes:
    data = model.model_dump(mode="json")
    separators = None if indent else (",", ":")
    text = json.dumps(data, ensure_ascii=False, indent=indent, separators=separators)
    return (text + "\n").encode("utf-8")


def _validated(model: type, blob: bytes) -> bytes:
    """blob, after checking that the exact bytes to be written read back as a valid model."""
    model.model_validate_json(blob)
    return blob


def _size(path: str, blobs: list[bytes]) -> FileEntry:
    return FileEntry(
        path=path,
        files=len(blobs),
        bytes=sum(len(b) for b in blobs),
        gzip_bytes=sum(len(gzip.compress(b, mtime=0)) for b in blobs),
    )


def publish(
    results: list[AdapterResult],
    operators: dict[str, OperatorConfig],
    out_dir: Path,
    *,
    mode: str,
    generated_at: datetime,
) -> Published:
    """Merge the results, validate every file and write them under out_dir/data."""
    if out_dir.resolve() == (ROOT / "site").resolve():
        raise PublishError("publish to a build folder, not the committed site/ folder")
    features: list[MapFeature] = []
    details: dict[str, bytes] = {}
    entries: dict[str, OperatorEntry] = {}
    attribution: list[str] = []
    for result in sorted(results, key=lambda r: r.operator_id):
        config = operators.get(result.operator_id)
        if config is None or not config.enabled or config.licence is None:
            raise PublishError(f"{result.operator_id} is not switched on in the registry")
        attribution.append(" ".join(str(config.attribution).split()))
        by_location: dict[str, list[ConnectorPrice]] = defaultdict(list)
        for price in price_locations(result.locations, result.tariffs):
            by_location[price.location_id].append(price)
        tariffs = {t.id: t for t in result.tariffs}
        mapped, not_mapped = 0, []
        for location in sorted(result.locations, key=lambda loc: loc.id):
            if not in_uk(location):
                not_mapped.append(location.id)
                continue
            key = location_key(location.id)
            if key in details:
                raise PublishError(f"two locations share the detail file name {key}")
            prices = by_location[location.id]
            site = site_tariffs(location, tariffs)
            listed = sorted(o.tariff_id for o in site.options if o.tariff_id in tariffs)
            detail = LocationDetail(
                location=location,
                tariffs=[tariffs[i] for i in listed],
                prices=[_price_out(p) for p in prices],
                tariff_options=[_option_out(o) for o in site.options],
                tariff_comparison=site.comparison,
                attribution=attribution[-1],
                licence=config.licence.name,
                licence_url=config.licence.url,
                fetched_at=result.fetched_at,
            )
            details[key] = _validated(LocationDetail, _dump(detail))
            coordinates = (
                round(location.coordinates.longitude, 6),
                round(location.coordinates.latitude, 6),
            )
            features.append(
                MapFeature(
                    geometry=PointGeometry(coordinates=coordinates),
                    properties=map_properties(location, prices, key),
                )
            )
            mapped += 1
        entries[result.operator_id] = OperatorEntry(
            name=config.display_name,
            fetched_at=result.fetched_at,
            mode=mode,
            complete=result.complete,
            mapped=mapped,
            not_mapped=len(not_mapped),
            not_mapped_ids=not_mapped,
            tariffs=len(result.tariffs),
            attribution=attribution[-1],
            licence=config.licence.name,
            licence_url=config.licence.url,
        )

    layer = MapLayer(
        generated_at=generated_at,
        attribution=attribution,
        licence_note=LICENCE_NOTE,
        features=features,
    )
    layer_bytes = _validated(MapLayer, _dump(layer))
    files = [_size("data/locations.geojson", [layer_bytes])]
    if details:
        files.append(_size("data/loc/", list(details.values())))
    manifest = Manifest(generated_at=generated_at, operators=entries, files=files)

    data = out_dir / "data"
    shutil.rmtree(data / "loc", ignore_errors=True)  # no detail file outlives its location
    data.mkdir(parents=True, exist_ok=True)
    (data / "locations.geojson").write_bytes(layer_bytes)
    for key, blob in details.items():
        path = data / "loc" / key[:2] / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    (data / "manifest.json").write_bytes(_validated(Manifest, _dump(manifest, indent=2)))

    report = [f"published to {data}:"]
    for entry in files:
        report.append(
            f"  {entry.path}: {entry.files} file(s), {entry.bytes:,} bytes "
            f"({entry.gzip_bytes:,} gzipped)"
        )
    for operator_id, entry in entries.items():
        left_off = f", {entry.not_mapped} left off (outside the UK)" if entry.not_mapped else ""
        report.append(f"  {operator_id}: {entry.mapped} locations mapped{left_off}")
    return Published(manifest=manifest, report=report)
