# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Every count derives from live inventory; the value score is computed here."""

from shopping_agent import SearchFilters


async def _result(backend, session, query, product_id, filters=None):
    results = await backend.search_products(session, query, filters, limit=20)
    return next((p for p in results if p.product_id == product_id), None)


async def test_remaining_count_matches_inventory_state(backend, session):
    pit = await _result(backend, session, "headliner friday pit", "AT-TIX-101-PIT")
    assert pit.attributes["tickets_remaining"] == "6"  # 350 capacity - 344 sold
    assert pit.labels == ["Selling fast, 6 left"]
    assert pit.in_stock is True


async def test_holds_in_another_session_lower_the_count_everyone_sees(
    backend, session, other_session
):
    await backend.add_to_cart(other_session, "AT-TIX-101-PIT", 2)
    pit = await _result(backend, session, "headliner friday pit", "AT-TIX-101-PIT")
    assert pit.attributes["tickets_remaining"] == "4"
    assert pit.labels == ["Selling fast, 4 left"]


async def test_expired_holds_put_the_count_back(backend, session, other_session, clock):
    await backend.add_to_cart(other_session, "AT-TIX-101-PIT", 2)
    clock.advance(10_000)
    pit = await _result(backend, session, "headliner friday pit", "AT-TIX-101-PIT")
    assert pit.attributes["tickets_remaining"] == "6"


async def test_sold_out_tier_stays_findable_and_reads_sold_out(backend, session):
    pit = await _result(backend, session, "synth-pop act fall tour", "AT-TIX-103-PIT")
    assert pit is not None
    assert pit.in_stock is False
    assert pit.labels == ["Sold out, waitlist open"]
    assert pit.attributes["tickets_remaining"] == "0"


async def test_roomy_tiers_carry_no_urgency_label(backend, session):
    terrace = await _result(backend, session, "headliner friday terrace", "AT-TIX-101-TER")
    assert terrace.labels == []  # 900 capacity - 348 sold = 552 left


async def test_min_quantity_is_a_hard_filter_on_live_inventory(backend, session):
    filters = SearchFilters(attributes={"min_quantity": "7"})
    pit = await _result(backend, session, "headliner friday pit", "AT-TIX-101-PIT", filters)
    assert pit is None  # 6 open
    low = await _result(backend, session, "headliner friday lower", "AT-TIX-101-LOW", filters)
    assert low is not None


async def test_value_score_is_deterministic_and_server_computed(backend, session):
    below_face = await _result(backend, session, "resale headliner", "AT-RSL-203")
    assert below_face.attributes["value_score"] == "10"
    assert below_face.attributes["value_verdict"] == "green"
    assert below_face.attributes["vs_box_office"] == "-28%"
    assert below_face.attributes["box_office_all_in_usd"] == "89.00"

    above_market = await _result(backend, session, "resale jane doe", "AT-RSL-204")
    assert above_market.attributes["value_score"] == "4"
    assert above_market.attributes["value_verdict"] == "red"
    assert above_market.attributes["vs_box_office"] == "+29%"


async def test_sold_out_primary_bumps_the_resale_score(backend, session):
    # The terrace resale is +9% over box office (base score 6); the sold-out box office
    # adds one point.
    listing = await _result(backend, session, "resale synth-pop act terrace", "AT-RSL-202")
    assert listing.attributes["value_score"] == "7"
    assert listing.attributes["value_verdict"] == "amber"
