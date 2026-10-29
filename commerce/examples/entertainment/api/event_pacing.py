# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""``present_event_pacing``: live sell-through per event and tier against the baseline of
comparable events, with hold buckets and waitlist depth. The model names the events and
an optional caption each; every figure comes from the engine and the pacing book."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from commerce_common.presentation import EnrichmentContext, PresentationExtension

from .mock_merchant import MockTicketingMerchant


class EventPacingPayload(BaseModel):
    event_ids: list[str] = Field(min_length=1, max_length=4)
    notes: dict[str, str] = Field(
        default_factory=dict,
        description="Optional short caption per event_id (e.g. why this event needs attention).",
    )


# The JSON schema the model sees; the payload model above is what the executor enforces.
_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "event_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 4,
            "items": {"type": "string"},
        },
        "notes": {
            "type": "object",
            "additionalProperties": {"type": "string", "maxLength": 200},
            "description": "Optional short caption per event_id (e.g. why this event needs attention).",
        },
    },
    "required": ["event_ids"],
    "additionalProperties": False,
}


def build_event_pacing_extension(backend: MockTicketingMerchant) -> PresentationExtension:
    async def _enrich(payload: EventPacingPayload, context: EnrichmentContext) -> dict[str, Any]:
        del context  # bound to its backend at construction
        rows = backend.event_pacing_rows(payload.event_ids)
        if not rows:
            raise ValueError(
                "None of those ids are events in this promoter's pacing book. Search the "
                "portfolio listings first and use event ids from the results (the tier "
                "listings carry their event_id)."
            )
        events: list[dict[str, Any]] = []
        for row in rows:
            entry = dict(row)
            note = payload.notes.get(row["event_id"])
            if note:
                entry["note"] = note[:200]
            events.append(entry)
        enriched: dict[str, Any] = {"grain": "week", "events": events}
        return enriched

    return PresentationExtension(
        name="present_event_pacing",
        component="event_pacing",
        description=(
            "Show the sell-through pacing panel for one or more of the promoter's events: "
            "per tier, the live sold/open counts, sell-through against the comparable-events "
            "baseline at today's days-to-event, hold and kill buckets, waitlist depth, and "
            "the weekly sales history. Use it when discussing how a show is filling or "
            "before staging a price step or hold release; pass event_ids from this session's "
            "listing results — the panel numbers are filled in from the live engine."
        ),
        input_schema=_INPUT_SCHEMA,
        payload_model=EventPacingPayload,
        enrich=_enrich,
    )
