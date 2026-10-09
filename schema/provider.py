"""Model for one charging plan provider file (providers/<id>.yaml).

A provider is anyone a driver can pay for charging through: a roaming app such as
Octopus Electroverse, or an operator's own app and subscriptions. Operator open data
feeds rarely say what a subscription costs, so each plan here is copied by hand from the
provider's own published page, with the page, an exact quote and the date it was read
(owner's decision, 9 October 2026: feed prices where they exist, plus a dated list from
providers' own pages).

Rules the model enforces:
- A plan is only kept when the provider's terms allow it to be reused: no restriction
  found, or reuse allowed with attribution. Providers whose terms forbid copying keep
  their file (so the check is recorded) but list no plans.
- Every plan has a source on the provider's own site, an exact quote and a date.
- Prices are in pounds and pence. A price or fee that is not published is left out
  (null), never estimated.
- A plan whose published figures disagree with another of the provider's own pages says
  so in needs_testing, and the map shows that note with it.
"""

import datetime as dt
from decimal import Decimal
from typing import Annotated, Literal
from urllib.parse import urlsplit

from pydantic import Field, model_validator

from schema.operator import NeutralText, SafeUrl, _Model

ProviderId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_]*$")]
PlanId = Annotated[str, Field(pattern=r"^[a-z0-9][a-z0-9_]*$")]
ProviderKind = Literal["roaming", "operator"]
Reuse = Literal["no_restriction_found", "attribution", "personal_use_only", "forbidden"]
REUSABLE: tuple[str, ...] = ("no_restriction_found", "attribution")
Money = Annotated[Decimal, Field(ge=0, max_digits=8, decimal_places=4)]


class ProviderTerms(_Model):
    url: SafeUrl | None = Field(default=None, description="The provider's terms page.")
    reuse: Reuse = Field(description="What the terms say about copying or reusing content.")
    quote: str | None = Field(
        default=None,
        min_length=1,
        description="The clause on reuse, word for word, or null when none was found.",
    )
    attribution: NeutralText | None = Field(
        default=None, description="Wording to show when the terms ask for attribution."
    )
    checked: dt.date

    @model_validator(mode="after")
    def _check(self) -> "ProviderTerms":
        if self.reuse == "attribution" and not self.attribution:
            raise ValueError("terms that ask for attribution need the attribution wording")
        if self.reuse in ("personal_use_only", "forbidden") and not self.quote:
            raise ValueError("a restriction needs the provider's own words in quote")
        return self


class PlanSource(_Model):
    url: SafeUrl
    quote: str = Field(min_length=1, description="Copied word for word from the page.")
    checked: dt.date


class Plan(_Model):
    id: PlanId
    name: str = Field(min_length=1, description="The plan's name as the provider writes it.")
    pay_by: str = Field(
        min_length=1,
        description="How the driver pays, in plain words, for example 'Electroverse app or "
        "Electrocard'.",
    )
    monthly_fee: Money | None = Field(
        default=None,
        description="Pounds per month including VAT; 0 for no fee; null when not published.",
    )
    fee_note: NeutralText | None = Field(
        default=None, description="Minimum term, annual option, trial and so on."
    )
    price_per_kwh: Money | None = Field(
        default=None, description="Pounds per kWh including VAT, when a fixed price is published."
    )
    discount_percent: Annotated[Decimal, Field(gt=0, lt=100)] | None = Field(
        default=None, description="Percentage off, when the plan is published as a discount."
    )
    discount_of: NeutralText | None = Field(
        default=None,
        description="What the discount is taken off, in plain words, for example "
        '"Electroverse\'s own price on the IONITY network".',
    )
    includes_vat: bool | None = Field(
        description="Whether the provider says its prices include VAT; null when not stated."
    )
    networks: list[str] = Field(
        min_length=1, description="Networks the plan applies to, as the provider names them."
    )
    operator_ids: list[str] = Field(
        default_factory=list,
        description="Ids from operators/ for those networks, so the map can show the plan "
        "at their locations. Only networks this project has a registry file for.",
    )
    conditions: NeutralText | None = Field(
        default=None, description="Times of day, charger speeds, caps or other fees."
    )
    needs_testing: NeutralText | None = Field(
        default=None,
        description="Set when the provider's own pages disagree or something is unclear.",
    )
    source: PlanSource

    @model_validator(mode="after")
    def _check(self) -> "Plan":
        if (
            self.monthly_fee is None
            and self.price_per_kwh is None
            and self.discount_percent is None
        ):
            raise ValueError("a plan needs a published fee, price or discount")
        if self.price_per_kwh is not None and self.discount_percent is not None:
            raise ValueError("give a fixed price or a discount, not both")
        if self.discount_percent is not None and not self.discount_of:
            raise ValueError("a discount needs discount_of: what it is taken off")
        if self.discount_percent is None and self.discount_of:
            raise ValueError("discount_of is only for discounts")
        return self


class ProviderFile(_Model):
    id: ProviderId
    name: str = Field(min_length=1)
    kind: ProviderKind
    website: SafeUrl
    terms: ProviderTerms
    plans: list[Plan] = Field(default_factory=list)
    notes: NeutralText | None = None

    @model_validator(mode="after")
    def _check(self) -> "ProviderFile":
        if self.plans and self.terms.reuse not in REUSABLE:
            raise ValueError(
                f"terms.reuse is {self.terms.reuse!r}: plans may only be listed when the "
                "provider's terms allow reuse"
            )
        ids = [p.id for p in self.plans]
        if len(ids) != len(set(ids)):
            raise ValueError("plan ids must be unique within a provider")
        site = _host(self.website)
        for plan in self.plans:
            if _host(plan.source.url) != site and not _host(plan.source.url).endswith("." + site):
                raise ValueError(
                    f"plan {plan.id!r}: its source must be on the provider's own site ({site})"
                )
        return self


def _host(url: str) -> str:
    host = (urlsplit(url).hostname or "").lower()
    return host.removeprefix("www.")
