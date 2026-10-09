"""The live status snapshot (Phase 3, docs/PHASE3_PLAN.md and ADR 0015).

One file per operator: the status of every EVSE at every location the map shows, keyed
by the same location key as the map's detail files (pipeline.publish.location_key). The
pipeline builds it from operator feeds with the same polite client and normalisers as the
daily run, and the live Worker (proxy/worker.js) stores and serves it without reading
operator feeds itself. Nothing on the site uses it yet.
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
