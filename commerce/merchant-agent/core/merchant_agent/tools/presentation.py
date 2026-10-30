# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Payload schemas for the built-in presentation tools: what the model may send. The
joins that turn a payload into what the portal renders live in ``enrichment``."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from commerce_common.presentation import PresentationPayload

# The card a stage call also renders when ``stage_shows_preview`` is on.
PREVIEW_TOOL = "present_change_preview"


class MetricPick(BaseModel):
    """One tile: the model names the metric and annotates it; the value is joined
    from what the tools returned."""

    metric: str = Field(max_length=60)
    note: str | None = Field(default=None, max_length=140)


class PresentMetricsPayload(PresentationPayload):
    title: str | None = Field(default=None, max_length=80)
    period: str | None = Field(default=None, max_length=80)
    picks: list[MetricPick] = Field(min_length=1, max_length=8)


class DigestItem(BaseModel):
    kind: Literal["low_stock", "slow_mover", "order_issue", "metric", "pending_change", "note"]
    ref_id: str | None = Field(default=None, max_length=64)
    headline: str = Field(max_length=120)
    why_it_matters: str | None = Field(default=None, max_length=160)


class PresentDigestPayload(PresentationPayload):
    title: str | None = Field(default=None, max_length=80)
    items: list[DigestItem] = Field(min_length=1, max_length=8)


class PresentChangePreviewPayload(PresentationPayload):
    """The model picks the change; every diff line and figure on the card comes from
    the staged record."""

    change_id: str
    headline: str | None = Field(default=None, max_length=120)
    note: str | None = Field(default=None, max_length=200)
