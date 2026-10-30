# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The orchestrator's staging follow-through gate, driven against a scripted model client."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from commerce_common.testing import (
    FakeClient,
    text_block,
    text_message,
    tool_calls_message,
    tool_use_message,
)
from merchant_agent.gates import STAGING_FOLLOWTHROUGH_REMINDER
from merchant_agent_runtime import MerchantAgent


async def run_turn(agent: MerchantAgent, text: str, session, state) -> list:
    messages = [{"role": "user", "content": text}]
    events = []
    async for event in agent.stream_turn(messages, session, state):
        events.append(event)
    return events


async def run_turn_with_history(agent: MerchantAgent, text: str, session, state) -> list:
    """Returns the messages list as the orchestrator left it after the turn."""
    messages = [{"role": "user", "content": text}]
    async for _ in agent.stream_turn(messages, session, state):
        pass
    return messages


def reminder_messages(messages: list) -> list:
    return [
        message
        for message in messages
        if message.get("role") == "user"
        and isinstance(message.get("content"), list)
        and any(
            block.get("type") == "text" and block.get("text") == STAGING_FOLLOWTHROUGH_REMINDER
            for block in message["content"]
        )
    ]


@pytest.fixture
def make_agent(backend, skills):
    def _make(responses: list[SimpleNamespace], **config_updates: Any) -> MerchantAgent:
        client = FakeClient(responses)
        agent = MerchantAgent(backend=backend, skills=skills, client=client)
        if config_updates:
            agent.config = agent.config.model_copy(update=config_updates)
        return agent

    return _make


async def test_a_stage_call_shows_the_preview_and_the_sentence_with_the_chips_ends_the_turn(
    make_agent, session, state
):
    """The staging turn as the prompt has it: read, stage (the change_update and the card
    reach the host in that round), then one sentence beside the chips, which closes the
    turn."""
    restock = {"items": [{"listing_id": "L-202", "action": "restock", "quantity": 24}]}
    chips = ("present_suggestions", {"suggestions": ["Make it 40 instead", "What else is low?"]})
    closing = tool_calls_message(chips)
    closing.content.insert(0, text_block("Staged; approve it on the preview card."))
    agent = make_agent(
        [
            tool_use_message("search_listings", {"query": "planter"}),
            tool_calls_message(("stage_inventory_action", restock, "tu-stage")),
            closing,
        ]
    )
    events = await run_turn(agent, "Restock the planter by 24", session, state)
    assert len(agent.client.calls) == 3  # no closing round after the sentence and chips
    kinds = [(e.type, e.data.get("component")) for e in events if e.type in ("ui", "change_update")]
    assert kinds == [("change_update", None), ("ui", "change_preview"), ("ui", "suggestions")]
    preview = next(e for e in events if e.data.get("component") == "change_preview")
    change_id = next(iter(state.seen_changes))
    assert preview.data["stream_id"] == "tu-stage"
    assert preview.data["payload"]["change_id"] == change_id
    assert state.seen_changes[change_id].status.value == "staged"
    assert not state.approved_change_ids
    assert events[-1].type == "turn_complete" and events[-1].data["stop_reason"] == "end_turn"
    # With the flag off the stage shows nothing, and a stage call beside the chips leaves
    # the closing line to the model.
    agent = make_agent(
        [
            tool_use_message("search_listings", {"query": "planter"}),
            tool_calls_message(("stage_inventory_action", restock), chips),
            text_message("Staged; review it on the preview card."),
        ],
        stage_shows_preview=False,
    )
    events = await run_turn(agent, "Restock the planter by 24", session, state)
    assert len(agent.client.calls) == 3
    assert [e.data.get("component") for e in events if e.type == "ui"] == ["suggestions"]


# -- the staging follow-through gate --------------------------------------------------

CHANGE_TEXT = "Take the ocean storage bins from $29 down to $26 for the campaign window."


async def test_change_turn_without_staging_gets_one_reminder(make_agent, session, state):
    agent = make_agent(
        [
            text_message("Happy to — want me to set that up?"),
            text_message("Here is where that lands against the pricing floor."),
        ]
    )
    messages = await run_turn_with_history(agent, CHANGE_TEXT, session, state)

    calls = agent.client.calls
    assert len(calls) == 2
    assert calls[1]["tool_choice"] == {"type": "auto"}
    reminders = reminder_messages(messages)
    assert len(reminders) == 1
    # messages holds the operator turn, the first answer, the reminder, and the reminded answer.
    assert messages[2] is reminders[0]
    assert messages[-1]["role"] == "assistant"


async def test_change_turn_that_stages_is_not_reminded(make_agent, session, state):
    agent = make_agent(
        [
            tool_use_message("search_listings", {"query": "ocean storage"}),
            tool_use_message(
                "stage_price_update",
                {"items": [{"listing_id": "L-201", "new_price": 31.0}]},
            ),
            text_message("Staged the price move — review the preview to apply it."),
        ]
    )
    messages = await run_turn_with_history(agent, CHANGE_TEXT, session, state)
    assert len(agent.client.calls) == 3
    assert reminder_messages(messages) == []


async def test_blocked_stage_attempt_suppresses_the_reminder(make_agent, session, state):
    agent = make_agent(
        [
            tool_use_message(
                "stage_price_update",
                {"items": [{"listing_id": "L-999", "new_price": 26.0}]},
            ),
            text_message("I can't stage that yet — let me look the listing up first."),
        ]
    )
    messages = await run_turn_with_history(agent, CHANGE_TEXT, session, state)
    assert len(agent.client.calls) == 2
    assert reminder_messages(messages) == []
    assert state.seen_changes == {}


async def test_followthrough_gate_disabled_by_config(make_agent, session, state):
    agent = make_agent(
        [text_message("Happy to — want me to set that up?")],
        staging_followthrough_gate=False,
    )
    messages = await run_turn_with_history(agent, CHANGE_TEXT, session, state)
    assert len(agent.client.calls) == 1
    assert reminder_messages(messages) == []


async def test_reminder_fires_at_most_once(make_agent, session, state):
    agent = make_agent(
        [
            text_message("Happy to — want me to set that up?"),
            text_message("Sticking with my answer: the request needs a decision first."),
        ]
    )
    messages = await run_turn_with_history(agent, CHANGE_TEXT, session, state)
    assert len(agent.client.calls) == 2
    assert len(reminder_messages(messages)) == 1


async def test_force_text_backstop_holds_on_the_reminded_pass(make_agent, session, state):
    # With max_tool_iterations=1 the reminded pass is also the force_text pass.
    agent = make_agent(
        [text_message("First answer."), text_message("Reminded answer.")],
        max_tool_iterations=1,
    )
    await run_turn_with_history(agent, CHANGE_TEXT, session, state)
    calls = agent.client.calls
    assert len(calls) == 2
    assert calls[0]["tool_choice"] == {"type": "auto"}
    assert calls[1]["tool_choice"] == {"type": "none"}


async def test_a_change_turn_that_reaches_its_chips_unstaged_is_reminded_before_it_closes(
    make_agent, session, state
):
    chips = ("present_suggestions", {"suggestions": ["Stage $26 on L-201"]})
    agent = make_agent(
        [
            tool_use_message("search_listings", {"query": "ocean storage"}),
            tool_calls_message(chips),
            tool_use_message(
                "stage_price_update", {"items": [{"listing_id": "L-201", "new_price": 26.0}]}
            ),
            tool_calls_message(chips),
        ]
    )
    assert agent.config.close_on_presentation
    messages = [{"role": "user", "content": CHANGE_TEXT}]
    events = [event async for event in agent.stream_turn(messages, session, state)]
    assert len(agent.client.calls) == 4
    (reminded,) = reminder_messages(messages)
    # The reminder follows the chips round's results, and the reminded pass may close.
    assert messages.index(reminded) == 5 and messages[4]["content"][0]["type"] == "tool_result"
    assert events[-1].type == "turn_complete" and events[-1].data["stop_reason"] == "end_turn"
    assert [e.data["component"] for e in events if e.type == "ui"].count("suggestions") == 2


async def test_non_change_turn_is_never_reminded(make_agent, session, state):
    agent = make_agent([text_message("Sales were up six percent on the prior week.")])
    messages = await run_turn_with_history(
        agent, "Thanks for the recap yesterday — anything urgent this morning?", session, state
    )
    assert len(agent.client.calls) == 1
    assert reminder_messages(messages) == []
