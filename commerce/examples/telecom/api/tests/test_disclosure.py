# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The service-facts disclosure: core present_disclosure tool + MockTelecom's content."""

from shopping_agent import ShoppingAgentConfig
from shopping_agent.tools.registry import build_tools


def test_tool_registered_only_when_enabled():
    on = ShoppingAgentConfig(enable_disclosures=True)
    off = ShoppingAgentConfig()
    names_on = [t["name"] for t in build_tools(on, [])]
    names_off = [t["name"] for t in build_tools(off, [])]
    assert "present_disclosure" in names_on
    assert "present_disclosure" not in names_off
    assert [n for n in names_on if n != "present_disclosure"] == names_off


async def test_disclosure_rows_are_server_authored(executor):
    await executor.execute("search_products", {"query": "home internet fiber", "limit": 25})
    result = await executor.execute(
        "present_disclosure",
        {"product_id": "AM-NET-302"},
    )
    assert not result.is_error
    ui = next(e for e in result.events if e.type == "ui")
    assert ui.data["component"] == "disclosure"
    payload = ui.data["payload"]
    assert payload["title"] == "Home Fiber 1 Gig: service facts"
    labels = {row["label"]: row["value"] for row in payload["rows"]}
    assert labels["Monthly price"] == "$70"
    assert labels["Typical download speed"] == "940 Mbps"
    assert labels["Typical latency"] == "11 ms"
    assert "plan-pricing-disclosures" in payload["sources"]
    assert "suggestions" not in payload


async def test_disclosure_requires_provenance(executor):
    result = await executor.execute("present_disclosure", {"product_id": "AM-NET-302"})
    assert result.blocked == "provenance"
    assert not result.is_error
    assert "didn't come from this session" in result.result_text


async def test_no_disclosure_for_devices(executor):
    await executor.execute("search_products", {"query": "ACME Phone", "limit": 25})
    result = await executor.execute("present_disclosure", {"product_id": "AM-DEV-202"})
    assert result.is_error
    assert "No disclosure exists" in result.result_text


async def test_disclosure_closes_with_server_summed_all_in_estimate(executor):
    await executor.execute("search_products", {"query": "home internet fiber", "limit": 25})
    fiber = await executor.execute("present_disclosure", {"product_id": "AM-NET-302"})
    rows = next(e for e in fiber.events if e.type == "ui").data["payload"]["rows"]
    assert rows[-1]["label"] == "Estimated all-in"
    assert rows[-1]["value"] == "$71.45/mo"  # $70 plan + $1.45 surcharge
    assert "before location taxes" in rows[-1]["note"]

    await executor.execute("search_products", {"query": "unlimited plan", "limit": 25})
    plan = await executor.execute("present_disclosure", {"product_id": "AM-PLAN-103"})
    rows = next(e for e in plan.events if e.type == "ui").data["payload"]["rows"]
    assert rows[-1]["label"] == "Estimated all-in"
    assert rows[-1]["value"] == "$66.45/mo"  # $65 plan + $1.45 surcharge


async def test_plan_disclosure_states_network_management(executor):
    await executor.execute("search_products", {"query": "unlimited plan", "limit": 25})
    result = await executor.execute("present_disclosure", {"product_id": "AM-PLAN-103"})
    assert not result.is_error
    payload = next(e for e in result.events if e.type == "ui").data["payload"]
    labels = {row["label"]: row["value"] for row in payload["rows"]}
    assert "35 GB" in labels["Network management"]
    assert labels["High-speed data"] == "Unlimited"
