# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""``present_venue_map``: a schematic of the room (labelled tier blocks in a small
viewbox, not seat geometry). The model names a ticket of the event and may highlight or
recommend tiers; every block, price, and count is built here from the venue fixture and
live inventory."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from commerce_common.presentation import EnrichmentContext, PresentationExtension


class VenueMapPayload(BaseModel):
    # Anchored on a ticket product_id because search results carry product ids, not
    # event ids; the event is read from that product's record.
    product_id: str
    title: str | None = Field(default=None, max_length=80)
    highlight_product_ids: list[str] = Field(default_factory=list, max_length=4)
    recommended_product_id: str | None = None


# The JSON schema the model sees; the payload model above is what the executor enforces.
_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "product_id": {
            "type": "string",
            "description": (
                "Any ticket product_id for the event, from this session's search "
                "results — the schematic renders that product's whole event."
            ),
        },
        "title": {"type": "string", "maxLength": 80},
        "highlight_product_ids": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 4,
            "description": "Ticket product_ids from this session's results to visually highlight.",
        },
        "recommended_product_id": {"type": "string"},
    },
    "required": ["product_id"],
    "additionalProperties": False,
}


async def _enrich(payload: VenueMapPayload, context: EnrichmentContext) -> dict[str, Any]:
    backend = context.backend
    seen = context.state.seen_products

    sample = backend.products.get(payload.product_id)
    if (
        payload.product_id not in seen
        or sample is None
        or sample.category not in {"tickets", "resale"}
    ):
        raise ValueError(
            "That product_id isn't a ticket from this session's catalog results. Search "
            "for the event's tickets first, then map the venue using one of those "
            "ticket product_ids."
        )
    event_id = sample.attributes.get("event_id", "")

    venue = backend.venues.get(sample.attributes.get("venue_id", ""))
    if venue is None:
        raise ValueError("No venue schematic exists for that event.")

    # Every tier of the event, seen or not: the schematic shows the whole room.
    tiers_by_code = {
        product.attributes.get("tier_code"): product
        for product in backend.products.values()
        if product.attributes.get("event_id") == event_id and product.category == "tickets"
    }

    highlight = {
        pid for pid in payload.highlight_product_ids if pid in seen and pid in backend.products
    }
    recommended = (
        payload.recommended_product_id
        if payload.recommended_product_id in seen
        and payload.recommended_product_id in backend.products
        else None
    )
    # Highlighting every tier highlights nothing; collapse to the recommendation.
    tier_ids = {product.product_id for product in tiers_by_code.values()}
    if tier_ids and tier_ids <= highlight:
        highlight = {recommended} if recommended else set()

    sections: list[dict[str, Any]] = []
    for section in venue["sections"]:
        entry: dict[str, Any] = {
            "section_id": section["section_id"],
            "label": section["label"],
            "kind": section["kind"],
            "x": section["x"],
            "y": section["y"],
            "w": section["w"],
            "h": section["h"],
        }
        if "short_label" in section:
            # The label small blocks fall back to when the tier name will not fit.
            entry["short_label"] = section["short_label"]
        tier = tiers_by_code.get(section.get("tier_code"))
        if tier is not None:
            remaining = backend.engine.remaining(tier.product_id)
            entry |= {
                "product_id": tier.product_id,
                "tier": tier.attributes.get("tier"),
                "price_all_in": tier.price,
                "currency": tier.currency,
                "remaining": remaining,
                "status": "sold_out" if remaining == 0 else "on_sale",
                "highlighted": tier.product_id in highlight,
            }
        sections.append(entry)

    enriched: dict[str, Any] = {
        "event": {
            "event_id": event_id,
            "name": sample.attributes.get("event_name"),
            "date": sample.attributes.get("event_date"),
            "time": sample.attributes.get("event_time"),
        },
        "venue": {
            "venue_id": venue["venue_id"],
            "name": venue["name"],
            "city": venue["city"],
            "viewbox": venue["viewbox"],
        },
        "sections": sections,
    }
    if payload.title:
        enriched["title"] = payload.title
    if recommended:
        enriched["recommended_product_id"] = recommended
    return enriched


def build_venue_map_extension() -> PresentationExtension:
    return PresentationExtension(
        name="present_venue_map",
        component="venue_map",
        description=(
            "Show a stylized venue schematic for one event: every tier as a labeled, "
            "color-codable block with its live all-in price and availability. Use when "
            "the user is choosing between tiers or asks where seats are. Pass any "
            "ticket product_id for the event from this session's search results; the "
            "UI renders that product's whole event and fills in every price and count "
            "from the venue's live inventory. You may highlight up to 4 tier "
            "product_ids and recommend one."
        ),
        input_schema=_INPUT_SCHEMA,
        payload_model=VenueMapPayload,
        enrich=_enrich,
    )
