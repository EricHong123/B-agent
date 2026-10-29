# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The shopping orchestrator's ui_partial frames and its account prefetch."""

from __future__ import annotations

import pytest

from commerce_common.testing import FakeClient, text_message, tool_calls_message, tool_use_message
from shopping_agent import Product
from shopping_agent_runtime import ShoppingAgent


@pytest.fixture
def make_agent(backend, skills):
    def _make(responses, chunks: dict[int, list[str]] | None = None) -> ShoppingAgent:
        client = FakeClient(responses, chunks)
        return ShoppingAgent(backend=backend, skills=skills, client=client)

    return _make


async def collect_events(agent: ShoppingAgent, text: str, session, state) -> list:
    messages = [{"role": "user", "content": text}]
    return [event async for event in agent.stream_turn(messages, session, state)]


PRODUCTS = [
    Product(product_id="p-100", title="2-Person Backpacking Tent", price=149.0),
    Product(product_id="p-200", title="Two-Burner Camp Stove", price=64.5),
]

FINAL_INPUT = {
    "title": "A few options",
    "picks": [
        {"product_id": "p-100", "reason": "lightweight"},
        {"product_id": "p-200", "reason": "cheap"},
    ],
}

# Four deltas; only three change what the user would see. Chunk 3 finishes a reason
# string that chunk 2 already surfaced, so it must not re-emit.
CHUNKS = {
    0: [
        '{"title": "A few options", "picks": [{"product_id": "p-10',  # title, no resolvable item
        '0", "reason": "light',  # p-100 resolves: first item appears
        'weight"}',  # reason text grows: no structural change
        ', {"product_id": "p-200", "reason": "cheap"}]}',  # second item appears
    ]
}


async def test_ui_partial_emitted_on_structural_change_only(make_agent, session, state):
    state.remember_products(PRODUCTS)
    agent = make_agent(
        [tool_use_message("present_products", FINAL_INPUT), text_message("Here you go.")],
        chunks=CHUNKS,
    )
    events = await collect_events(agent, "show me camping picks", session, state)

    partials = [e for e in events if e.type == "ui_partial"]
    assert len(partials) == 3
    assert [len(p.data["payload"]["items"]) for p in partials] == [0, 1, 2]
    assert all(p.data["component"] == "products" for p in partials)
    # Every frame carries the stream_id the client uses to replace the previous frame.
    assert {p.data["stream_id"] for p in partials} == {"tu-1"}

    (ui,) = [e for e in events if e.type == "ui"]
    assert ui.data["stream_id"] == "tu-1"
    assert len(ui.data["payload"]["items"]) == 2


async def test_ui_partial_skips_unresolvable_ids(make_agent, session, state):
    # With no provenance nothing resolves, so only the title frame differs structurally.
    agent = make_agent(
        [tool_use_message("present_products", FINAL_INPUT), text_message("...")],
        chunks=CHUNKS,
    )
    events = await collect_events(agent, "show me camping picks", session, state)
    partials = [e for e in events if e.type == "ui_partial"]
    assert len(partials) == 1
    assert partials[0].data["payload"]["items"] == []


async def test_no_frame_goes_out_before_a_title_or_an_item(make_agent, session, state):
    state.remember_products(PRODUCTS)
    untitled = {0: [CHUNKS[0][0].replace('"title": "A few options", ', ""), *CHUNKS[0][1:]]}
    final = {key: value for key, value in FINAL_INPUT.items() if key != "title"}
    agent = make_agent(
        [tool_use_message("present_products", final), text_message("Here you go.")],
        chunks=untitled,
    )
    events = await collect_events(agent, "show me camping picks", session, state)
    partials = [e for e in events if e.type == "ui_partial"]
    assert [len(p.data["payload"]["items"]) for p in partials] == [1, 2]
    # A half-written reason never renders: the first item arrives without one.
    assert "reason" not in partials[0].data["payload"]["items"][0]


GUIDE_INPUT = {
    "title": "Pitching on rocky ground",
    "sections": [
        {"heading": "Pick the spot", "body": "Look for a flat patch clear of roots."},
        {"heading": "Anchor it", "body": "Use rock stacks where stakes will not go in."},
    ],
}

GUIDE_CHUNKS = {
    0: [
        '{"title": "Pitching on rocky ground", "sections": [{"heading": "Pick the sp',
        'ot", "body": "Look for a flat patch clear of roots."}, {"heading": "Anchor',
        ' it", "body": "Use rock stacks where stakes will not go in."}]}',
    ]
}


async def test_a_guide_streams_its_title_then_each_closed_section(make_agent, session, state):
    chips = ("present_suggestions", {"suggestions": ["Show freestanding tents"]})
    agent = make_agent(
        [tool_calls_message(("present_guide", GUIDE_INPUT), chips)], chunks=GUIDE_CHUNKS
    )
    events = await collect_events(agent, "how do I pitch a tent on rock", session, state)
    partials = [e for e in events if e.type == "ui_partial"]
    assert [len(p.data["payload"]["sections"]) for p in partials] == [0, 1, 2]
    assert partials[0].data["payload"]["title"] == "Pitching on rocky ground"
    assert all(p.data["component"] == "guide" for p in partials)
    guide, suggestions = [e for e in events if e.type == "ui"]
    assert "suggestions" not in guide.data["payload"]
    assert suggestions.data["payload"]["suggestions"] == ["Show freestanding tents"]
    # The chips went out in the card's round and closed the turn: one model call.
    assert len(agent.client.calls) == 1


# -- account prefetch ----------------------------------------------------------------


ACCOUNT = {
    "current_plan": "Essential 5GB",
    "contract_end": "2026-08-01",
    "upgrade_eligibility": {"eligible": True, "reason": "month 22 of 24"},
}


def _agent(backend, skills) -> ShoppingAgent:
    # _prefetch never calls the client, so any object will do.
    return ShoppingAgent(backend=backend, skills=skills, client=object())


async def test_prefetch_default_backend_has_no_account(backend, skills, session):
    agent = _agent(backend, skills)
    preferences, cart, facts, account = await agent._prefetch(session)
    assert preferences is not None
    assert cart is not None
    assert facts == []
    assert account is None


async def test_prefetch_account_override_flows_through(backend, skills, session, monkeypatch):
    async def fake_account(session):
        del session
        return dict(ACCOUNT)

    monkeypatch.setattr(backend, "get_account_context", fake_account)
    agent = _agent(backend, skills)
    _, _, _, account = await agent._prefetch(session)
    assert account == ACCOUNT


async def test_prefetch_raising_account_degrades_to_none(backend, skills, session, monkeypatch):
    async def broken_account(session):
        raise RuntimeError("billing system down")

    monkeypatch.setattr(backend, "get_account_context", broken_account)
    agent = _agent(backend, skills)
    preferences, cart, _, account = await agent._prefetch(session)
    assert account is None
    assert preferences is not None
    assert cart is not None


async def test_a_turn_closed_mid_round_leaves_no_unpaired_tool_use(make_agent, session, state):
    """The host may stop reading at any event; the stored conversation must still be one the
    next request can send."""
    agent = make_agent([tool_use_message("search_products", {"query": "tent"}), text_message("x")])
    messages = [{"role": "user", "content": "find me a tent"}]
    stream = agent.stream_turn(messages, session, state)
    async for event in stream:
        if event.type == "tool_call":
            break
    await stream.aclose()
    tool_uses = [
        block
        for message in messages
        if message["role"] == "assistant"
        for block in message["content"]
        if (block.get("type") if isinstance(block, dict) else block.type) == "tool_use"
    ]
    results = [
        block
        for message in messages
        if message["role"] == "user" and isinstance(message["content"], list)
        for block in message["content"]
        if block.get("type") == "tool_result"
    ]
    assert len(results) == len(tool_uses)
    assert messages[-1]["role"] == "user"


async def test_a_call_that_finished_before_the_close_keeps_its_real_result(
    make_agent, session, state
):
    """Closing at the tool_result event: the search ran, so its result is recorded rather than
    an invitation to call it again."""
    agent = make_agent([tool_use_message("search_products", {"query": "tent"}), text_message("x")])
    messages = [{"role": "user", "content": "find me a tent"}]
    stream = agent.stream_turn(messages, session, state)
    async for event in stream:
        if event.type == "tool_result":
            break
    await stream.aclose()
    result = messages[-1]["content"][0]
    assert result["type"] == "tool_result" and not result["is_error"]
    assert "interrupted" not in result["content"]
