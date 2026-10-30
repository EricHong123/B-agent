# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The storefront server's own surface: the result mapping and per-connection provenance."""

from __future__ import annotations

from mcp.shared.memory import create_connected_server_and_client_session
from storefront_mcp_server import build_server

from commerce_common.memory import InMemoryMemoryStore
from commerce_common.testing import result_text
from shopping_agent.fencing import STOREFRONT_FENCE
from shopping_agent.gates import provenance_error

YOGA_MAT = "AR-1301"  # returned by a "yoga mat" search of the retail fixture
HEADPHONES = "AR-1105"  # returned by a "headphones" search
ESPRESSO_MACHINE = "AR-1002"  # a "coffee maker" match priced well over 100


def server():
    return build_server(memory_store=InMemoryMemoryStore())


async def test_held_calls_are_plain_results_failures_set_is_error_and_reads_are_fenced():
    async with create_connected_server_and_client_session(server()) as client:
        held = await client.call_tool("add_to_cart", {"product_id": YOGA_MAT, "quantity": 1})
        assert not held.isError and result_text(held) == provenance_error(YOGA_MAT)
        failed = await client.call_tool("get_product_details", {"product_id": "AR-00000"})
        assert failed.isError
        search = await client.call_tool("search_products", {"query": "yoga mat"})
        assert STOREFRONT_FENCE.open in result_text(search) and YOGA_MAT in result_text(search)
        # The structured filters argument reaches the executor as sent.
        unfiltered = await client.call_tool("search_products", {"query": "coffee maker"})
        assert ESPRESSO_MACHINE in result_text(unfiltered)
        filtered = await client.call_tool(
            "search_products", {"query": "coffee maker", "filters": {"max_price": 100}}
        )
        assert not filtered.isError and ESPRESSO_MACHINE not in result_text(filtered)
        added = await client.call_tool("add_to_cart", {"product_id": YOGA_MAT, "quantity": 1})
        assert not added.isError and f"Added {YOGA_MAT}" in result_text(added)


async def test_provenance_is_scoped_to_the_connection_but_the_cart_is_shared():
    shared = server()
    async with create_connected_server_and_client_session(shared) as first:
        await first.call_tool("search_products", {"query": "yoga mat"})
        await first.call_tool("search_products", {"query": "headphones"})
        await first.call_tool("add_to_cart", {"product_id": YOGA_MAT, "quantity": 1})
    async with create_connected_server_and_client_session(shared) as second:
        # The first connection saw the headphones; this one did not.
        unseen = await second.call_tool("add_to_cart", {"product_id": HEADPHONES, "quantity": 1})
        assert result_text(unseen) == provenance_error(HEADPHONES)
        # The line the first connection added grants cart-membership edits.
        updated = await second.call_tool(
            "update_cart_item", {"product_id": YOGA_MAT, "quantity": 3}
        )
        assert "Updated quantity" in result_text(updated)
        removed = await second.call_tool("remove_from_cart", {"product_id": YOGA_MAT})
        assert "Removed" in result_text(removed)
