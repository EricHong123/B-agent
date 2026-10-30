# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

from commerce_common.presentation import invalid_payload_prefix


async def test_invalid_payload_is_a_soft_error(executor):
    result = await executor.execute("present_plan_comparison", {"plan_ids": ["just-one"]})
    assert result.is_error
    assert result.result_text.startswith(invalid_payload_prefix("present_plan_comparison"))


async def test_matrix_rows_are_built_server_side(executor):
    await executor.execute("search_products", {"query": "phone plan", "limit": 25})
    result = await executor.execute(
        "present_plan_comparison",
        {
            "title": "Plans that fit 15GB months",
            "plan_ids": ["AM-PLAN-102", "AM-PLAN-103", "AM-PLAN-104"],
            "dimension_keys": ["data_allowance_gb", "hotspot_gb", "price_guarantee"],
            "annotations": [
                {"plan_id": "AM-PLAN-103", "best_for": "heavier data months"},
                {"plan_id": "AM-PLAN-102", "best_for": "predictable months"},
            ],
            "recommended_plan_id": "AM-PLAN-103",
        },
    )
    assert not result.is_error
    ui = next(e for e in result.events if e.type == "ui")
    assert ui.data["component"] == "plan_matrix"
    payload = ui.data["payload"]

    # The price row is always first.
    price_row = payload["rows"][0]
    assert price_row["key"] == "price"
    assert price_row["values"] == ["$50/mo", "$65/mo", "$85/mo"]

    data_row = next(r for r in payload["rows"] if r["key"] == "data_allowance_gb")
    assert data_row["values"] == ["15 GB", "Unlimited", "Unlimited"]
    assert data_row["label"] == "High-speed data"

    assert [p["product_id"] for p in payload["plans"]] == [
        "AM-PLAN-102",
        "AM-PLAN-103",
        "AM-PLAN-104",
    ]
    assert payload["recommended_plan_id"] == "AM-PLAN-103"
    assert {a["plan_id"] for a in payload["annotations"]} == {"AM-PLAN-102", "AM-PLAN-103"}


async def test_unseen_plan_ids_are_dropped_and_recommendation_filtered(executor):
    await executor.execute("search_products", {"query": "phone plan", "limit": 25})
    result = await executor.execute(
        "present_plan_comparison",
        {
            "plan_ids": ["AM-PLAN-102", "AM-PLAN-103", "AM-PLAN-999"],
            "recommended_plan_id": "AM-PLAN-999",
            "annotations": [{"plan_id": "AM-PLAN-999", "best_for": "nobody — it does not exist"}],
        },
    )
    assert not result.is_error
    payload = next(e for e in result.events if e.type == "ui").data["payload"]
    assert [p["product_id"] for p in payload["plans"]] == ["AM-PLAN-102", "AM-PLAN-103"]
    assert "recommended_plan_id" not in payload
    assert payload["annotations"] == []


async def test_human_phrased_dimensions_are_aliased_and_empty_rows_dropped(executor):
    await executor.execute("search_products", {"query": "phone plan", "limit": 25})
    result = await executor.execute(
        "present_plan_comparison",
        {
            "plan_ids": ["AM-PLAN-102", "AM-PLAN-103"],
            "dimension_keys": ["hotspot", "roaming", "talk and text", "streaming"],
        },
    )
    assert not result.is_error
    payload = next(e for e in result.events if e.type == "ui").data["payload"]
    keys = [row["key"] for row in payload["rows"]]
    assert "hotspot_gb" in keys
    assert "intl_roaming" in keys
    assert "talk_and_text" not in keys  # no plan carries a value for it
    hotspot = next(r for r in payload["rows"] if r["key"] == "hotspot_gb")
    assert hotspot["values"] == ["10 GB", "25 GB"]


async def test_current_plan_threaded_from_account_context(executor):
    await executor.execute("search_products", {"query": "phone plan", "limit": 25})
    result = await executor.execute(
        "present_plan_comparison",
        {"plan_ids": ["AM-PLAN-102", "AM-PLAN-103"]},
    )
    assert not result.is_error
    payload = next(e for e in result.events if e.type == "ui").data["payload"]
    assert payload["current_plan"] == {
        "product_id": "AM-PLAN-101",
        "name": "Essential 5GB",
        "price_per_month": 35.0,
        "data_allowance_gb": "5",
    }
    usage = payload["account_usage"]
    assert usage["avg_gb_per_month_last_3"] == 14.2
    assert len(usage["cycles_gb_last_3"]) == 3
    assert usage["top_up_spend_usd_last_3_months"] == 40.0
    assert all(
        p["attributes"]["price_qualifier"].startswith("+ taxes & fees") for p in payload["plans"]
    )
    assert all(row["key"] != "price_qualifier" for row in payload["rows"])


async def test_current_plan_absent_for_prospects(make_executor, other_session):
    executor = make_executor(other_session)
    await executor.execute("search_products", {"query": "phone plan", "limit": 25})
    result = await executor.execute(
        "present_plan_comparison",
        {"plan_ids": ["AM-PLAN-102", "AM-PLAN-103"]},
    )
    assert not result.is_error
    payload = next(e for e in result.events if e.type == "ui").data["payload"]
    assert "current_plan" not in payload
    assert "account_usage" not in payload


async def test_matrix_without_provenance_is_a_soft_error(executor):
    result = await executor.execute(
        "present_plan_comparison",
        {"plan_ids": ["AM-PLAN-102", "AM-PLAN-103"]},
    )
    assert result.is_error
    assert "Search for plans first" in result.result_text
