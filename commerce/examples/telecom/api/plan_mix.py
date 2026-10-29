# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""``present_plan_mix``: the subscriber base per plan (lines, share, churn, ARPU, per-line
economics, weekly trend). The model names the plans and an optional caption each; every
figure comes from the merchant backend."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from commerce_common.presentation import EnrichmentContext, PresentationExtension

from .mock_merchant import MockTelecomMerchant


class PlanMixPayload(BaseModel):
    plan_ids: list[str] = Field(min_length=1, max_length=8)
    notes: dict[str, str] = Field(
        default_factory=dict,
        description="Optional short caption per plan_id (e.g. why this plan matters now).",
    )


# The JSON schema the model sees; the payload model above is what the executor enforces.
_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "plan_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 8,
            "items": {"type": "string"},
        },
        "notes": {
            "type": "object",
            "additionalProperties": {"type": "string", "maxLength": 200},
            "description": "Optional short caption per plan_id (e.g. why this plan matters now).",
        },
    },
    "required": ["plan_ids"],
    "additionalProperties": False,
}


def build_plan_mix_extension(backend: MockTelecomMerchant) -> PresentationExtension:
    async def _enrich(payload: PlanMixPayload, context: EnrichmentContext) -> dict[str, Any]:
        del context  # bound to its backend at construction
        rows = backend.plan_mix_rows(payload.plan_ids)
        if not rows:
            raise ValueError(
                "None of those ids are plans in this carrier's subscriber data. Search the "
                "catalog listings first and use plan or home-internet ids from the results."
            )
        plans: list[dict[str, Any]] = []
        for row in rows:
            entry = dict(row)
            note = payload.notes.get(row["plan_id"])
            if note:
                entry["note"] = note[:200]
            plans.append(entry)
        enriched: dict[str, Any] = {
            "total_subscribers": backend.total_subscribers(),
            "grain": "week",
            "plans": plans,
        }
        return enriched

    return PresentationExtension(
        name="present_plan_mix",
        component="plan_mix",
        description=(
            "Show the subscriber-base panel for one or more of the carrier's plans or "
            "home-internet tiers: active lines and share of base, monthly churn, ARPU, "
            "wholesale cost and margin per line, and the weekly subscriber trend. Use it "
            "when discussing plan mix, churn, or margin, or before staging a plan price or "
            "retention move; pass plan_ids from this session's listing results — the panel "
            "numbers are filled in from the carrier's own data."
        ),
        input_schema=_INPUT_SCHEMA,
        payload_model=PlanMixPayload,
        enrich=_enrich,
    )
