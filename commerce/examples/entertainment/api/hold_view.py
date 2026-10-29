# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""``present_hold``: the card for tickets held on the server timer but not bought. The
model supplies at most a note; the lines, total, and countdown come from the session's
live holds."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from commerce_common.presentation import EnrichmentContext, PresentationExtension
from shopping_agent import cart_payload

from .ticketing import HOLD_TTL_S


class HoldViewPayload(BaseModel):
    note: str | None = Field(default=None, max_length=200)


# The JSON schema the model sees; the payload model above is what the executor enforces.
_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "note": {
            "type": "string",
            "maxLength": 200,
            "description": "One optional short line of context above the held lines.",
        },
    },
    "additionalProperties": False,
}


async def _enrich(payload: HoldViewPayload, context: EnrichmentContext) -> dict[str, Any]:
    backend = context.backend
    session = context.session
    holds = backend.engine.holds_for_session(session.session_id)
    if not holds:
        raise ValueError(
            "No hold is running for this session; add the tickets to the cart first "
            "(that places the timed hold), then present it."
        )
    cart = await backend.get_cart(session)
    enriched: dict[str, Any] = {
        "cart": cart_payload(cart),
        "hold": {
            "seconds_remaining": min(
                backend.engine.seconds_until(hold.expires_at) for hold in holds
            ),
            "hold_minutes": HOLD_TTL_S // 60,
        },
    }
    if payload.note:
        enriched["note"] = payload.note
    return enriched


def build_hold_view_extension() -> PresentationExtension:
    return PresentationExtension(
        name="present_hold",
        component="hold",
        description=(
            "Show the live hold card: every held ticket line, the all-in total, and the "
            "real countdown until the seats release. Use it right after add_to_cart "
            "places or grows a ticket hold and the customer is pausing (finding a card, "
            "still deciding) rather than checking out. Holds are not orders — never "
            "present a hold with present_order_status; use checkout only when the "
            "customer says they are ready to pay."
        ),
        input_schema=_INPUT_SCHEMA,
        payload_model=HoldViewPayload,
        enrich=_enrich,
    )
