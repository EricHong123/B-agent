# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The merchant server's own surface: result mapping, per-connection provenance, approval config."""

from __future__ import annotations

from mcp import ClientSession
from mcp.shared.memory import create_connected_server_and_client_session
from merchant_mcp_server import build_server

from commerce_common.memory import InMemoryMemoryStore
from commerce_common.testing import result_text
from merchant_agent import MerchantAgentConfig, MerchantSessionState
from merchant_agent.gates import check_apply_change, check_listing_provenance

DECALS = "AR-2102"  # the retail fixture's wall decals, priced at 24.00
APPROVAL_ON = MerchantAgentConfig(brand_name="ACME")


def server(config: MerchantAgentConfig | None = None):
    return build_server(memory_store=InMemoryMemoryStore(), config=config)


async def _stage_decals_price(client: ClientSession, new_price: float) -> str:
    """Searches for provenance, stages a decals price move, and returns the change id."""
    await client.call_tool("search_listings", {"query": "ocean wall decals"})
    result = await client.call_tool(
        "stage_price_update", {"items": [{"listing_id": DECALS, "new_price": new_price}]}
    )
    text = result_text(result)
    assert not result.isError and "Staged only" in text
    return text.split('"change_id": "', 1)[1].split('"', 1)[0]


async def test_held_calls_are_plain_results_and_the_default_config_applies_on_the_platforms_say_so():
    async with create_connected_server_and_client_session(server()) as client:
        held = await client.call_tool(
            "stage_price_update", {"items": [{"listing_id": DECALS, "new_price": 26.0}]}
        )
        assert not held.isError
        assert (
            result_text(held)
            == check_listing_provenance(MerchantSessionState(), [DECALS]).result_text
        )
        failed = await client.call_tool("get_listing", {"listing_id": "AR-00000"})
        assert failed.isError
        # The structured filters argument reaches the executor as sent: the decals hold 3.
        kept = await client.call_tool(
            "search_listings", {"query": "ocean wall decals", "filters": {"max_stock": 3}}
        )
        dropped = await client.call_tool(
            "search_listings", {"query": "ocean wall decals", "filters": {"max_stock": 2}}
        )
        assert DECALS in result_text(kept) and DECALS not in result_text(dropped)

        change_id = await _stage_decals_price(client, 26.0)
        applied = await client.call_tool("apply_change", {"change_id": change_id})
        assert not applied.isError and f"Applied {change_id}" in result_text(applied)
        listing = await client.call_tool("get_listing", {"listing_id": DECALS})
        assert '"price": 26.0' in result_text(listing)

        again = await client.call_tool("apply_change", {"change_id": change_id})
        assert again.isError and "not staged" in result_text(again)


async def test_provenance_is_scoped_to_the_connection_and_the_queue_is_shared():
    shared = server()
    async with create_connected_server_and_client_session(shared) as first:
        change_id = await _stage_decals_price(first, 26.0)
    async with create_connected_server_and_client_session(shared) as second:
        staged = await second.call_tool(
            "stage_price_update", {"items": [{"listing_id": DECALS, "new_price": 25.0}]}
        )
        assert (
            result_text(staged)
            == check_listing_provenance(MerchantSessionState(), [DECALS]).result_text
        )
        applied = await second.call_tool("apply_change", {"change_id": change_id})
        expected = check_apply_change(MerchantSessionState(), APPROVAL_ON, change_id)
        assert result_text(applied) == expected.result_text
        # Listing the queue grants this connection provenance for the change.
        pending = await second.call_tool("get_pending_changes", {})
        assert change_id in result_text(pending)
        applied = await second.call_tool("apply_change", {"change_id": change_id})
        assert "Applied" in result_text(applied)


def test_a_config_that_leaves_approval_on_is_reported_at_startup(capsys):
    server(APPROVAL_ON)
    assert "require_host_approval is on" in capsys.readouterr().err


async def test_a_config_that_leaves_approval_on_holds_every_apply():
    async with create_connected_server_and_client_session(server(APPROVAL_ON)) as client:
        change_id = await _stage_decals_price(client, 26.0)
        result = await client.call_tool("apply_change", {"change_id": change_id})
        assert not result.isError and "has not been approved" in result_text(result)
        listing = await client.call_tool("get_listing", {"listing_id": DECALS})
        assert '"price": 24.0' in result_text(listing)
