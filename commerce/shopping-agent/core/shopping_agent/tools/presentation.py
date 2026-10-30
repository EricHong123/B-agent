# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Payload schemas for the built-in presentation tools: what the model may send. The
joins that turn a payload into what the host renders live in ``enrichment``."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from commerce_common.presentation import PresentationPayload


class ProductPick(BaseModel):
    product_id: str
    reason: str | None = Field(default=None, max_length=140)


class PresentProductsPayload(PresentationPayload):
    """The model sends ``picks``; the host receives ``items``, each pick joined to its
    catalog record."""

    title: str | None = Field(default=None, max_length=80)
    layout: Literal["carousel", "grid", "list"] = "carousel"
    picks: list[ProductPick] = Field(min_length=1, max_length=12)


class ComparisonEntry(BaseModel):
    product_id: str
    pros: list[str] = Field(default_factory=list, max_length=4)
    cons: list[str] = Field(default_factory=list, max_length=3)
    best_for: str | None = Field(default=None, max_length=80)


class PresentComparisonPayload(PresentationPayload):
    title: str | None = Field(default=None, max_length=80)
    entries: list[ComparisonEntry] = Field(min_length=2, max_length=4)
    dimensions: list[str] = Field(default_factory=list, max_length=6)
    recommended_product_id: str | None = None


class PlanStep(BaseModel):
    label: str = Field(max_length=120)
    detail: str | None = Field(default=None, max_length=240)
    product_ids: list[str] = Field(default_factory=list, max_length=8)


class PresentPlanPayload(PresentationPayload):
    title: str = Field(max_length=80)
    intro: str | None = Field(default=None, max_length=240)
    steps: list[PlanStep] = Field(min_length=1, max_length=12)


class GuideSection(BaseModel):
    heading: str = Field(max_length=80)
    body: str = Field(max_length=600)


class PresentGuidePayload(PresentationPayload):
    """``related_product_ids`` become ``related_products`` on the host payload, and
    ``policy_ids`` become ``evidence``: each passage's source, version, and window."""

    title: str = Field(max_length=80)
    sections: list[GuideSection] = Field(min_length=1, max_length=8)
    related_product_ids: list[str] = Field(default_factory=list, max_length=8)
    sources: list[str] = Field(default_factory=list, max_length=5)
    policy_ids: list[str] = Field(default_factory=list, max_length=5)


class PresentOrderStatusPayload(PresentationPayload):
    order_id: str
    summary: str = Field(max_length=300)
    next_step: str | None = Field(default=None, max_length=200)


class CheckoutPayload(PresentationPayload):
    """Stages the cart for the host's checkout; nothing here charges."""

    note: str | None = Field(default=None, max_length=300)
    fulfillment_method: Literal["delivery", "pickup", "shipping"] | None = None


class PresentDisclosurePayload(PresentationPayload):
    """The model picks the product; the host renders the backend's disclosure record,
    including the record's own title. ``title`` here is accepted and unused."""

    product_id: str
    title: str | None = Field(default=None, max_length=80)
