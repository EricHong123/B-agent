# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The per-system switches on both configs: what each removes from the tool list, the
static prompt, and the grounding rules, on the Messages API, Agent SDK, and MCP paths."""

from __future__ import annotations

import merchant_mcp_server
import pytest
import storefront_mcp_server
from mcp.shared.memory import create_connected_server_and_client_session

from commerce_common.grounding import first_forced_tool
from commerce_common.memory import InMemoryMemoryStore
from commerce_common.skills import SkillRegistry
from merchant_agent import MerchantAgentConfig, MerchantSessionState
from merchant_agent.grounding import GROUNDING_RULES as MERCHANT_RULES
from merchant_agent.grounding import change_requested
from merchant_agent.prompt import build_static_system as merchant_static_system
from merchant_agent.tools.registry import build_tools as merchant_tools
from merchant_agent_sdk import MerchantToolset
from merchant_agent_sdk import tool_names as merchant_sdk_tool_names
from shopping_agent import ShoppingAgentConfig, ShoppingSessionState
from shopping_agent.grounding import GROUNDING_RULES as SHOPPING_RULES
from shopping_agent.prompt import build_static_system as shopping_static_system
from shopping_agent.tools.registry import build_tools as shopping_tools
from shopping_agent_sdk import ShoppingToolset
from shopping_agent_sdk import tool_names as shopping_sdk_tool_names

SHOPPING_SWITCHES = {
    "enable_cart": {"get_cart", "add_to_cart", "update_cart_item", "remove_from_cart", "checkout"},
    "enable_orders": {"get_orders", "get_order_status", "present_order_status"},
    "enable_policies": {"search_policies"},
    "enable_fulfillment": {"get_fulfillment_options"},
}
MERCHANT_SWITCHES = {
    "enable_listing_edits": {"stage_listing_update"},
    "enable_inventory": {
        "get_inventory_alerts",
        "get_order_issues",
        "get_return_reasons",
        "stage_inventory_action",
    },
    "enable_pricing": {"get_pricing_context", "stage_price_update", "stage_promotion"},
    "enable_campaigns": {"get_campaign_performance", "stage_campaign"},
}
CHANGE_QUEUE = {"get_pending_changes", "apply_change", "discard_change", "present_change_preview"}


def names(tools: list[dict]) -> list[str]:
    return [tool["name"] for tool in tools]


def shopping(**switches) -> ShoppingAgentConfig:
    return ShoppingAgentConfig(brand_name="ACME", **switches)


def merchant(**switches) -> MerchantAgentConfig:
    return MerchantAgentConfig(brand_name="ACME", **switches)


# -- tools[] ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "make,build,switch,removed",
    [(shopping, shopping_tools, *item) for item in SHOPPING_SWITCHES.items()]
    + [(merchant, merchant_tools, *item) for item in MERCHANT_SWITCHES.items()],
)
def test_a_switch_removes_its_tools_and_nothing_else(make, build, switch, removed):
    everything = names(build(make(), []))
    remaining = names(build(make(**{switch: False}), []))
    assert set(everything) - set(remaining) == removed
    assert remaining == [name for name in everything if name not in removed]  # order kept


def test_merchant_change_queue_goes_only_when_every_write_is_off():
    everything = set(names(merchant_tools(merchant(), [])))
    three_off = merchant(enable_listing_edits=False, enable_inventory=False, enable_pricing=False)
    assert three_off.stages_changes
    assert set(names(merchant_tools(three_off, []))) >= CHANGE_QUEUE
    all_off = merchant(**{switch: False for switch in MERCHANT_SWITCHES})
    assert not all_off.stages_changes
    remaining = set(names(merchant_tools(all_off, [])))
    assert not remaining & CHANGE_QUEUE
    assert everything - remaining == CHANGE_QUEUE.union(*MERCHANT_SWITCHES.values())
    assert {"get_business_snapshot", "query_metrics", "search_listings", "get_listing"} <= remaining


async def test_the_executor_refuses_a_switched_off_tool_on_any_path():
    """The tool list is what the model sees; the executor is what every path calls."""
    backend = storefront_mcp_server._default_backend()
    executor = ShoppingToolset(backend=backend, config=shopping(enable_cart=False)).executor
    refused = await executor.execute("add_to_cart", {"product_id": "AR-1602"})
    assert refused.is_error and refused.result_text == (
        "add_to_cart is not something this store offers; say so plainly and do not suggest it."
    )
    # dispatch is the prefetch path (grounding); it refuses the same way.
    assert (
        "not something this store offers" in (await executor.dispatch("get_cart", {})).result_text
    )
    assert not (await executor.execute("search_products", {"query": "tent"})).is_error


# -- static prompt ---------------------------------------------------------------------


def test_shopping_prompt_follows_the_switches():
    skills = SkillRegistry([])
    full = shopping_static_system(shopping(), skills)
    for phrase in ("checkout stages", "A cart tool", "search_policies or get_fulfillment"):
        assert phrase in full

    no_cart = shopping_static_system(shopping(enable_cart=False), skills)
    for phrase in ("cart", "checkout", "add, remove, buy"):
        assert phrase not in no_cart.split("# Trust and data")[0].lower().replace(
            "customer-care", ""
        ), phrase
    assert "Confirm a save after the tool call succeeds" in no_cart

    no_policies = shopping_static_system(shopping(enable_policies=False), skills)
    assert "search_policies" not in no_policies and "store's terms (return" not in no_policies
    assert "Stay within shopping, planning, and orders for ACME" in no_policies

    no_fulfillment = shopping_static_system(shopping(enable_fulfillment=False), skills)
    assert "get_fulfillment_options" not in no_fulfillment
    assert "only from a search_policies result" in no_fulfillment

    # A missing system is named as such, not as an outage.
    assert "This store has no" not in full
    no_orders = shopping_static_system(shopping(enable_orders=False), skills)
    assert "get_orders" not in no_orders
    assert "Stay within shopping, planning, and store terms for ACME" in no_orders
    assert "This store has no order history or tracking here." in no_orders
    assert "not an outage" in no_orders
    both = shopping_static_system(shopping(enable_cart=False, enable_policies=False), skills)
    assert "no a cart or checkout, no a lookup of the store's terms here" in both

    bare = shopping(**{switch: False for switch in SHOPPING_SWITCHES})
    assert "Stay within shopping and planning for ACME" in shopping_static_system(bare, skills)


def test_merchant_prompt_drops_the_write_contract_only_when_every_write_is_off():
    skills = SkillRegistry([])
    full = merchant_static_system(merchant(), skills)
    assert "This portal does not do" not in full
    for switch in MERCHANT_SWITCHES:
        # One switch off keeps the write contract and adds only the "does not do" sentence.
        one_off = merchant_static_system(merchant(**{switch: False}), skills)
        assert one_off.replace(one_off[one_off.index("\n- This portal does not do") :], "") in full
    no_pricing = merchant_static_system(merchant(enable_pricing=False), skills)
    assert "This portal does not do price changes or promotions." in no_pricing
    bare = merchant_static_system(merchant(**{s: False for s in MERCHANT_SWITCHES}), skills)
    for phrase in ("stage", "staging", "apply_change", "preview", "pproval", "guardrail"):
        assert phrase in full
        assert phrase not in bare, phrase
    for phrase in ("Ground every number", "present_metrics", "no turn ends without something"):
        assert phrase in bare


# -- grounding -------------------------------------------------------------------------


def test_shopping_grounding_rules_skip_a_switched_off_system():
    def forced(text: str, **switches: bool) -> str | None:
        return first_forced_tool(SHOPPING_RULES, shopping(**switches), text, ShoppingSessionState())

    assert forced("What is your return policy?") == "search_policies"
    assert forced("What is your return policy?", enable_policies=False) is None
    assert forced("Where is my order?") == "get_orders"
    assert forced("Where is my order?", enable_orders=False) is None


def test_merchant_followthrough_and_queue_rules_need_a_write_tool():
    ask = "Drop the tent price by 5% and apply it"
    assert change_requested(merchant(), ask)
    assert first_forced_tool(MERCHANT_RULES, merchant(), ask, MerchantSessionState()) is not None
    bare = merchant(**{switch: False for switch in MERCHANT_SWITCHES})
    assert not change_requested(bare, ask)
    assert first_forced_tool(MERCHANT_RULES, bare, ask, MerchantSessionState()) is None


# -- Agent SDK and MCP paths -----------------------------------------------------------


def test_sdk_toolsets_register_what_the_registry_carries():
    no_cart = shopping(enable_cart=False)
    assert not SHOPPING_SWITCHES["enable_cart"] & set(shopping_sdk_tool_names(no_cart))
    assert "search_products" in shopping_sdk_tool_names(no_cart)
    no_pricing = merchant(enable_pricing=False)
    assert not MERCHANT_SWITCHES["enable_pricing"] & set(merchant_sdk_tool_names(no_pricing))
    assert "stage_listing_update" in merchant_sdk_tool_names(no_pricing)
    # The toolsets construct without touching the switched-off handlers.
    ShoppingToolset(backend=storefront_mcp_server._default_backend(), config=no_cart)
    MerchantToolset(backend=merchant_mcp_server._default_backend(no_pricing), config=no_pricing)


async def test_mcp_servers_leave_switched_off_tools_unregistered():
    store = storefront_mcp_server.build_server(
        memory_store=InMemoryMemoryStore(), config=shopping(enable_cart=False, enable_orders=False)
    )
    async with create_connected_server_and_client_session(store) as client:
        listed = {tool.name for tool in (await client.list_tools()).tools}
    assert "search_products" in listed
    assert not listed & (SHOPPING_SWITCHES["enable_cart"] | SHOPPING_SWITCHES["enable_orders"])

    office = merchant_mcp_server.build_server(
        memory_store=InMemoryMemoryStore(),
        config=merchant(
            **{switch: False for switch in MERCHANT_SWITCHES}, require_host_approval=False
        ),
    )
    async with create_connected_server_and_client_session(office) as client:
        listed = {tool.name for tool in (await client.list_tools()).tools}
    assert {"get_business_snapshot", "search_listings"} <= listed
    assert not listed & CHANGE_QUEUE.union(*MERCHANT_SWITCHES.values())
