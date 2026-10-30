# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""present_venue_map is provenance-anchored and built from live inventory."""

import pytest

from commerce_common.presentation import EnrichmentContext
from entertainment.api.venue_map import VenueMapPayload, _enrich
from shopping_agent import ShoppingSessionState


def _context(backend, seen_ids):
    state = ShoppingSessionState()
    state.remember_products([backend.get_live_product(pid) for pid in seen_ids])
    return EnrichmentContext(backend=backend, config=None, session=None, state=state)


async def test_event_must_be_anchored_in_session_provenance(backend):
    payload = VenueMapPayload(product_id="AT-TIX-101-PIT")
    with pytest.raises(ValueError, match="Search"):
        await _enrich(payload, _context(backend, []))


async def test_sections_are_built_from_the_fixture_and_live_inventory(backend):
    payload = VenueMapPayload(product_id="AT-TIX-101-PIT", highlight_product_ids=["AT-TIX-101-PIT"])
    enriched = await _enrich(payload, _context(backend, ["AT-TIX-101-PIT"]))

    assert enriched["venue"]["name"] == "ACME Amphitheater"
    assert enriched["event"]["date"] == "2026-08-14"
    sections = {s["section_id"]: s for s in enriched["sections"]}
    assert sections["STAGE"]["kind"] == "stage" and "price_all_in" not in sections["STAGE"]
    pit = sections["PIT"]
    assert pit["price_all_in"] == 112.0
    assert pit["remaining"] == 6
    assert pit["status"] == "on_sale"
    assert pit["highlighted"] is True
    # The lower bowl tier spans several map blocks.
    assert sections["LOWER-L"]["product_id"] == "AT-TIX-101-LOW"
    assert sections["LOWER-C"]["remaining"] == 385


async def test_sold_out_event_sections_read_sold_out(backend):
    payload = VenueMapPayload(product_id="AT-TIX-103-TER")
    enriched = await _enrich(payload, _context(backend, ["AT-TIX-103-TER"]))
    tiers = [s for s in enriched["sections"] if s.get("product_id")]
    assert tiers and all(s["status"] == "sold_out" and s["remaining"] == 0 for s in tiers)


async def test_unseen_highlights_and_recommendations_are_dropped(backend):
    payload = VenueMapPayload(
        product_id="AT-TIX-101-PIT",
        highlight_product_ids=["AT-TIX-101-LOW"],  # not seen in this session
        recommended_product_id="AT-TIX-101-LOW",
    )
    enriched = await _enrich(payload, _context(backend, ["AT-TIX-101-PIT"]))
    sections = {s["section_id"]: s for s in enriched["sections"]}
    assert sections["LOWER-L"]["highlighted"] is False
    assert "recommended_product_id" not in enriched


async def test_the_payload_carries_no_chips_of_its_own(backend):
    payload = VenueMapPayload(product_id="AT-TIX-103-TER")
    enriched = await _enrich(payload, _context(backend, ["AT-TIX-103-TER"]))
    assert "suggestions" not in enriched


async def test_all_tier_highlights_collapse_to_the_recommended_steer(backend):
    seen = ["AT-TIX-101-PIT", "AT-TIX-101-LOW", "AT-TIX-101-TER"]
    payload = VenueMapPayload(
        product_id="AT-TIX-101-LOW",
        highlight_product_ids=seen,
        recommended_product_id="AT-TIX-101-LOW",
    )
    enriched = await _enrich(payload, _context(backend, seen))
    highlighted = {s["product_id"] for s in enriched["sections"] if s.get("highlighted")}
    assert highlighted == {"AT-TIX-101-LOW"}

    payload = VenueMapPayload(product_id="AT-TIX-101-LOW", highlight_product_ids=seen)
    enriched = await _enrich(payload, _context(backend, seen))
    assert not any(s.get("highlighted") for s in enriched["sections"])

    payload = VenueMapPayload(product_id="AT-TIX-101-LOW", highlight_product_ids=["AT-TIX-101-PIT"])
    enriched = await _enrich(payload, _context(backend, seen))
    highlighted = {s["product_id"] for s in enriched["sections"] if s.get("highlighted")}
    assert highlighted == {"AT-TIX-101-PIT"}
