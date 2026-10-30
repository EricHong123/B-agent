# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

from commerce_common.presentation import invalid_payload_prefix


async def test_enrichment_fills_the_panel_from_backend_data(merchant_executor):
    result = await merchant_executor.execute(
        "present_plan_mix",
        {
            "plan_ids": ["AM-PLAN-101", "AM-NET-301"],
            "notes": {"AM-PLAN-101": "Churn has climbed for six straight weeks."},
        },
    )
    assert not result.is_error
    ui = next(event for event in result.events if event.type == "ui")
    assert ui.data["component"] == "plan_mix"
    payload = ui.data["payload"]
    assert payload["total_subscribers"] == 49620
    assert payload["grain"] == "week"
    assert "suggestions" not in payload
    assert [row["plan_id"] for row in payload["plans"]] == ["AM-PLAN-101", "AM-NET-301"]

    essential = payload["plans"][0]
    assert essential["title"] == "Essential 5GB"
    assert essential["price"] == 35.0
    assert essential["subscribers"] == 12400
    assert essential["share_pct"] == round(12400 / 49620 * 100, 1)
    assert essential["churn_rate_pct"] == 2.1
    assert essential["arpu"] == 38.4
    assert essential["wholesale_cost_per_line_usd"] == 13.33
    assert essential["margin_per_line_usd"] == round(38.4 - 13.33, 2)
    assert essential["note"] == "Churn has climbed for six straight weeks."
    assert len(essential["weeks"]) == 13

    fiber = payload["plans"][1]
    assert fiber["kind"] == "home-internet"
    assert fiber["subscribers"] == 2900
    assert fiber["margin_per_line_usd"] == round(50.0 - 27.0, 2)
    assert "note" not in fiber


async def test_notes_are_truncated_and_unknown_ids_skipped(merchant_executor):
    result = await merchant_executor.execute(
        "present_plan_mix",
        {
            # The device id and the unknown id both drop out while a real plan remains.
            "plan_ids": ["AM-PLAN-102", "AM-DEV-201", "AM-PLAN-999"],
            "notes": {"AM-PLAN-102": "x" * 400},
        },
    )
    assert not result.is_error
    payload = next(event for event in result.events if event.type == "ui").data["payload"]
    assert [row["plan_id"] for row in payload["plans"]] == ["AM-PLAN-102"]
    assert len(payload["plans"][0]["note"]) == 200
    assert "suggestions" not in payload


async def test_all_unknown_ids_are_refused(merchant_executor):
    result = await merchant_executor.execute(
        "present_plan_mix", {"plan_ids": ["AM-PLAN-999", "AM-DEV-201"]}
    )
    assert result.is_error
    assert "subscriber data" in result.result_text
    assert not result.events


async def test_invalid_payloads_are_soft_errors(merchant_executor):
    missing_ids = await merchant_executor.execute("present_plan_mix", {"notes": {}})
    assert missing_ids.is_error
    assert missing_ids.result_text.startswith(invalid_payload_prefix("present_plan_mix"))

    too_many = await merchant_executor.execute(
        "present_plan_mix", {"plan_ids": [f"AM-PLAN-10{i}" for i in range(9)]}
    )
    assert too_many.is_error


async def test_promotion_apply_flow_through_the_executor(
    merchant_executor, merchant, merchant_state
):
    listed = await merchant_executor.execute("search_listings", {"query": "AM-PLAN-102"})
    assert not listed.is_error
    assert "AM-PLAN-102" in merchant_state.seen_listings
    # get_listing records provenance too, so the fiber tier passes the staging gate.
    fiber = await merchant_executor.execute("get_listing", {"listing_id": "AM-NET-301"})
    assert not fiber.is_error

    staged = await merchant_executor.execute(
        "stage_promotion",
        {
            "name": "August bundle offer",
            "listing_ids": ["AM-PLAN-102", "AM-NET-301"],
            "discount_pct": 15,
            "starts": "2026-08-03",
            "ends": "2026-08-30",
        },
    )
    assert not staged.is_error
    change_id = next(
        event.data["change"]["change_id"]
        for event in staged.events
        if event.type == "change_update"
    )

    applied = await merchant_executor.execute("apply_change", {"change_id": change_id})
    assert not applied.is_error
    assert merchant.promo_windows["AM-PLAN-102"][0]["change_id"] == change_id
    assert merchant.promo_windows["AM-NET-301"][0]["change_id"] == change_id

    # An applied promotion records a window; the standing prices stay at 50.0.
    panel = await merchant_executor.execute(
        "present_plan_mix", {"plan_ids": ["AM-PLAN-102", "AM-NET-301"]}
    )
    ui = next(event for event in panel.events if event.type == "ui")
    prices = {row["plan_id"]: row["price"] for row in ui.data["payload"]["plans"]}
    assert prices == {"AM-PLAN-102": 50.0, "AM-NET-301": 50.0}

    again = await merchant_executor.execute("apply_change", {"change_id": change_id})
    assert again.is_error
    assert "applied" in again.result_text
