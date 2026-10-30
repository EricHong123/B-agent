# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

from commerce_common.presentation import invalid_payload_prefix
from travel.api.itinerary import build_itinerary_extension


async def test_invalid_payload_is_a_soft_error(executor):
    result = await executor.execute("present_itinerary", {"title": "x" * 200, "days": []})
    assert result.is_error
    assert result.result_text.startswith(invalid_payload_prefix("present_itinerary"))


async def test_enrichment_resolves_only_provenance_seen_products(executor):
    await executor.execute("search_products", {"query": "Lisbon", "limit": 25})
    result = await executor.execute(
        "present_itinerary",
        {
            "title": "Three days in Lisbon",
            "travel_dates": "2026-09-14 to 2026-09-17",
            "days": [
                {
                    "label": "Day 1 — Arrive in Lisbon",
                    "note": "Check in, then wander the old town before dinner.",
                    "product_ids": ["AL-STAY-101", "AL-STAY-999"],
                },
                {"label": "Day 2 — Fado evening", "product_ids": ["AL-EXP-301"]},
            ],
            "suggestions": ["Add the stay to my trip", "Find a day trip"],
        },
    )
    assert not result.is_error
    ui = next(e for e in result.events if e.type == "ui")
    assert ui.data["component"] == "itinerary"
    payload = ui.data["payload"]
    assert payload["title"] == "Three days in Lisbon"
    assert payload["travel_dates"] == "2026-09-14 to 2026-09-17"
    # Chips a recorded call still carries are dropped; present_suggestions carries them.
    assert "suggestions" not in payload

    day_one, day_two = payload["days"]
    # The unknown id is dropped and the seen one is embedded as its catalog record.
    assert [p["product_id"] for p in day_one["products"]] == ["AL-STAY-101"]
    assert day_one["products"][0]["price"] == 214.0
    assert day_one["note"].startswith("Check in")
    assert "product_ids" not in day_one
    assert [p["product_id"] for p in day_two["products"]] == ["AL-EXP-301"]


async def test_products_never_seen_this_session_do_not_render(executor):
    result = await executor.execute(
        "present_itinerary",
        {"title": "Mystery trip", "days": [{"label": "Day 1", "product_ids": ["AL-STAY-101"]}]},
    )
    assert not result.is_error
    ui = next(e for e in result.events if e.type == "ui")
    assert ui.data["payload"]["days"][0]["products"] == []


async def test_enrichment_records_trip_plan_and_stamps_cancellation_deadlines(
    executor, backend, session
):
    await executor.execute("search_products", {"query": "Lisbon", "limit": 25})
    result = await executor.execute(
        "present_itinerary",
        {
            "title": "Lisbon long weekend",
            "travel_dates": "2026-10-15 to 2026-10-18",
            "days": [
                {"label": "Day 1 — Arrive", "product_ids": ["AL-STAY-101", "AL-STAY-104"]},
                {"label": "Day 2 — Old town", "product_ids": ["AL-EXP-301"]},
                {"label": "Day 4 — Fly home"},
            ],
        },
    )
    assert not result.is_error
    payload = next(e for e in result.events if e.type == "ui").data["payload"]

    # Day 1 to Day 4 is 3 nights, recorded for both Day 1 stays, so a quantity-1 add books 3.
    cart = await backend.add_to_cart(session, "AL-STAY-104", 1)
    assert cart.items[0].quantity == 3

    # Stays and experiences cut off 48 hours before their day; AL-STAY-101 is non-refundable.
    day_one, day_two, _ = payload["days"]
    by_id = {p["product_id"]: p for p in day_one["products"] + day_two["products"]}
    assert "free_cancellation_until" not in by_id["AL-STAY-101"]["attributes"]
    assert by_id["AL-STAY-104"]["attributes"]["free_cancellation_until"] == "2026-10-13"
    # The Day 2 experience falls on Oct 16, so its cutoff is Oct 14.
    assert by_id["AL-EXP-301"]["attributes"]["free_cancellation_until"] == "2026-10-14"


def test_parse_trip_start_reads_the_formats_models_write():
    from datetime import date, timedelta

    from travel.api.itinerary import _parse_trip_start

    assert _parse_trip_start("2026-10-15 to 2026-10-18") == date(2026, 10, 15)
    today = date.today()
    for text in ("Thu 15 Oct — Sun 18 Oct", "October 15–18", "Oct. 15 to Oct. 18"):
        start = _parse_trip_start(text)
        assert start is not None, text
        assert (start.month, start.day) == (10, 15), text
        # The next occurrence: at most about a month past, at most a year and a day ahead.
        assert today - timedelta(days=31) <= start <= today + timedelta(days=366), text
    assert _parse_trip_start("mid-October") is None
    assert _parse_trip_start(None) is None


async def test_undated_plan_stamps_no_deadlines(executor, backend, session):
    await executor.execute("search_products", {"query": "Lisbon", "limit": 25})
    result = await executor.execute(
        "present_itinerary",
        {
            "title": "Lisbon, sometime",
            "travel_dates": "mid-October",
            "days": [
                {"label": "Day 1 — Arrive", "product_ids": ["AL-STAY-104"]},
                {"label": "Day 3 — Fly home"},
            ],
        },
    )
    assert not result.is_error
    payload = next(e for e in result.events if e.type == "ui").data["payload"]
    stay = payload["days"][0]["products"][0]
    assert "free_cancellation_until" not in stay["attributes"]

    # Day 1 to Day 3 is 2 nights, recorded even without dates.
    cart = await backend.add_to_cart(session, "AL-STAY-104", 1)
    assert cart.items[0].quantity == 2


async def test_partial_enrichment_streams_days_with_provenance(executor, state):
    """Partial renders carry no suggestions."""
    from commerce_common.presentation import enrich_partial, partial_ui_tool_names

    extension = build_itinerary_extension()

    assert "present_itinerary" in partial_ui_tool_names({}, [extension])

    # No day label has closed yet, so there is nothing to render.
    assert enrich_partial(extension, {"title": "Lisbon"}, state) is None

    await executor.execute("search_products", {"query": "Lisbon", "limit": 25})
    prefix = {
        "title": "Three days in Lisbon",
        "travel_dates": "2026-09-14 to 2026-09-17",
        "days": [
            {"label": "Day 1 — Arrive", "product_ids": ["AL-STAY-101", "AL-STAY-9"]},
            {"label": "Day 2 — Old to"},  # label closed, rest still generating
        ],
        "suggestions": ["half-written sugg"],
    }
    enriched = enrich_partial(extension, prefix, state)
    assert enriched is not None
    component, payload, _signature = enriched
    assert component == "itinerary"
    assert payload["title"] == "Three days in Lisbon"
    assert payload["travel_dates"] == "2026-09-14 to 2026-09-17"
    assert "suggestions" not in payload
    day_one, day_two = payload["days"]
    assert [p["product_id"] for p in day_one["products"]] == ["AL-STAY-101"]
    assert day_one["products"][0]["price"] == 214.0
    assert day_two == {"label": "Day 2 — Old to", "products": []}


async def test_partial_enrichment_without_optin_stays_inert(state):
    from dataclasses import replace

    from commerce_common.presentation import enrich_partial, partial_ui_tool_names

    extension = replace(build_itinerary_extension(), enrich_partial=None)
    assert "present_itinerary" not in partial_ui_tool_names({}, [extension])
    assert (
        enrich_partial(extension, {"title": "Lisbon", "days": [{"label": "Day 1"}]}, state) is None
    )
