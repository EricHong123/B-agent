# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The SDK path's own surface: gated registration, the result mapping, and the UI buffer."""

from __future__ import annotations

import shopping_agent_sdk.agent as agent_module
from commerce_common.agent_sdk import CLOSE_HOOK_EVENT
from commerce_common.testing import result_text
from shopping_agent.fencing import STOREFRONT_FENCE
from shopping_agent.gates import provenance_error
from shopping_agent_sdk import (
    allowed_tool_names,
    build_shopping_sdk_tools,
    build_system_prompt,
    default_config,
    load_skill_registry,
    make_options,
    tool_names,
)

HEADPHONES_ID = "AR-1105"  # returned by a "headphones" search of the retail fixture

ONE_SKILL = "---\nname: gift-registry\ndescription: Registry requests.\n---\n\nBody.\n"


def test_skills_dir_selects_the_indexed_and_materialized_skills(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_module, "RUNTIME_ROOT", tmp_path / "runtime")
    skills_dir = tmp_path / "skills"
    (skills_dir / "gift-registry").mkdir(parents=True)
    (skills_dir / "gift-registry" / "SKILL.md").write_text(ONE_SKILL, encoding="utf-8")
    options, _ = make_options(skills_dir=skills_dir)
    assert options.skills == ["gift-registry"]
    assert "`gift-registry`" in options.system_prompt
    materialized = tmp_path / "runtime" / ".claude" / "skills"
    assert [p.name for p in materialized.iterdir()] == ["gift-registry"]
    default, _ = make_options()
    assert default.skills == load_skill_registry().names
    assert default.system_prompt == build_system_prompt(default_config(), load_skill_registry())


def test_config_gated_tools_register_and_allowlist_in_lockstep():
    """Under "dontAsk", a registered tool missing from allowed_tools is refused on every call."""
    config = default_config().model_copy(update={"enable_disclosures": True})
    options, toolset = make_options(config=config)
    registered = [t.name for t in build_shopping_sdk_tools(toolset)]
    assert "present_disclosure" in registered
    assert registered == tool_names(config)
    assert options.allowed_tools == [f"mcp__storefront__{name}" for name in registered]
    assert options.allowed_tools == allowed_tool_names(config)
    # The turn ends on the round that carries the chips, as on the Messages API path;
    # the hook's verdicts are commerce_common's and tested with the merchant SDK runtime.
    assert list(options.hooks) == [CLOSE_HOOK_EVENT]


async def test_held_calls_are_plain_results_and_failures_are_flagged(handlers):
    held = await handlers["add_to_cart"].handler({"product_id": HEADPHONES_ID, "quantity": 1})
    assert "is_error" not in held
    assert result_text(held) == provenance_error(HEADPHONES_ID)
    failed = await handlers["get_product_details"].handler({"product_id": "AR-00000"})
    assert failed["is_error"] is True


async def test_search_add_and_present_round_trip_through_the_registered_tools(handlers, toolset):
    search = await handlers["search_products"].handler({"query": "headphones"})
    assert STOREFRONT_FENCE.open in result_text(search) and HEADPHONES_ID in result_text(search)
    added = await handlers["add_to_cart"].handler({"product_id": HEADPHONES_ID, "quantity": 2})
    assert f"Added {HEADPHONES_ID} x2" in result_text(added)
    presented = await handlers["present_products"].handler(
        {"picks": [{"product_id": HEADPHONES_ID}]}
    )
    assert "is_error" not in presented
    events = toolset.drain_ui_events()
    assert [event["component"] for event in events] == ["products"]
    assert events[0]["payload"]["items"][0]["product"]["product_id"] == HEADPHONES_ID
    assert toolset.drain_ui_events() == []
