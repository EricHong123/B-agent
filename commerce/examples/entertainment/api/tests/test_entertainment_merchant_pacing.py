# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

from commerce_common.presentation import invalid_payload_prefix


async def test_enrichment_fills_the_panel_from_the_live_engine(merchant_executor):
    result = await merchant_executor.execute(
        "present_event_pacing",
        {
            "event_ids": ["AT-EVT-101", "AT-EVT-104"],
            "notes": {"AT-EVT-101": "Terrace pacing 16 points under the amphitheater curve."},
        },
    )
    assert not result.is_error
    ui = next(event for event in result.events if event.type == "ui")
    assert ui.data["component"] == "event_pacing"
    payload = ui.data["payload"]
    assert payload["grain"] == "week"
    assert "suggestions" not in payload
    assert [row["event_id"] for row in payload["events"]] == ["AT-EVT-101", "AT-EVT-104"]

    headliner = payload["events"][0]
    assert headliner["event_name"] == "The Headliner — Summer Tour"
    assert headliner["venue"] == "ACME Amphitheater"
    assert headliner["city"] == "Springfield"
    assert headliner["event_date"] == "2026-08-14"
    assert headliner["on_sale_date"] == "2026-05-08"
    assert headliner["days_to_event"] == 36  # pinned conftest clock: 2026-07-09
    assert headliner["baseline_kind"] == "amphitheater"
    assert headliner["note"] == "Terrace pacing 16 points under the amphitheater curve."

    pit = headliner["tiers"][0]
    assert pit["product_id"] == "AT-TIX-101-PIT"
    assert pit["tier"] == "GA Pit"
    assert (pit["capacity"], pit["sold"], pit["remaining"]) == (350, 344, 6)
    assert pit["sell_through_pct"] == round(344 / 350 * 100, 1)
    assert pit["baseline_pct"] == 55.2
    assert pit["pace_vs_baseline_pts"] == round(pit["sell_through_pct"] - 55.2, 1)
    assert pit["holds"] == {"promoter_hold": 8, "production_hold": 6, "comps": 8, "kills": 0}
    assert pit["waitlist_depth"] == 0
    assert len(pit["weekly_sold_cum"]) == 12

    duo = payload["events"][1]
    assert duo["baseline_kind"] == "club"
    assert "note" not in duo


async def test_reenrichment_tracks_live_engine_state(merchant_executor, merchant, backend):
    before = await merchant_executor.execute("present_event_pacing", {"event_ids": ["AT-EVT-101"]})
    tier = next(event for event in before.events if event.type == "ui").data["payload"]["events"][
        0
    ]["tiers"][1]
    assert (tier["product_id"], tier["remaining"]) == ("AT-TIX-101-LOW", 385)

    backend.engine.create_hold("s-fan", "demo-user", "AT-TIX-101-LOW", 5)
    after = await merchant_executor.execute("present_event_pacing", {"event_ids": ["AT-EVT-101"]})
    tier = next(event for event in after.events if event.type == "ui").data["payload"]["events"][0][
        "tiers"
    ][1]
    assert tier["remaining"] == 380
    assert tier["sold"] == 815  # holds do not count as sold


async def test_notes_are_truncated_and_unknown_ids_skipped(merchant_executor):
    result = await merchant_executor.execute(
        "present_event_pacing",
        {
            # The tier id and the unknown id both drop out while a real event remains.
            "event_ids": ["AT-EVT-105", "AT-TIX-101-PIT", "AT-EVT-999"],
            "notes": {"AT-EVT-105": "x" * 400},
        },
    )
    assert not result.is_error
    payload = next(event for event in result.events if event.type == "ui").data["payload"]
    assert [row["event_id"] for row in payload["events"]] == ["AT-EVT-105"]
    assert len(payload["events"][0]["note"]) == 200
    assert "suggestions" not in payload


async def test_all_unknown_ids_are_refused(merchant_executor):
    result = await merchant_executor.execute(
        "present_event_pacing", {"event_ids": ["AT-EVT-999", "AT-TIX-101-PIT"]}
    )
    assert result.is_error
    assert "pacing book" in result.result_text
    assert not result.events


async def test_invalid_payloads_are_soft_errors(merchant_executor):
    missing_ids = await merchant_executor.execute("present_event_pacing", {"notes": {}})
    assert missing_ids.is_error
    assert missing_ids.result_text.startswith(invalid_payload_prefix("present_event_pacing"))

    too_many = await merchant_executor.execute(
        "present_event_pacing", {"event_ids": [f"AT-EVT-10{i}" for i in range(5)]}
    )
    assert too_many.is_error


async def test_release_apply_flow_through_the_executor(
    merchant_executor, merchant, backend, merchant_state
):
    listed = await merchant_executor.execute("search_listings", {"query": "AT-TIX-105-BAL"})
    assert not listed.is_error
    # search_listings records provenance, so the staged write passes the gate.
    assert "AT-TIX-105-BAL" in merchant_state.seen_listings

    staged = await merchant_executor.execute(
        "stage_inventory_action",
        {"items": [{"listing_id": "AT-TIX-105-BAL", "action": "restock", "quantity": 10}]},
    )
    assert not staged.is_error
    change_id = next(
        event.data["change"]["change_id"]
        for event in staged.events
        if event.type == "change_update"
    )
    assert backend.engine.capacity("AT-TIX-105-BAL") == 260

    applied = await merchant_executor.execute("apply_change", {"change_id": change_id})
    assert not applied.is_error
    assert backend.engine.capacity("AT-TIX-105-BAL") == 270
    assert backend.engine.remaining("AT-TIX-105-BAL") == 260 - 97 + 10

    # The balcony's promoter hold was 20 before the 10-seat release.
    panel = await merchant_executor.execute("present_event_pacing", {"event_ids": ["AT-EVT-105"]})
    ui = next(event for event in panel.events if event.type == "ui")
    balcony = next(
        tier
        for tier in ui.data["payload"]["events"][0]["tiers"]
        if tier["product_id"] == "AT-TIX-105-BAL"
    )
    assert balcony["capacity"] == 270
    assert balcony["remaining"] == 173
    assert balcony["holds"] == {"promoter_hold": 10, "production_hold": 0, "comps": 6, "kills": 0}

    again = await merchant_executor.execute("apply_change", {"change_id": change_id})
    assert again.is_error
    assert "applied" in again.result_text
