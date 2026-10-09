"""Models for the files the pipeline publishes for the map (blueprint task 7).

- data/locations.geojson: one slim point per location, for the map and its filters.
- data/loc/<shard>/<key>.json: everything about one location, loaded on click.
- data/manifest.json: when each operator was fetched, attribution, counts and file sizes.
- data/status.json: feed health for each operator, with a 30-day history.

Every file is validated against these models before it is written, and their JSON Schema
is exported to schema/json/ so the front end and CI can check the files too.
"""

import datetime as dt
from typing import Annotated, Literal

from pydantic import AwareDatetime, Field

from schema.models import Coordinates, Location, PriceState, RecordId, SourceId, Tariff, _Model
from schema.runlog import RunLog

Key = Annotated[str, Field(pattern=r"^[0-9a-f]{16}$")]
SCHEMA_VERSION = 1


class PointGeometry(_Model):
    type: Literal["Point"] = "Point"
    coordinates: tuple[float, float] = Field(description="[longitude, latitude], WGS 84.")


MapPrice = Literal["free", "priced", "unknown"]


class ConnectorSummary(_Model):
    """One kind of connector at a location, so filters can ask for one connector that meets
    every condition at once. Connectors that would give the same entry appear once."""

    std: str = Field(description="Connector standard (OCPI 2.2.1 name).")
    kw: float | None = Field(default=None, ge=0, description="Maximum power, kW.")
    price: MapPrice = Field(description="'free' only when its price state is free_confirmed.")
    ppk: float | None = Field(
        default=None,
        ge=0,
        description="Pence per kWh including VAT: the highest energy price that can apply. "
        "Null when the tariff states no VAT or gives no energy price.",
    )
    out: bool = Field(
        description="True when the operator reported this connector's charge point as out of "
        "service (out_of_order, inoperative, planned or removed) in the fetch the file was "
        "built from. False for any other status, including unknown."
    )


class MapProperties(_Model):
    id: RecordId
    key: Key = Field(description="Detail file: data/loc/<first two characters>/<key>.json.")
    op: SourceId = Field(description="Operator registry id.")
    name: str | None = None
    kw: float | None = Field(default=None, ge=0, description="Highest connector power, kW.")
    plugs: list[str] = Field(description="Connector standards (OCPI 2.2.1 names), sorted.")
    evses: int = Field(ge=0)
    price: MapPrice = Field(
        description="'free' only when every connector's price state is free_confirmed; "
        "'priced' when any connector is priced; otherwise 'unknown'."
    )
    pt: str = Field(description="Price summary worded by pipeline/pricing.py.")
    cons: list[ConnectorSummary] = Field(description="Each kind of connector, sorted.")


class MapFeature(_Model):
    type: Literal["Feature"] = "Feature"
    geometry: PointGeometry
    properties: MapProperties


class MapLayer(_Model):
    type: Literal["FeatureCollection"] = "FeatureCollection"
    generated_at: AwareDatetime
    attribution: list[str] = Field(description="One attribution statement per operator.")
    licence_note: str
    features: list[MapFeature]


class ConnectorPriceOut(_Model):
    evse_uid: str
    connector_id: str
    state: PriceState
    text: str = Field(description="Worded by pipeline/pricing.py.")
    reason: str | None = None
    indicative: str | None = Field(default=None, description="For example '49.2p/kWh'.")
    tariff_ids: list[RecordId]
    unresolved_ids: list[RecordId]


class TariffOptionOut(_Model):
    """One tariff listed at a location, so people can compare them."""

    tariff_id: RecordId
    name: str | None = Field(default=None, description="The operator's own description.")
    kind: str = Field(description="How it is paid for, from its OCPI type, in plain words.")
    state: MapPrice = Field(description="'free' only when its price state is free_confirmed.")
    text: str = Field(description="Worded by pipeline/pricing.py.")
    reason: str | None = None
    varies: str | None = Field(
        default=None, description="What the price depends on, such as the time of day."
    )
    connectors: int = Field(ge=0, description="How many of the location's connectors list it.")
    ppk_low: float | None = Field(
        default=None, ge=0, description="Lowest energy price that can apply, pence per kWh."
    )
    ppk_high: float | None = Field(
        default=None, ge=0, description="Highest energy price that can apply, pence per kWh."
    )
    includes_vat: bool | None = Field(
        default=None, description="Whether ppk_low and ppk_high include VAT."
    )


class CoordinatesCorrection(_Model):
    published: Coordinates = Field(description="The coordinates exactly as the operator sent them.")
    note: str = Field(description="What was corrected and why, shown with the location.")


class LocationDetail(_Model):
    location: Location
    coordinates_corrected: CoordinatesCorrection | None = Field(
        default=None,
        description="Set when this project swapped the operator's latitude and longitude, "
        "by the owner's decision recorded in the operator file. Null otherwise.",
    )
    tariffs: list[Tariff] = Field(
        description="Every tariff this location's connectors list that was found."
    )
    prices: list[ConnectorPriceOut]
    tariff_options: list[TariffOptionOut] = Field(
        default_factory=list,
        description="Every tariff the connectors list, in the order first listed, "
        "including ones that could not be found.",
    )
    tariff_comparison: str | None = Field(
        default=None,
        description="Which listed tariff has the lowest energy price, worded by "
        "pipeline/pricing.py; null when they cannot be compared fairly.",
    )
    attribution: str
    licence: str
    licence_url: str | None = None
    fetched_at: AwareDatetime


class OperatorEntry(_Model):
    name: str
    fetched_at: AwareDatetime
    mode: Literal["fixtures", "live"]
    complete: bool
    mapped: int = Field(ge=0, description="Locations on the map.")
    not_mapped: int = Field(ge=0, description="Locations left off: coordinates outside the UK.")
    not_mapped_ids: list[RecordId] = Field(description="Ids of the locations left off.")
    corrected: int = Field(
        default=0,
        ge=0,
        description="Locations shown after swapping latitude and longitude the operator sent "
        "the wrong way round.",
    )
    corrected_ids: list[RecordId] = Field(
        default_factory=list, description="Ids of the corrected locations."
    )
    tariffs: int = Field(ge=0)
    attribution: str
    licence: str
    licence_url: str | None = None


class FileEntry(_Model):
    path: str
    files: int = Field(ge=1)
    bytes: int = Field(ge=0)
    gzip_bytes: int = Field(ge=0, description="Size after gzip, as most browsers receive it.")


class Manifest(_Model):
    schema_version: Literal[1] = SCHEMA_VERSION
    generated_at: AwareDatetime
    operators: dict[SourceId, OperatorEntry]
    files: list[FileEntry]


class HistoryPoint(_Model):
    """One day's latest run for one operator."""

    date: dt.date
    fetched_at: AwareDatetime
    failed: bool
    complete: bool
    locations: int = Field(ge=0)
    connectors_with_tariff_pct: float | None = Field(default=None, ge=0, le=100)
    evses_with_status_pct: float | None = Field(default=None, ge=0, le=100)


class OperatorStatus(_Model):
    name: str
    last_attempt: AwareDatetime | None = None
    last_success: AwareDatetime | None = None
    latest: RunLog | None = Field(default=None, description="The most recent run log.")
    history: list[HistoryPoint] = Field(description="Up to 30 days, oldest first.")


class StatusFile(_Model):
    schema_version: Literal[1] = SCHEMA_VERSION
    generated_at: AwareDatetime
    operators: dict[SourceId, OperatorStatus]
