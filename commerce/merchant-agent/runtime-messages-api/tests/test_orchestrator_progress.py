# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Delegate status lines interleaved into ``stream_turn`` between tool_call and tool_result."""

from __future__ import annotations

import asyncio
from typing import Any

from pydantic import BaseModel

from commerce_common.delegation import DelegateExtension
from commerce_common.testing import FakeClient, text_message, tool_calls_message, tool_use_message
from merchant_agent_runtime import MerchantAgent


class DelegateResult(BaseModel):
    ok: bool = True


def emitting_delegate(name: str, messages: list[str]) -> DelegateExtension:
    """A delegate that posts a fixed list of status lines then returns cleanly."""

    async def run(context, args):
        del args
        for message in messages:
            context.emit_status(message)
            await asyncio.sleep(0)  # yields so the drain can interleave
        return DelegateResult()

    return DelegateExtension(
        name=name,
        description="test delegate",
        input_schema={"type": "object"},
        result_model=DelegateResult,
        run=run,
    )


def make_agent(backend, skills, responses, delegates, **config_updates):
    client = FakeClient(responses)
    agent = MerchantAgent(
        backend=backend,
        skills=skills,
        client=client,
        extra_delegates=tuple(delegates),
    )
    if config_updates:
        agent.config = agent.config.model_copy(update=config_updates)
    return agent


async def collect(agent, text, session, state) -> list:
    events = []
    async for event in agent.stream_turn([{"role": "user", "content": text}], session, state):
        events.append(event)
    return events


def _first_index(events, predicate) -> int:
    return next(index for index, event in enumerate(events) if predicate(event))


async def test_delegate_progress_interleaves_between_call_and_result(
    backend, skills, session, state
):
    agent = make_agent(
        backend,
        skills,
        [
            tool_use_message("probe", {"question": "why"}),
            text_message("Here is what the analysis found."),
        ],
        delegates=[emitting_delegate("probe", ["reading the snapshot", "querying metrics"])],
    )
    events = await collect(agent, "Why did sales move?", session, state)

    call_at = _first_index(events, lambda e: e.type == "tool_call" and e.data["tool"] == "probe")
    result_at = _first_index(
        events, lambda e: e.type == "tool_result" and e.data["tool"] == "probe"
    )
    progress = [
        index
        for index, event in enumerate(events)
        if event.type == "progress" and event.data.get("tool") == "probe"
    ]
    assert progress
    assert call_at < min(progress)
    assert max(progress) < result_at
    # The executor adds the "starting" line.
    messages = [events[i].data["message"] for i in progress]
    assert messages == ["starting", "reading the snapshot", "querying metrics"]


async def test_plain_read_turn_has_no_progress_frames(backend, skills, session, state):
    agent = make_agent(
        backend,
        skills,
        [
            tool_use_message("get_business_snapshot", {}),
            text_message("Sales were up six percent."),
        ],
        delegates=[emitting_delegate("probe", ["unused"])],
    )
    events = await collect(agent, "How were sales last week?", session, state)
    types = [event.type for event in events]
    assert "progress" not in types
    assert types == ["tool_call", "tool_result", "text_delta", "turn_complete"]


async def test_client_disconnect_cancels_the_in_flight_delegate(backend, skills, session, state):
    cancelled: list[bool] = []

    async def run(context, args):
        del args
        context.emit_status("working")
        try:
            await asyncio.sleep(100)
        except asyncio.CancelledError:
            cancelled.append(True)
            raise
        return DelegateResult()

    delegate = DelegateExtension(
        name="probe",
        description="slow delegate",
        input_schema={"type": "object"},
        result_model=DelegateResult,
        run=run,
    )
    agent = make_agent(
        backend,
        skills,
        [tool_use_message("probe", {"question": "q"}), text_message("unreached")],
        delegates=[delegate],
    )

    before = {task for task in asyncio.all_tasks()}
    agen = agent.stream_turn([{"role": "user", "content": "q"}], session, state)
    async for event in agen:
        if event.type == "progress":
            break  # the host disconnects at the first status line
    await agen.aclose()

    assert cancelled == [True]
    leaked = [
        task
        for task in asyncio.all_tasks() - before
        if task is not asyncio.current_task() and not task.done()
    ]
    assert leaked == []


async def test_delegate_timeout_streams_frames_then_a_soft_error(backend, skills, session, state):
    async def run(context, args):
        del args
        context.emit_status("reading the snapshot")
        context.emit_status("querying metrics")
        try:
            async with asyncio.timeout(context.config.analysis_timeout_s):
                await asyncio.sleep(10)
        except TimeoutError:
            raise ValueError("hit its time budget before submitting") from None
        return DelegateResult()

    delegate = DelegateExtension(
        name="probe",
        description="timing-out delegate",
        input_schema={"type": "object"},
        result_model=DelegateResult,
        run=run,
    )
    agent = make_agent(
        backend,
        skills,
        [
            tool_use_message("probe", {"question": "q"}),
            text_message("I ran out of time — reusing what we have."),
        ],
        delegates=[delegate],
        analysis_timeout_s=0.05,
    )
    events = await collect(agent, "Why did sales move?", session, state)

    progress_messages = [event.data["message"] for event in events if event.type == "progress"]
    assert "reading the snapshot" in progress_messages
    assert "querying metrics" in progress_messages
    result = next(
        event for event in events if event.type == "tool_result" and event.data["tool"] == "probe"
    )
    assert result.data["is_error"] is True
    assert "time budget" in result.data["summary"]
    assert events[-1].type == "turn_complete"


async def test_delegate_cap_counts_across_one_gather(backend, skills, session, state):
    agent = make_agent(
        backend,
        skills,
        [
            tool_calls_message(("probe_a", {}), ("probe_b", {}), ("probe_a", {})),
            text_message("Both ran; the third was refused."),
        ],
        delegates=[
            emitting_delegate("probe_a", ["alpha"]),
            emitting_delegate("probe_b", ["beta"]),
        ],
        max_delegate_calls_per_turn=2,
    )
    events = await collect(agent, "Run both analyses", session, state)

    progress_messages = [event.data["message"] for event in events if event.type == "progress"]
    # The refused third call never started, so it posted no "starting" line.
    assert "alpha" in progress_messages
    assert "beta" in progress_messages
    assert progress_messages.count("starting") == 2

    results = {event.data["id"]: event for event in events if event.type == "tool_result"}
    assert results["tu-1"].data["is_error"] is False
    assert results["tu-2"].data["is_error"] is False
    assert results["tu-3"].data["is_error"] is True
    assert "reuse the analysis result above" in results["tu-3"].data["summary"]


async def test_no_progress_bleeds_into_a_later_iteration(backend, skills, session, state):
    agent = make_agent(
        backend,
        skills,
        [
            tool_use_message("probe", {"question": "q"}),
            tool_use_message("get_business_snapshot", {}),
            text_message("Done."),
        ],
        delegates=[emitting_delegate("probe", ["reading the snapshot"])],
    )
    events = await collect(agent, "Analyze then confirm the snapshot", session, state)

    snapshot_call_at = _first_index(
        events, lambda e: e.type == "tool_call" and e.data["tool"] == "get_business_snapshot"
    )
    last_progress_at = max(index for index, event in enumerate(events) if event.type == "progress")
    assert last_progress_at < snapshot_call_at


async def test_status_lines_never_enter_model_context(backend, skills, session, state):
    secret = "secret-status-line-4271"
    agent = make_agent(
        backend,
        skills,
        [
            tool_use_message("probe", {"question": "q"}),
            text_message("The analysis is done."),
        ],
        delegates=[emitting_delegate("probe", [secret])],
    )
    working = [{"role": "user", "content": "Why did sales move?"}]
    async for _ in agent.stream_turn(working, session, state):
        pass

    assert secret not in _flatten(working)


def _flatten(messages: list[dict[str, Any]]) -> str:
    parts: list[str] = []
    for message in messages:
        content = message.get("content")
        if isinstance(content, str):
            parts.append(content)
        elif isinstance(content, list):
            for block in content:
                if isinstance(block, dict):
                    parts.append(str(block))
    return "\n".join(parts)
