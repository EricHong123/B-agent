# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The SDK path's own surface: registration, the toolset, the prefetch texts, and run_turn."""

from __future__ import annotations

import pytest
from claude_agent_sdk import (
    AssistantMessage,
    ResultMessage,
    TextBlock,
    ToolUseBlock,
)

import merchant_agent_sdk.agent as agent_module
from commerce_common.agent_sdk import CLOSE_HOOK_EVENT, close_on_presentation_hook
from commerce_common.execution import LOAD_SKILL
from commerce_common.testing import result_text
from merchant_agent import MerchantAgentConfig, MerchantSessionState
from merchant_agent.analysis import (
    ANALYSIS_READ_TOOLS,
    ANALYSIS_TOOL,
    build_analysis_tool_definition,
)
from merchant_agent.fencing import MERCHANT_FENCE
from merchant_agent.gates import (
    STAGED_AND_SHOWN_NOTE,
    STAGING_FOLLOWTHROUGH_REMINDER,
    check_listing_provenance,
)
from merchant_agent_sdk import (
    ANALYSIS_AGENT_ADAPTER,
    ANALYSIS_AGENT_NAME,
    build_merchant_sdk_tools,
    build_system_prompt,
    default_config,
    ground_message,
    load_skill_registry,
    make_options,
    mcp_tool_name,
    run_turn,
    tool_contracts,
)

HEADPHONES_ID = "AR-1105"  # returned by a "headphones" search of the retail fixture

CHANGE_TEXT = "Take the noise cancelling headphones from $249 down to $239 for the push."

ONE_SKILL = "---\nname: supplier-orders\ndescription: Reorder requests.\n---\n\nBody.\n"


def _assistant(*blocks) -> AssistantMessage:
    return AssistantMessage(content=list(blocks), model="test-model")


def _result(cost: float = 0.01) -> ResultMessage:
    return ResultMessage(
        subtype="success",
        duration_ms=1,
        duration_api_ms=1,
        is_error=False,
        num_turns=1,
        session_id="s-1",
        total_cost_usd=cost,
    )


class ScriptedClient:
    """A ClaudeSDKClient stand-in that plays back one scripted response stream per query."""

    def __init__(self, scripts: list) -> None:
        self.queries: list[str] = []
        self._scripts = list(scripts)

    async def query(self, text: str) -> None:
        self.queries.append(text)

    async def receive_response(self):
        assert self._scripts, "more queries than scripted responses"
        script = self._scripts.pop(0)
        if isinstance(script, Exception):
            raise script
        for message in script:
            yield message


# -- registration ----------------------------------------------------------------------


def test_registered_tools_are_the_registry_minus_skill_loading_and_analysis():
    config = default_config().model_copy(update={"enable_analysis": True})
    _, toolset = make_options(config=config)
    registered = [t.name for t in build_merchant_sdk_tools(toolset)]
    excluded = {LOAD_SKILL, ANALYSIS_TOOL}
    assert registered == [name for name in tool_contracts(config) if name not in excluded]
    assert ANALYSIS_TOOL in tool_contracts(config)


def test_skills_dir_selects_the_indexed_and_materialized_skills(tmp_path, monkeypatch):
    monkeypatch.setattr(agent_module, "RUNTIME_ROOT", tmp_path / "runtime")
    skills_dir = tmp_path / "skills"
    (skills_dir / "supplier-orders").mkdir(parents=True)
    (skills_dir / "supplier-orders" / "SKILL.md").write_text(ONE_SKILL, encoding="utf-8")
    options, _ = make_options(skills_dir=skills_dir)
    assert options.skills == ["supplier-orders"]
    assert "`supplier-orders`" in options.system_prompt
    materialized = tmp_path / "runtime" / ".claude" / "skills"
    assert [p.name for p in materialized.iterdir()] == ["supplier-orders"]
    default, _ = make_options()
    assert default.skills == load_skill_registry().names
    assert default.system_prompt == build_system_prompt(default_config(), load_skill_registry())


def test_default_surface_has_no_subagents_and_closes_on_the_chips_round():
    options, _ = make_options()
    assert options.agents is None
    assert options.tools == ["Skill"]
    assert ANALYSIS_AGENT_ADAPTER not in options.system_prompt
    assert list(options.hooks) == [CLOSE_HOOK_EVENT]


def test_analysis_maps_onto_a_read_only_subagent():
    config = MerchantAgentConfig(brand_name="ACME", enable_analysis=True)
    options, _ = make_options(config=config)
    assert options.tools == ["Skill", "Task"]
    assert set(options.agents) == {ANALYSIS_AGENT_NAME}
    agent = options.agents[ANALYSIS_AGENT_NAME]
    assert agent.description == build_analysis_tool_definition()["description"]
    assert agent.tools == [mcp_tool_name(name) for name in ANALYSIS_READ_TOOLS]
    assert not any(
        fragment in tool
        for tool in agent.tools
        for fragment in ("stage", "apply", "discard", "present", "memory")
    )
    assert ANALYSIS_AGENT_ADAPTER in options.system_prompt
    assert "analysis engine" in agent.prompt
    assert "merchant_data" in agent.prompt
    assert "submit_analysis" in agent.prompt


# -- the toolset ------------------------------------------------------------------------


async def test_held_calls_are_plain_results_and_failures_are_flagged(handlers):
    held = await handlers["stage_inventory_action"].handler(
        {"items": [{"listing_id": HEADPHONES_ID, "action": "restock", "quantity": 24}]}
    )
    assert "is_error" not in held
    assert (
        result_text(held)
        == check_listing_provenance(MerchantSessionState(), [HEADPHONES_ID]).result_text
    )
    failed = await handlers["get_listing"].handler({"listing_id": "AR-00000"})
    assert failed["is_error"] is True


async def test_search_stage_apply_and_preview_round_trip_through_the_registered_tools(
    handlers, toolset
):
    search = await handlers["search_listings"].handler({"query": "headphones"})
    assert MERCHANT_FENCE.open in result_text(search) and HEADPHONES_ID in result_text(search)
    staged = await handlers["stage_inventory_action"].handler(
        {"items": [{"listing_id": HEADPHONES_ID, "action": "restock", "quantity": 24}]}
    )
    assert STAGED_AND_SHOWN_NOTE in result_text(staged)
    change_id = next(iter(toolset.state.seen_changes))
    # The stage call rendered its own preview; present_change_preview shows it again.
    (shown,) = toolset.drain_ui_events()
    assert shown["component"] == "change_preview" and shown["payload"]["change_id"] == change_id
    await handlers["present_change_preview"].handler({"change_id": change_id})
    assert [event["component"] for event in toolset.drain_ui_events()] == ["change_preview"]
    applied = await handlers["apply_change"].handler({"change_id": change_id})
    assert toolset.session.operator in result_text(applied)
    assert toolset.state.seen_changes[change_id].applied_by == toolset.session.operator
    assert toolset.drain_ui_events() == []


async def test_host_approval_goes_through_the_toolsets_approval_api(handlers, toolset):
    toolset.config.require_host_approval = True
    await handlers["search_listings"].handler({"query": "headphones"})
    await handlers["stage_inventory_action"].handler(
        {"items": [{"listing_id": HEADPHONES_ID, "action": "restock", "quantity": 24}]}
    )
    change_id = next(iter(toolset.state.seen_changes))
    assert [c.change_id for c in toolset.pending_host_approvals()] == [change_id]

    refused = await handlers["apply_change"].handler({"change_id": change_id})
    assert "is_error" not in refused
    assert toolset.config.approval_surface in result_text(refused)

    # A cleared mark approves nothing: the change is pending again and apply is held.
    toolset.host_approve(change_id)
    toolset.host_clear(change_id)
    assert [c.change_id for c in toolset.pending_host_approvals()] == [change_id]
    held = await handlers["apply_change"].handler({"change_id": change_id})
    assert toolset.config.approval_surface in result_text(held)

    toolset.host_approve(change_id)
    applied = await handlers["apply_change"].handler({"change_id": change_id})
    assert "is_error" not in applied
    assert toolset.pending_host_approvals() == []


# -- ground_message: the two rules' prefetch texts ---------------------------------------


async def test_a_performance_question_is_grounded_with_the_fenced_snapshot(toolset):
    text = "How did sales do this week?"
    grounded = await ground_message(text, toolset)
    assert grounded.startswith(text) and MERCHANT_FENCE.open in grounded and '"sales"' in grounded
    assert toolset.state.latest_snapshot is not None


async def test_an_apply_request_is_grounded_with_the_queue(toolset):
    text = "There's a price change we settled on yesterday — go ahead and put it through."
    grounded = await ground_message(text, toolset)
    assert grounded.startswith(text) and "Pending approval queue for this turn" in grounded


# -- run_turn --------------------------------------------------------------------------


async def test_change_turn_without_staging_sends_the_reminder_once(toolset):
    client = ScriptedClient(
        [
            [_assistant(TextBlock("Want me to set that up?")), _result(0.01)],
            [_assistant(TextBlock("Here is the follow-through.")), _result(0.02)],
        ]
    )
    result = await run_turn(client, CHANGE_TEXT, toolset=toolset)
    assert client.queries == [CHANGE_TEXT, STAGING_FOLLOWTHROUGH_REMINDER]
    assert "Want me to set that up?" in result.text
    assert "Here is the follow-through." in result.text
    assert result.cost_usd == pytest.approx(0.03)


async def test_reminder_suppressed_when_a_stage_tool_ran(toolset):
    client = ScriptedClient(
        [
            [
                _assistant(
                    ToolUseBlock(
                        id="t1",
                        name=mcp_tool_name("stage_price_update"),
                        input={"items": [{"listing_id": HEADPHONES_ID, "new_price": 239.0}]},
                    ),
                    TextBlock("Staged — review the preview to apply it."),
                ),
                _result(),
            ]
        ]
    )
    result = await run_turn(client, CHANGE_TEXT, toolset=toolset)
    assert client.queries == [CHANGE_TEXT]
    assert result.tool_calls == [mcp_tool_name("stage_price_update")]


async def test_a_change_turn_is_reminded_before_the_hook_may_close_it_on_its_chips(
    handlers, toolset
):
    (matcher,) = close_on_presentation_hook(toolset, enabled=True)[CLOSE_HOOK_EVENT]
    (hook,) = matcher.hooks

    class ChipsClient(ScriptedClient):
        """The round the CLI would run on each pass: text, present_suggestions, the hook."""

        verdicts: list[dict] = []

        async def query(self, text: str) -> None:
            await ScriptedClient.query(self, text)
            await handlers["present_suggestions"].handler(
                {"suggestions": ["Stage $239 on the headphones"]}
            )
            self.verdicts.append(await hook({"tool_calls": [{}]}, None, None))

    client = ChipsClient(
        [
            [_assistant(TextBlock("The floor is $210; $239 clears it.")), _result()],
            [_assistant(TextBlock("Say the word and I stage $239.")), _result()],
        ]
    )
    result = await run_turn(client, CHANGE_TEXT, toolset=toolset)
    # Unstaged, the first chips round stays open and the reminder follows; the reminded
    # pass closes on its chips.
    assert client.queries == [CHANGE_TEXT, STAGING_FOLLOWTHROUGH_REMINDER]
    assert [verdict.get("continue_") for verdict in client.verdicts] == [None, False]
    assert [event["component"] for event in result.ui] == ["suggestions"]


async def test_the_closing_hook_judges_the_round_the_way_the_messages_api_loop_does(
    handlers, toolset
):
    (matcher,) = close_on_presentation_hook(toolset, enabled=True)[CLOSE_HOOK_EVENT]
    (hook,) = matcher.hooks
    chips = {"suggestions": ["Check margin room"]}

    async def round_of(*calls: tuple[str, dict], extra: int = 0) -> dict:
        toolset.begin_turn()
        for name, args in calls:
            await handlers[name].handler(args)
        return await hook({"tool_calls": [{}] * (len(calls) + extra)}, "batch", None)

    stop = {"continue_": False, "stopReason": "The reply closed on its chips."}
    assert await round_of(("present_suggestions", chips)) == stop
    assert toolset.turn_closed
    # A read in the round, a card refused in it, or a call that bypassed the toolset
    # (the Skill tool) leaves the turn to the model.
    assert await round_of(("search_listings", {"query": "h"}), ("present_suggestions", chips)) == {}
    assert not toolset.turn_closed
    refused = ("present_change_preview", {"change_id": "chg-404"})
    assert await round_of(refused, ("present_suggestions", chips)) == {}
    assert await round_of(("present_suggestions", chips), extra=1) == {}
    # Switched off, the deployment registers no hook.
    assert close_on_presentation_hook(toolset, enabled=False) is None


def test_the_ui_drain_keeps_only_the_last_set_of_chips(toolset):
    toolset.ui_events = [
        {"component": "suggestions", "payload": {"suggestions": ["a"]}},
        {"component": "metrics", "payload": {}},
        {"component": "suggestions", "payload": {"suggestions": ["b"]}},
    ]
    assert [e["component"] for e in toolset.drain_ui_events()] == ["metrics", "suggestions"]
    assert toolset.drain_ui_events() == []


async def test_reminder_suppressed_with_the_gate_off(toolset):
    toolset.config.staging_followthrough_gate = False
    client = ScriptedClient([[_assistant(TextBlock("Want me to set that up?")), _result()]])
    await run_turn(client, CHANGE_TEXT, toolset=toolset)
    assert client.queries == [CHANGE_TEXT]


async def test_non_change_turn_is_never_reminded(toolset):
    client = ScriptedClient([[_assistant(TextBlock("All quiet this morning.")), _result()]])
    await run_turn(client, "Anything urgent in the queue this morning?", toolset=toolset)
    assert client.queries == ["Anything urgent in the queue this morning?"]


async def test_detector_reads_the_pre_injection_operator_text(toolset):
    # The text trips both gates: the snapshot is appended to the outgoing query, and the
    # change cue is read from the operator's original text.
    text = "How did sales do this week — should we drop the tote price by 10%?"
    client = ScriptedClient(
        [
            [_assistant(TextBlock("Sales held steady; a cut is defensible.")), _result()],
            [_assistant(TextBlock("Follow-through after the reminder.")), _result()],
        ]
    )
    await run_turn(client, text, toolset=toolset)
    assert client.queries[0].startswith(text)
    assert MERCHANT_FENCE.open in client.queries[0]
    assert client.queries[1] == STAGING_FOLLOWTHROUGH_REMINDER


async def test_reminded_turn_merges_tool_calls_and_ui(handlers, toolset):
    # On the reminder query the client stages through the real handler, which renders
    # the change's preview card.
    await handlers["search_listings"].handler({"query": "headphones"})

    class RemindedPassClient(ScriptedClient):
        async def query(self, text: str) -> None:
            await ScriptedClient.query(self, text)
            if text != STAGING_FOLLOWTHROUGH_REMINDER:
                return
            await handlers["stage_price_update"].handler(
                {"items": [{"listing_id": HEADPHONES_ID, "new_price": 239.0}]}
            )

    client = RemindedPassClient(
        [
            [
                _assistant(
                    ToolUseBlock(
                        id="t1",
                        name=mcp_tool_name("get_pricing_context"),
                        input={"listing_id": HEADPHONES_ID},
                    ),
                    TextBlock("Here is the pricing context."),
                ),
                _result(0.01),
            ],
            [
                _assistant(
                    ToolUseBlock(
                        id="t2",
                        name=mcp_tool_name("stage_price_update"),
                        input={"items": [{"listing_id": HEADPHONES_ID, "new_price": 239.0}]},
                    ),
                    TextBlock("Staged — review the preview to apply it."),
                ),
                _result(0.02),
            ],
        ]
    )
    result = await run_turn(client, CHANGE_TEXT, toolset=toolset)
    assert client.queries == [CHANGE_TEXT, STAGING_FOLLOWTHROUGH_REMINDER]
    assert result.tool_calls == [
        mcp_tool_name("get_pricing_context"),
        mcp_tool_name("stage_price_update"),
    ]
    assert [event["component"] for event in result.ui] == ["change_preview"]
    assert toolset.drain_ui_events() == []


async def test_reminder_failure_degrades_to_the_unreminded_result(toolset):
    client = ScriptedClient(
        [
            [_assistant(TextBlock("Want me to set that up?")), _result(0.01)],
            RuntimeError("stream dropped"),
        ]
    )
    result = await run_turn(client, CHANGE_TEXT, toolset=toolset)
    assert client.queries == [CHANGE_TEXT, STAGING_FOLLOWTHROUGH_REMINDER]
    assert result.text == "Want me to set that up?"
    assert result.cost_usd == pytest.approx(0.01)
    assert not result.is_error
