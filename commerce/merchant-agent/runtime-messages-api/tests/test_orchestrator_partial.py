# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The merchant orchestrator's ui_partial frames: only what the session's provenance
resolves renders while a card streams."""

from __future__ import annotations

import json

import pytest

from commerce_common.testing import FakeClient, text_message, tool_calls_message
from merchant_agent import BusinessSnapshot, ChangeItem, ChangeKind, Listing
from merchant_agent_runtime import MerchantAgent


@pytest.fixture
def make_agent(backend, skills):
    def _make(responses, chunks: dict[int, list[str]] | None = None) -> MerchantAgent:
        return MerchantAgent(backend=backend, skills=skills, client=FakeClient(responses, chunks))

    return _make


async def collect_events(agent: MerchantAgent, text: str, session, state) -> list:
    messages = [{"role": "user", "content": text}]
    return [event async for event in agent.stream_turn(messages, session, state)]


def chunked(payload: dict, *cuts: str) -> list[str]:
    """``payload`` as JSON, split after each of ``cuts`` in order."""
    text, pieces = json.dumps(payload), []
    for cut in cuts:
        index = text.index(cut) + len(cut)
        pieces.append(text[:index])
        text = text[index:]
    return [*pieces, text]


DIGEST = {
    "title": "This morning",
    "items": [
        {"kind": "low_stock", "ref_id": "L-202", "headline": "2 left against 41 sold a month"},
        {"kind": "slow_mover", "ref_id": "L-203", "headline": "120 on hand, 4 sold a month"},
    ],
}
CHIPS = ("present_suggestions", {"suggestions": ["Restock L-202 by 40"]})


async def test_a_digest_streams_entry_by_entry_with_listing_joins(make_agent, session, state):
    state.remember_listings(
        [Listing(listing_id="L-202", title="Sprout Ceramic Planter", price=18.0)]
    )
    chunks = {0: chunked(DIGEST, '"headline": "2 left', 'a month"}')}
    agent = make_agent([tool_calls_message(("present_digest", DIGEST), CHIPS)], chunks)
    events = await collect_events(agent, "Give me the morning briefing", session, state)
    partials = [e for e in events if e.type == "ui_partial"]
    assert [len(p.data["payload"]["items"]) for p in partials] == [0, 1, 2]
    assert partials[0].data["payload"]["title"] == "This morning"
    assert partials[1].data["payload"]["items"][0]["listing"]["listing_id"] == "L-202"
    ui, chips = [e for e in events if e.type == "ui"]
    assert ui.data["stream_id"] == partials[0].data["stream_id"] == "tu-1"
    assert chips.data["component"] == "suggestions"
    assert len(agent.client.calls) == 1  # the chips in the same round closed the turn


async def test_a_digest_entry_with_a_kind_the_schema_lacks_waits_for_validation(
    make_agent, session, state
):
    payload = {"title": "Today", "items": [{"kind": "weather", "headline": "Rain later"}]}
    chunks = {0: chunked(payload, 'later"}')}
    agent = make_agent(
        [tool_calls_message(("present_digest", payload), CHIPS), text_message("Fixed.")], chunks
    )
    events = await collect_events(agent, "Brief me", session, state)
    partials = [e for e in events if e.type == "ui_partial"]
    assert [p.data["payload"]["items"] for p in partials] == [[]]
    (rejected,) = [
        e for e in events if e.type == "tool_result" and e.data["tool"] == "present_digest"
    ]
    assert rejected.data["is_error"]


async def test_a_metrics_card_waits_for_its_first_grounded_pick(make_agent, session, state):
    state.remember_snapshot(
        BusinessSnapshot(
            period="2026-06-19/2026-06-25",
            compare_to="2026-06-12/2026-06-18",
            sales=18432.0,
            orders=412,
            traffic=9120,
            conversion_rate=4.5,
            average_order_value=44.7,
        )
    )
    payload = {
        "title": "Last week",
        "picks": [{"metric": "footfall"}, {"metric": "sales", "note": "up on the prior week"}],
    }
    chunks = {0: chunked(payload, '"footfall"}', '"sales"')}
    agent = make_agent(
        [
            tool_calls_message(("present_metrics", payload), CHIPS),
            text_message("Footfall is not tracked."),
        ],
        chunks,
    )
    events = await collect_events(agent, "Recap last week for me", session, state)
    partials = [e for e in events if e.type == "ui_partial"]
    # The title alone is no frame and neither is the ungrounded pick; the grounded one is.
    assert [[m["metric"] for m in p.data["payload"]["metrics"]] for p in partials] == [["sales"]]
    first = partials[0].data["payload"]
    assert first["period"] == "2026-06-19/2026-06-25"
    assert "note" not in first["metrics"][0] or first["metrics"][0]["note"] is None
    # The dropped pick's note keeps the closing round.
    assert len(agent.client.calls) == 2


async def test_a_change_preview_renders_the_staged_record_before_the_headline(
    make_agent, backend, session, state
):
    change = backend.ledger.stage(
        kind=ChangeKind.INVENTORY_ACTION,
        summary="Restock L-202 by 40",
        items=[ChangeItem(target="L-202", field="stock", before=2, after=42)],
        actor=session.operator,
    )
    state.remember_change(change)
    payload = {"change_id": change.change_id, "headline": "Restock the planter by 40"}
    chunks = {0: chunked(payload, f'"{change.change_id}"', '"headline": "Restock')}
    agent = make_agent([tool_calls_message(("present_change_preview", payload), CHIPS)], chunks)
    events = await collect_events(agent, "Preview the restock", session, state)
    partials = [e for e in events if e.type == "ui_partial"]
    assert len(partials) == 1
    frame = partials[0].data["payload"]
    assert frame["change"]["change_id"] == change.change_id and "headline" not in frame
    ui, _chips = [e for e in events if e.type == "ui"]
    assert ui.data["payload"]["headline"] == "Restock the planter by 40"
