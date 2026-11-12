"""Statuses read between the daily fetches (Phase 3, docs/PHASE3_PLAN.md, ADR 0032).

LiveSnapshot is one file per operator: the status of every EVSE at every location the map
shows, keyed by the same location key as the map's detail files
(pipeline.publish.location_key). The pipeline builds it from operator feeds with the same
polite client and normalisers as the daily run (pipeline.refresh), and RefreshLog records
each run.

LiveShard and LiveIndex are what the site serves (pipeline.live_site): the snapshots that
are newer than the map files, split into small files by the first two characters of the
location key, like the detail files, so the details screen reads one small file.
"""

from typing import Literal

from pydantic import AwareDatetime, Field, model_validator

from schema.models import EvseStatus, _Model
from schema.published import Key

LIVE_SCHEMA_VERSION = 1


class LiveEvse(_Model):
    uid: str = Field(min_length=1, description="OCPI EVSE uid, unique within its location.")
    status: EvseStatus
    status_at: AwareDatetime | None = Field(
        description="When the operator last reported the status. Null only when unknown."
    )

    @model_validator(mode="after")
    def _check(self) -> "LiveEvse":
        if self.status != "unknown" and self.status_at is None:
            raise ValueError("status_at is required when status is not 'unknown'")
        return self


class LiveSnapshot(_Model):
    schema_version: Literal[1] = LIVE_SCHEMA_VERSION
    operator: str = Field(pattern=r"^[a-z0-9_]+$", description="Operator id in the registry.")
    fetched_at: AwareDatetime = Field(
        description="When the newest data in this snapshot was fetched from the operator."
    )
    full_fetch_at: AwareDatetime = Field(
        description="When every location was last fetched, rather than only changes."
    )
    attribution: str = Field(min_length=1, description="The operator's attribution statement.")
    licence: str = Field(min_length=1, description="The licence the operator's data is used under.")
    licence_url: str | None = None
    locations: dict[Key, list[LiveEvse]] = Field(
        description="EVSE statuses by location key, as in data/loc/<shard>/<key>.json."
    )


class LiveLocation(_Model):
    """One location's statuses in a status file the site serves."""

    operator: str = Field(pattern=r"^[a-z0-9_]+$", description="Operator id in the registry.")
    fetched_at: AwareDatetime = Field(
        description="When these statuses were read from the operator's feed."
    )
    evses: list[LiveEvse]


class LiveShard(_Model):
    """data/live/<shard>.json: statuses read since the daily fetch, for the locations whose
    key starts with <shard>. A location with nothing newer than its detail file is absent."""

    schema_version: Literal[1] = LIVE_SCHEMA_VERSION
    generated_at: AwareDatetime = Field(description="When the status files were written.")
    locations: dict[Key, LiveLocation]


class LiveIndexEntry(_Model):
    """One operator's statuses in the status files, with their source and licence."""

    fetched_at: AwareDatetime = Field(
        description="When the statuses were read from the operator's feed."
    )
    locations: int = Field(ge=0)
    evses: int = Field(ge=0)
    attribution: str = Field(min_length=1, description="The operator's attribution statement.")
    licence: str = Field(min_length=1, description="The licence the operator's data is used under.")
    licence_url: str | None = None


class LiveIndex(_Model):
    """data/live/index.json: which operators' statuses the status files hold."""

    schema_version: Literal[1] = LIVE_SCHEMA_VERSION
    generated_at: AwareDatetime = Field(description="When the status files were written.")
    map_generated_at: AwareDatetime = Field(
        description="generated_at of the map files the statuses belong to."
    )
    operators: dict[str, LiveIndexEntry] = Field(
        description="Operators with statuses newer than their data on the map."
    )
    left_out: dict[str, str] = Field(
        default_factory=dict,
        description="Operators whose snapshot was not used, each with the reason in neutral words.",
    )


class RefreshEntry(_Model):
    """What one status refresh did for one operator (pipeline.refresh)."""

    fetched_at: AwareDatetime | None = Field(
        description="When the statuses in the operator's snapshot were fetched. Null when "
        "it has no snapshot."
    )
    last_contact_at: AwareDatetime | None = Field(
        description="When this project last finished asking the operator's host in a "
        "refresh, so the next run can keep the host's gap across runs. Null if never."
    )
    refreshed: bool = Field(description="True when this run wrote a new snapshot.")
    requests: int | None = Field(default=None, ge=0, description="Requests this run made.")
    locations: int = Field(default=0, ge=0, description="Locations in the snapshot.")
    evses: int = Field(default=0, ge=0, description="EVSEs in the snapshot.")
    not_on_map: int = Field(
        default=0, ge=0, description="Locations in the feed that the map does not show."
    )
    not_in_feed: int = Field(
        default=0, ge=0, description="Locations on the map that the feed did not list."
    )
    ambiguous: int = Field(
        default=0, ge=0, description="Locations whose id matched more than one on the map."
    )
    note: str | None = Field(
        default=None, description="Why there is no new snapshot, in neutral words."
    )


class RefreshLog(_Model):
    """A record of one status refresh, kept with its snapshots (live/refresh.json)."""

    schema_version: Literal[1] = LIVE_SCHEMA_VERSION
    generated_at: AwareDatetime = Field(description="When the refresh finished.")
    map_generated_at: AwareDatetime = Field(
        description="generated_at of the map files the snapshots were laid over."
    )
    operators: dict[str, RefreshEntry]
