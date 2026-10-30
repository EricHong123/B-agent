# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

from datetime import datetime

from commerce_common.types import MemoryCategory, MemoryFact
from merchant_agent.fencing import MERCHANT_FENCE
from merchant_agent.prompt import build_dynamic_context, build_static_system
from merchant_agent.tools.registry import build_tools


def test_static_system_mentions_store_skills_and_fence(config, skills):
    text = build_static_system(config, skills)
    assert "ACME" in text
    assert "performance-insights" in text
    assert "merchant_data" in text  # the fence notice is present
    assert "apply_change" in text  # the approval rule is stated
    assert "the merchant assistant" in text  # no invented persona


def test_web_search_is_config_gated_and_appends_last(config, skills):
    base = build_tools(config, skills.names)
    assert all(t.get("name") != "web_search" for t in base)
    enabled = config.model_copy(update={"enable_web_search": True})
    with_search = build_tools(enabled, skills.names)
    assert with_search[-1]["name"] == "web_search"
    assert with_search[:-1] == base


def test_stage_tools_advertise_the_per_change_item_cap(config, skills):
    tools = {t["name"]: t for t in build_tools(config, skills.names)}
    for name in ("stage_price_update", "stage_inventory_action"):
        items_schema = tools[name]["input_schema"]["properties"]["items"]
        assert items_schema["maxItems"] == config.max_items_per_change


def test_dynamic_context_is_fenced_and_contains_store_data():
    block = build_dynamic_context(
        merchant_context={
            "store": "ACME",
            "current_period": "2026-06-19/2026-06-25",
            "alerts": {"low_stock": 2, "order_issues": 1},
            "operator": "demo-operator",
        },
        memory_facts=[
            MemoryFact(
                key="margin_floor",
                value="keep margins above 30%",
                category=MemoryCategory.CONSTRAINT,
            ),
        ],
        now=datetime(2026, 6, 26, 9, 41),
    )
    assert block.startswith("# Merchant context")
    assert MERCHANT_FENCE.open in block and MERCHANT_FENCE.close in block
    assert "<storefront_data>" not in block
    assert "current_period" in block
    assert "margin_floor" in block
    assert "2026-06-26T09:00" in block
    without_clock = build_dynamic_context(merchant_context=None, memory_facts=[], now=None)
    assert "local_time" not in without_clock


def test_dynamic_context_oversize_store_context_collapses_to_note():
    block = build_dynamic_context(
        merchant_context={"history": "x" * 5000},
        memory_facts=[],
        merchant_context_max_chars=2000,
    )
    assert "merchant context omitted (too large)" in block
    assert "xxxx" not in block


def test_dynamic_context_without_store_context_has_no_store_key():
    block = build_dynamic_context(merchant_context=None, memory_facts=[])
    assert '"store"' not in block
    assert '"saved_memory"' in block
