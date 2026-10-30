# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""ground_message wires the shopping rules to the toolset's executor and state."""

from __future__ import annotations

from shopping_agent.fencing import STOREFRONT_FENCE
from shopping_agent_sdk import ground_message

HEADPHONES_ID = "AR-1105"
PAST_ORDER_ID = "AR-78214"
PAST_ORDER_ITEM_ID = "AR-1104"


async def test_an_id_reference_is_grounded_and_unlocks_the_cart_gate(handlers, toolset):
    text = f"Add {HEADPHONES_ID} to my cart."
    grounded = await ground_message(text, toolset)
    assert grounded.startswith(text) and STOREFRONT_FENCE.open in grounded
    assert HEADPHONES_ID in toolset.state.seen_products
    result = await handlers["add_to_cart"].handler({"product_id": HEADPHONES_ID, "quantity": 1})
    assert "is_error" not in result


async def test_an_order_ask_is_grounded_with_the_orders_and_their_items(toolset):
    grounded = await ground_message("Where's my order?", toolset)
    assert PAST_ORDER_ID in grounded
    assert PAST_ORDER_ITEM_ID in toolset.state.seen_products


async def test_a_policy_question_passes_through_because_its_rule_has_no_prefetch(toolset):
    text = "How do returns work?"
    assert await ground_message(text, toolset) == text
