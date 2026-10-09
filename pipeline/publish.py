"""Merge operator results and publish the files the map loads (blueprint task 7).

    uv run python -m pipeline.run --fixtures --publish build

writes, under build/data/:

- locations.geojson: one slim point per location, for the map and its filters. It holds
  no live status, because a daily snapshot would look current when it is not. Each kind
  of connector only says whether it was reported out of service in this fetch, so the
  map can offer to hide those; the map says the report is from the last daily fetch.
- loc/<shard>/<key>.json: everything about one location, its tariffs and the price of
  each connector as worded by pipeline/pricing.py. EVSE statuses carry their dates.
- manifest.json: when each operator was fetched, attribution, counts and file sizes.

Rules:
- Only operators switched on in the registry are published (their terms have been read).
- Locations whose coordinates are not in the UK (pipeline/geography.py, ADR 0017) are
  left off the map and counted.
  Operator data is not corrected, with one exception the owner decides per operator
  (swapped_coordinates in the operator file, ADR 0013): a point whose latitude and
  longitude are obviously the wrong way round is swapped back, and a longitude obviously
  missing its minus sign gets it back. The published point is kept in the detail file,
  and the map says so.
- When an operator's fetch fails, the map keeps showing its last good copy from the
  previous published files (`previous`), if that copy is at most MAX_KEPT_DAYS old and
  still valid. Its manifest entry says so and keeps the original fetch time; each
  location's detail file keeps its own fetched_at, so nothing looks newer than it is
  (ADR 0018).
- Every file is validated against schema/published.py before it is written.
- The committed site/ folder is never written to; the deploy step copies site/ and adds
  this output.
"""

import gzip
import hashlib
import json
import re
import shutil
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path

from adapters.ocpi_221 import AdapterResult
from pipeline.geography import place_in_uk
from pipeline.health import in_uk
from pipeline.plans import load_providers
from pipeline.pricing import location_summary, plan_fee_text, plan_price_text
from pipeline.registry import ROOT
from pipeline.tariffs import ConnectorPrice, TariffOption, price_locations, site_tariffs
from schema.models import Connector, Coordinates, Location
from schema.operator import OperatorConfig
from schema.published import (
    ConnectorPriceOut,
    ConnectorSummary,
    CoordinatesCorrection,
    FileEntry,
    LocationDetail,
    Manifest,
    MapFeature,
    MapLayer,
    MapProperties,
    OperatorEntry,
    PlanOut,
    PlansFile,
    PointGeometry,
    TariffOptionOut,
)

# A UK postcode, with or without its space (the BFPO and overseas territory forms are not
# needed here). Used only to decide whether swapped coordinates are obviously a UK place.
UK_POSTCODE = re.compile(r"^[A-Z]{1,2}[0-9][A-Z0-9]? ?[0-9][A-Z]{2}$", re.IGNORECASE)

SWAP_NOTE = (
    "The operator published this location's latitude and longitude the wrong way round, "
    "which put it outside the UK. This map shows it with the two swapped back; the "
    "operator's own figures are latitude {lat} and longitude {lon}."
)

SIGN_NOTE = (
    "The operator published this location's longitude without its minus sign, which put it "
    "outside the UK. This map shows it with the minus sign added; the operator's own "
    "figures are latitude {lat} and longitude {lon}."
)

LICENCE_NOTE = (
    "Charge point data belongs to each operator and is used in line with the Open "
    "Government Licence v3.0, with the attribution statements listed here. This project's "
    "Apache-2.0 licence covers its code only. Check prices and availability at the charger."
)


# The oldest last good copy shown for an operator whose fetch failed (ADR 0018).
MAX_KEPT_DAYS = 7


class PublishError(Exception):
    """The results cannot be published as they are."""


@dataclass
class Published:
    manifest: Manifest
    report: list[str]
    # Operators whose fetch failed and whose last good copy is shown, with its fetch time.
    kept: dict[str, datetime] = field(default_factory=dict)


@dataclass
class KeptCopy:
    """An operator's last good copy from the previous published files."""

    operator_id: str
    entry: OperatorEntry
    features: list[MapFeature]
    details: dict[str, bytes]


def last_good_copy(
    previous: Path, operator_id: str, config: OperatorConfig, now: datetime
) -> tuple[KeptCopy | None, str]:
    """The operator's copy in the previous published files under previous/data, and why
    not when there is none to keep. The copy is checked against today's models."""
    data = previous / "data"
    try:
        manifest = Manifest.model_validate_json((data / "manifest.json").read_bytes())
        entry = manifest.operators.get(operator_id)
        if entry is None:
            return None, "the previous files have no copy"
        if entry.mode != "live":
            return None, "the previous copy is not from a live fetch"
        if now - entry.fetched_at > timedelta(days=MAX_KEPT_DAYS):
            return None, f"the previous copy is more than {MAX_KEPT_DAYS} days old"
        layer = MapLayer.model_validate_json((data / "locations.geojson").read_bytes())
        features = [f for f in layer.features if f.properties.op == operator_id]
        details = {}
        for feature in features:
            key = feature.properties.key
            blob = (data / "loc" / key[:2] / f"{key}.json").read_bytes()
            detail = LocationDetail.model_validate_json(blob)
            if detail.location.provenance.source_id != operator_id:
                return None, f"the previous detail file {key} is not this operator's"
            details[key] = blob
    except FileNotFoundError as exc:
        return None, f"the previous files are missing {Path(exc.filename).name}"
    except ValueError as exc:  # pydantic's ValidationError is a ValueError
        return None, f"the previous files are not valid today: {str(exc).splitlines()[0]}"
    if len(features) != entry.mapped:
        return None, "the previous files do not match their manifest"
    attribution = " ".join(str(config.attribution).split())
    entry = entry.model_copy(update={"kept_from_previous": True, "attribution": attribution})
    return KeptCopy(operator_id, entry, features, details), ""


def location_key(location_id: str) -> str:
    """A short, file-safe name for a location's detail file. Ids may contain spaces."""
    return hashlib.sha256(location_id.encode("utf-8")).hexdigest()[:16]


def _pence(amount: Decimal) -> float:
    return float((amount * 100).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP))


MAP_PRICE = {"free_confirmed": "free", "priced": "priced", "unknown": "unknown"}


def _sortable(value: float | None) -> float:
    """None sorts before every real value and never equals one."""
    return -1.0 if value is None else value


# OCPI 2.2.1 EVSE statuses under which a charge point cannot be used. "blocked" (a parked
# car, for example) and "unknown" are not counted.
OUT_OF_SERVICE = frozenset({"out_of_order", "inoperative", "planned", "removed"})


def _connector_summary(
    connector: Connector, price: ConnectorPrice, status: str
) -> ConnectorSummary:
    with_vat = price.state == "priced" and price.includes_vat and price.energy_high is not None
    return ConnectorSummary(
        std=connector.standard,
        kw=connector.max_kw,
        price=MAP_PRICE[price.state],
        ppk=_pence(price.energy_high) if with_vat else None,
        out=status in OUT_OF_SERVICE,
    )


def map_properties(location: Location, prices: list[ConnectorPrice], key: str) -> MapProperties:
    """The slim properties of one location. prices holds one entry per connector, in the
    order price_locations gives them."""
    connectors = [c for evse in location.evses for c in evse.connectors]
    statuses = [evse.status for evse in location.evses for _ in evse.connectors]
    if len(prices) != len(connectors):
        raise PublishError(f"{location.id}: expected a price for each connector")
    powers = [c.max_kw for c in connectors if c.max_kw is not None]
    states = {p.state for p in prices}
    summaries = {
        (s.std, _sortable(s.kw), s.price, _sortable(s.ppk), s.out): s
        for s in (
            _connector_summary(c, p, st)
            for c, p, st in zip(connectors, prices, statuses, strict=True)
        )
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
        original_name=option.original_name,
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


PLANS_NOTE = (
    "Copied by hand from each provider's own published pages, on the date shown with each "
    "plan, and only where the provider's terms allow reuse. Plans and prices change often: "
    "check with the provider before signing up."
)


def plans_file(operators: dict[str, OperatorConfig], generated_at: datetime) -> PlansFile:
    """Every listed plan, for the map's plan list, details and calculator."""
    plans = []
    for provider in load_providers(operator_ids=set(operators)).values():
        attribution = provider.terms.attribution if provider.terms.reuse == "attribution" else None
        for plan in provider.plans:
            fixed = plan.price_per_kwh is not None and plan.includes_vat
            plans.append(
                PlanOut(
                    id=f"{provider.id}.{plan.id}",
                    provider=provider.name,
                    provider_kind=provider.kind,
                    name=plan.name,
                    pay_by=plan.pay_by,
                    fee_text=plan_fee_text(plan.monthly_fee),
                    price_text=plan_price_text(
                        plan.price_per_kwh,
                        plan.discount_percent,
                        plan.discount_of,
                        plan.includes_vat,
                    ),
                    monthly_fee=None if plan.monthly_fee is None else float(plan.monthly_fee),
                    ppk=_pence(plan.price_per_kwh) if fixed else None,
                    discount_percent=(
                        None if plan.discount_percent is None else float(plan.discount_percent)
                    ),
                    networks=plan.networks,
                    operator_ids=plan.operator_ids,
                    conditions=plan.conditions,
                    needs_testing=plan.needs_testing,
                    fee_note=plan.fee_note,
                    attribution=attribution,
                    source_url=plan.source.url,
                    checked=plan.source.checked,
                )
            )
    return PlansFile(generated_at=generated_at, note=PLANS_NOTE, plans=plans)


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


def swapped_back(location: Location, config: OperatorConfig) -> Location | None:
    """The location with latitude and longitude swapped, if the owner allows it for this
    operator and the swap is obvious: the published point is outside the UK, the swapped
    point is inside it, the country is GBR and the postcode is a UK postcode."""
    if config.swapped_coordinates is None or in_uk(location):
        return None
    postcode = (location.address.postal_code or "").strip()
    if location.address.country != "GBR" or not UK_POSTCODE.match(postcode):
        return None
    published = location.coordinates
    try:
        swapped = Coordinates(latitude=published.longitude, longitude=published.latitude)
    except ValueError:
        return None
    moved = location.model_copy(update={"coordinates": swapped})
    return moved if in_uk(moved) else None


def sign_restored(location: Location, config: OperatorConfig) -> Location | None:
    """The location with a minus sign added to its longitude, if the owner allows it for
    this operator and the missing sign is obvious: the published longitude is positive and
    the point is outside the UK, the same point west of the Greenwich meridian is on the
    UK's land or within 2 km of its coast (the wider reach for small islands is not used
    here), the country is GBR, and the postcode is a UK postcode or none is given (such
    as "N/A"). A location with a postcode from another country is never moved."""
    if config.swapped_coordinates is None or in_uk(location):
        return None
    postcode = (location.address.postal_code or "").strip()
    has_postcode = any(c.isdigit() for c in postcode)
    if location.address.country != "GBR" or (has_postcode and not UK_POSTCODE.match(postcode)):
        return None
    published = location.coordinates
    if published.longitude <= 0:
        return None
    if not place_in_uk(published.latitude, -published.longitude):
        return None
    flipped = Coordinates(latitude=published.latitude, longitude=-published.longitude)
    return location.model_copy(update={"coordinates": flipped})


def corrected_coordinates(
    location: Location, config: OperatorConfig
) -> tuple[Location, CoordinatesCorrection] | None:
    """The location moved back into the UK and a note saying how, or None if neither an
    obvious swap nor an obviously missing minus sign explains why it is outside."""
    published = location.coordinates
    figures = {"lat": published.latitude, "lon": published.longitude}
    for correct, note in ((swapped_back, SWAP_NOTE), (sign_restored, SIGN_NOTE)):
        moved = correct(location, config)
        if moved is not None:
            return moved, CoordinatesCorrection(published=published, note=note.format(**figures))
    return None


def publish(
    results: list[AdapterResult],
    operators: dict[str, OperatorConfig],
    out_dir: Path,
    *,
    mode: str,
    generated_at: datetime,
    kept: list[KeptCopy] = (),
) -> Published:
    """Merge the results, and any last good copies kept for operators whose fetch failed,
    validate every file and write them under out_dir/data."""
    if out_dir.resolve() == (ROOT / "site").resolve():
        raise PublishError("publish to a build folder, not the committed site/ folder")
    features: list[MapFeature] = []
    details: dict[str, bytes] = {}
    entries: dict[str, OperatorEntry] = {}
    attribution: list[str] = []
    fresh = {r.operator_id for r in results}
    for copy in sorted(kept, key=lambda c: c.operator_id):
        config = operators.get(copy.operator_id)
        if config is None or not config.enabled or config.licence is None:
            raise PublishError(f"{copy.operator_id} is not switched on in the registry")
        if copy.operator_id in fresh:
            raise PublishError(f"{copy.operator_id} has both a fresh fetch and a kept copy")
        for key, blob in copy.details.items():
            if key in details:
                raise PublishError(f"two locations share the detail file name {key}")
            details[key] = blob
        features.extend(copy.features)
        entries[copy.operator_id] = copy.entry
    for result in sorted(results, key=lambda r: r.operator_id):
        config = operators.get(result.operator_id)
        if config is None or not config.enabled or config.licence is None:
            raise PublishError(f"{result.operator_id} is not switched on in the registry")
        attribution.append(" ".join(str(config.attribution).split()))
        by_location: dict[str, list[ConnectorPrice]] = defaultdict(list)
        for price in price_locations(result.locations, result.tariffs):
            by_location[price.location_id].append(price)
        tariffs = {t.id: t for t in result.tariffs}
        mapped, not_mapped, corrected = 0, [], []
        for location in sorted(result.locations, key=lambda loc: loc.id):
            correction = None
            if not in_uk(location):
                fixed = corrected_coordinates(location, config)
                if fixed is None:
                    not_mapped.append(location.id)
                    continue
                location, correction = fixed
                corrected.append(location.id)
            key = location_key(location.id)
            if key in details:
                raise PublishError(f"two locations share the detail file name {key}")
            prices = by_location[location.id]
            site = site_tariffs(location, tariffs)
            listed = sorted(o.tariff_id for o in site.options if o.tariff_id in tariffs)
            detail = LocationDetail(
                location=location,
                coordinates_corrected=correction,
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
            corrected=len(corrected),
            corrected_ids=corrected,
            tariffs=len(result.tariffs),
            attribution=attribution[-1],
            licence=config.licence.name,
            licence_url=config.licence.url,
        )

    features.sort(key=lambda f: (f.properties.op, f.properties.id))
    layer = MapLayer(
        generated_at=generated_at,
        attribution=[entries[i].attribution for i in sorted(entries)],
        licence_note=LICENCE_NOTE,
        features=features,
    )
    layer_bytes = _validated(MapLayer, _dump(layer))
    files = [_size("data/locations.geojson", [layer_bytes])]
    if details:
        files.append(_size("data/loc/", list(details.values())))
    plans_bytes = _validated(PlansFile, _dump(plans_file(operators, generated_at)))
    files.append(_size("data/plans.json", [plans_bytes]))
    entries = dict(sorted(entries.items()))
    manifest = Manifest(generated_at=generated_at, operators=entries, files=files)

    data = out_dir / "data"
    shutil.rmtree(data / "loc", ignore_errors=True)  # no detail file outlives its location
    data.mkdir(parents=True, exist_ok=True)
    (data / "locations.geojson").write_bytes(layer_bytes)
    for key, blob in details.items():
        path = data / "loc" / key[:2] / f"{key}.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(blob)
    (data / "plans.json").write_bytes(plans_bytes)
    (data / "manifest.json").write_bytes(_validated(Manifest, _dump(manifest, indent=2)))

    report = [f"published to {data}:"]
    for entry in files:
        report.append(
            f"  {entry.path}: {entry.files} file(s), {entry.bytes:,} bytes "
            f"({entry.gzip_bytes:,} gzipped)"
        )
    for operator_id, entry in entries.items():
        left_off = f", {entry.not_mapped} left off (outside the UK)" if entry.not_mapped else ""
        swapped = f", {entry.corrected} with coordinates corrected" if entry.corrected else ""
        last_good = (
            f", from its last good copy fetched {entry.fetched_at:%Y-%m-%d %H:%M} UTC"
            if entry.kept_from_previous
            else ""
        )
        report.append(
            f"  {operator_id}: {entry.mapped} locations mapped{left_off}{swapped}{last_good}"
        )
    kept_at = {c.operator_id: c.entry.fetched_at for c in kept}
    return Published(manifest=manifest, report=report, kept=kept_at)
