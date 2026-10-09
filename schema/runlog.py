"""The run log: one file per operator per run, written by `pipeline.run --log-dir`.

Logs hold counts, health figures and logged problems, never records or keys. The feed
health page (pipeline/status.py) publishes nothing a log does not hold, and refuses a log
with any field not listed here.
"""

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

MAX_ISSUE_LENGTH = 500


class _LogModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ModuleSummary(_LogModel):
    pages: int = Field(ge=0)
    records: int = Field(ge=0)
    reported: int | None = Field(ge=0)
    complete: bool


class KeptCounts(_LogModel):
    locations: int = Field(ge=0)
    tariffs: int = Field(ge=0)


class Health(_LogModel):
    """Figures counted from what was received, for the feed health page."""

    locations: int = Field(ge=0)
    locations_in_uk: int = Field(ge=0, description="Coordinates in the UK (pipeline/geography.py).")
    evses: int = Field(ge=0)
    evses_with_status: int = Field(ge=0, description="Status other than unknown.")
    connectors: int = Field(ge=0)
    connectors_with_tariff: int = Field(
        ge=0, description="At least one listed tariff was found in the operator's tariffs."
    )
    median_last_updated_days: float | None = Field(
        ge=0,
        description="Median age, at fetch time, of the locations' own last_updated dates. "
        "Null when no location gives one.",
    )


class RunLog(_LogModel):
    """The only fields a run log may have."""

    operator: str = Field(pattern=r"^[a-z0-9_]+$")
    mode: Literal["fixtures", "live"]
    fetched_at: str = Field(pattern=r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}Z$")
    requests: int | None = Field(ge=0)
    complete: bool
    failed: bool
    error: Annotated[str, Field(max_length=MAX_ISSUE_LENGTH)] | None
    modules: dict[Literal["locations", "tariffs"], ModuleSummary]
    kept: KeptCounts
    health: Health | None = Field(description="Null when the run failed.")
    issues: list[Annotated[str, Field(max_length=MAX_ISSUE_LENGTH)]]
