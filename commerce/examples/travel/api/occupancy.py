# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""``present_occupancy_calendar``: weekly occupancy, pace, and applied rate overrides for
the supplier's stays over a date window. The model names the stays, the window, and an
optional caption each; every figure comes from the merchant backend."""

from __future__ import annotations

from datetime import date
from typing import Any

from pydantic import BaseModel, Field

from commerce_common.presentation import EnrichmentContext, PresentationExtension

from .mock_merchant import MockTravelMerchant


class OccupancyCalendarPayload(BaseModel):
    listing_ids: list[str] = Field(min_length=1, max_length=6)
    start: str = Field(max_length=10, description="Window start, YYYY-MM-DD.")
    end: str = Field(max_length=10, description="Window end, YYYY-MM-DD.")
    notes: dict[str, str] = Field(
        default_factory=dict,
        description="Optional short caption per listing_id (e.g. why this window matters).",
    )


# The JSON schema the model sees; the payload model above is what the executor enforces.
_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "listing_ids": {
            "type": "array",
            "minItems": 1,
            "maxItems": 6,
            "items": {"type": "string"},
        },
        "start": {"type": "string", "maxLength": 10, "description": "Window start, YYYY-MM-DD."},
        "end": {"type": "string", "maxLength": 10, "description": "Window end, YYYY-MM-DD."},
        "notes": {
            "type": "object",
            "additionalProperties": {"type": "string", "maxLength": 200},
            "description": "Optional short caption per listing_id (e.g. why this window matters).",
        },
    },
    "required": ["listing_ids", "start", "end"],
    "additionalProperties": False,
}


def _parse_window(start_text: str, end_text: str) -> tuple[date, date]:
    try:
        start = date.fromisoformat(start_text)
        end = date.fromisoformat(end_text)
    except ValueError as error:
        raise ValueError(
            "start and end must be ISO dates (YYYY-MM-DD) — adjust them and call "
            "present_occupancy_calendar again."
        ) from error
    if end < start:
        raise ValueError("The window end is before its start — swap the dates and try again.")
    return start, end


def build_occupancy_extension(backend: MockTravelMerchant) -> PresentationExtension:
    async def _enrich(
        payload: OccupancyCalendarPayload, context: EnrichmentContext
    ) -> dict[str, Any]:
        del context  # bound to its backend at construction
        start, end = _parse_window(payload.start, payload.end)
        rows = await backend.get_occupancy_calendar(payload.listing_ids, start, end)
        if not rows:
            raise ValueError(
                "None of those listing ids are in this supplier's occupancy data. Search the "
                "portfolio listings first and use ids from the results."
            )
        if all(not row.get("weeks") for row in rows):
            raise ValueError(
                "The occupancy data doesn't cover that date range. Ask for dates within the "
                "supplier's published calendar window instead."
            )
        listings: list[dict[str, Any]] = []
        for row in rows:
            entry = dict(row)
            note = payload.notes.get(row["listing_id"])
            if note:
                entry["note"] = note[:200]
            listings.append(entry)
        enriched: dict[str, Any] = {
            "start": start.isoformat(),
            "end": end.isoformat(),
            "grain": "week",
            "listings": listings,
        }
        return enriched

    return PresentationExtension(
        name="present_occupancy_calendar",
        component="occupancy_calendar",
        description=(
            "Show the weekly occupancy and pacing calendar for one or more of the supplier's "
            "stays over a date window: nightly rate, midweek and weekend occupancy, "
            "on-the-books pace, and any rate override already applied to that window. Use it "
            "when discussing date-bound demand or before staging a rate move; pass listing_ids "
            "from this session's listing results — the calendar numbers are filled in from the "
            "supplier's own data."
        ),
        input_schema=_INPUT_SCHEMA,
        payload_model=OccupancyCalendarPayload,
        enrich=_enrich,
    )
