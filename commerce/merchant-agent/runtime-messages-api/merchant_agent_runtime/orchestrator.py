# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The merchant agent's turn loop on the Messages API: one model call per iteration,
tools dispatched eagerly as their blocks close while delegate progress lines stream,
presentation calls rendered while they stream, a rolling cache breakpoint through the
conversation, a round of clean presentation calls that includes the chips ending the
turn (``close_on_presentation``), one reminder when a change request would end without
a staging attempt, and memory extracted once the reply is out.

    agent = MerchantAgent(backend=my_backend, skills_dir=Path("merchant-agent/skills"))
    async for event in agent.stream_turn(messages, session, state):
        ...
    await agent.update_memory(messages, session)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any, cast

from anthropic import AsyncAnthropic

from commerce_common.delegation import DelegateExtension
from commerce_common.grounding import first_forced_tool
from commerce_common.memory import MemoryRuntime, MemoryStore, MemoryWriteFilter
from commerce_common.presentation import (
    PresentationComponent,
    PresentationExtension,
    partial_ui_tool_names,
)
from commerce_common.prompt_assembly import (
    build_request_messages,
    build_system_blocks,
    with_eager_input,
    with_tool_cache_control,
)
from commerce_common.skills import SkillRegistry
from commerce_common.streaming import AgentEvent, ToolOutcome
from commerce_common.turn import (
    EagerDispatcher,
    StreamedRound,
    accumulate_usage,
    assistant_message,
    close_open_tool_uses,
    compact_history,
    elapsed_ms,
    fetched,
    latest_exchange,
    latest_user_text,
    log_model_call,
    outcome_events,
    prompt_tokens,
    round_closes_turn,
    salvage_round,
    tool_result_block,
    transcript_text,
    usage_totals,
)
from commerce_common.types import MemoryFact
from merchant_agent.backend import MerchantBackend
from merchant_agent.config import MerchantAgentConfig
from merchant_agent.enrichment import PRESENTATION_COMPONENTS
from merchant_agent.executor import MerchantToolExecutor, build_memory
from merchant_agent.gates import STAGING_FOLLOWTHROUGH_REMINDER, turn_attempted_staging
from merchant_agent.grounding import GROUNDING_RULES, change_requested
from merchant_agent.prompt import build_dynamic_context, build_static_system
from merchant_agent.tools.registry import build_tools
from merchant_agent.types import MerchantSessionContext, MerchantSessionState

from .analysis import build_analysis_delegate

logger = logging.getLogger(__name__)

HOST_TEXTS = frozenset({STAGING_FOLLOWTHROUGH_REMINDER})


class MerchantAgent:
    """One deployment of the agent. ``memory`` is its :class:`MemoryRuntime`; a portal
    with its own memory routes reads and writes through ``memory.store``.
    ``executor_class`` is the seam for a deployment's own :class:`MerchantToolExecutor`
    subclass (its own ``domain_error`` mapping or result wording)."""

    def __init__(
        self,
        *,
        backend: MerchantBackend,
        skills: SkillRegistry | None = None,
        skills_dir: Path | None = None,
        config: MerchantAgentConfig | None = None,
        memory_store: MemoryStore | None = None,
        memory_write_filter: MemoryWriteFilter | None = None,
        client: AsyncAnthropic | None = None,
        extra_presentation_tools: Sequence[PresentationExtension] = (),
        extra_delegates: Sequence[DelegateExtension] = (),
        executor_class: type[MerchantToolExecutor] = MerchantToolExecutor,
    ) -> None:
        if skills is None:
            skills = SkillRegistry.from_dir(skills_dir) if skills_dir else SkillRegistry([])
        self.config = config or MerchantAgentConfig()
        self.executor_class = executor_class
        self.backend = backend
        self.skills = skills
        self.memory: MemoryRuntime = build_memory(self.config, memory_store, memory_write_filter)
        self.client = client or AsyncAnthropic(timeout=self.config.request_timeout_s)
        self.extra_presentation_tools = tuple(extra_presentation_tools)
        self.extra_delegates = tuple(extra_delegates)
        built_in = (
            [build_analysis_delegate(self.client, self.backend, self.config)]
            if self.config.enable_analysis
            else []
        )
        self.delegates: tuple[DelegateExtension, ...] = (*built_in, *self.extra_delegates)
        self._specs: dict[str, PresentationComponent] = {
            **PRESENTATION_COMPONENTS,
            **{ext.name: ext for ext in self.extra_presentation_tools},
        }
        self._partial_ui_tools = partial_ui_tool_names(
            PRESENTATION_COMPONENTS, self.extra_presentation_tools
        )
        # Built once: the same bytes on every request of this deployment. The registry
        # adds the built-in delegate's contract from the config, so only extras pass here;
        # the presentation tools that render while they stream ask the API for their
        # input as it is generated.
        self._static_system = build_static_system(self.config, self.skills)
        tools = build_tools(
            self.config, self.skills.names, self.extra_presentation_tools, self.extra_delegates
        )
        self._tools = with_tool_cache_control(with_eager_input(tools, self._partial_ui_tools))

    async def stream_turn(
        self,
        messages: list[dict[str, Any]],
        session: MerchantSessionContext,
        state: MerchantSessionState | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Run one turn. ``messages`` ends with the operator's message and is extended
        in place with the turn's assistant messages, tool results, and any reminder, so
        the host stores it as is; ``state`` carries the session's provenance and comes
        back on every turn."""
        state = state if state is not None else MerchantSessionState()
        turn_started = time.monotonic()
        usage = usage_totals()
        merchant_context, memory_facts = await asyncio.gather(
            fetched(self.backend.get_merchant_context(session)),
            fetched(self.memory.tier_one(session.merchant_id)),
        )
        # The second system block, built once per turn: the same bytes across the turn's
        # rounds, and across turns until the state in it moves (prompt_assembly).
        context = build_dynamic_context(
            merchant_context=merchant_context,
            memory_facts=list(memory_facts or []),
            now=session.local_now(),
            reply_language=session.reply_language,
            merchant_context_max_chars=self.config.max_context_chars,
        )
        system = build_system_blocks(self._static_system, context)
        # Delegates post progress lines while their executions are in flight; the loop
        # below drains them into the stream between the tool_call and tool_result events.
        progress: asyncio.Queue[AgentEvent | None] = asyncio.Queue()
        executor = self.executor_class(
            backend=self.backend,
            config=self.config,
            skills=self.skills,
            session=session,
            state=state,
            memory=self.memory,
            extensions=self.extra_presentation_tools,
            delegates=self.delegates,
            progress=progress.put_nowait,
            usage=usage,
        )
        user_text = latest_user_text(messages, HOST_TEXTS)
        forced_tool = first_forced_tool(GROUNDING_RULES, self.config, user_text, state)
        remind = change_requested(self.config, user_text)
        stop_reason: str | None = None
        last_prompt = 0

        def reminder() -> dict[str, Any]:
            # Appended as a persisted message, so the next turn's cache prefix extends
            # this one; the model keeps the final call on staging.
            return {
                "role": "user",
                "content": [{"type": "text", "text": STAGING_FOLLOWTHROUGH_REMINDER}],
            }

        # A turn the host abandons at a yield, or a round that raises, must not leave the
        # stored conversation on a tool_use with no result: the next request would be
        # rejected. The finally pairs any open call with its result, or an error.
        settled: dict[str, ToolOutcome] = {}
        try:
            for round_index in range(self.config.max_tool_iterations + 1):
                force_text = round_index == self.config.max_tool_iterations
                if force_text:
                    tool_choice: dict[str, str] = {"type": "none"}
                elif round_index == 0 and forced_tool:
                    tool_choice = {"type": "tool", "name": forced_tool}
                else:
                    tool_choice = {"type": "auto"}

                # The marker is skipped on non-auto rounds: tool_choice keys the cached
                # messages span, so an entry written under a forced round is unreadable
                # by the auto rounds that follow.
                request_messages = build_request_messages(
                    messages,
                    rolling_breakpoint=(
                        self.config.rolling_conversation_cache and tool_choice["type"] == "auto"
                    ),
                )
                request: dict[str, Any] = {
                    "model": self.config.model,
                    "max_tokens": self.config.max_tokens,
                    "system": system,
                    "tools": self._tools,
                    "tool_choice": tool_choice,
                    "messages": request_messages,
                    **self.config.thinking_request_fields(),
                }
                dispatcher = EagerDispatcher(
                    executor.execute, self.config.eager_tool_dispatch and not force_text
                )
                streamed = StreamedRound(
                    specs=self._specs,
                    partial_tools=self._partial_ui_tools,
                    state=state,
                    eager_frames=self.config.eager_partial_frames,
                )
                call_started = time.monotonic()
                # This finally is the dispatcher's only backstop: a started execution (and
                # any delegate run inside it) must not outlive its turn, and the exits that
                # would leak one — a stream error, a malformed stream, the portal closing this
                # generator at a yield — all pass through it. Once ``collect`` has joined
                # every task, cancel is a no-op, so the happy path pays nothing.
                try:
                    async with self.client.messages.stream(**cast(Any, request)) as stream:
                        async for event in streamed.relay(
                            stream, dispatcher, executor.tool_call_event
                        ):
                            yield event
                        final = None if streamed.abandoned else await stream.get_final_message()
                    response = final or streamed
                    log_model_call(
                        logger,
                        request,
                        response,
                        call_started,
                        session.session_id,
                        round=round_index,
                    )
                    if final is None:
                        # The SDK rejected a streamed card's input that is not JSON. The round
                        # is kept as far as it came and that call is answered as an error, so
                        # the model sends it again; the input itself is not logged.
                        reply, tool_uses, unreadable = salvage_round(
                            streamed, dispatcher, logger, session.session_id, round_index
                        )
                    else:
                        reply = assistant_message(final)
                        tool_uses = [block for block in final.content if block.type == "tool_use"]
                        unreadable = set()
                    stop_reason = final.stop_reason if final else "tool_use"
                    accumulate_usage(usage, response)
                    last_prompt = prompt_tokens(response)
                    if reply is not None:
                        messages.append(reply)
                    if turn_attempted_staging(block.name for block in tool_uses):
                        remind = False
                    if not tool_uses or force_text:
                        if remind and not force_text:
                            remind = False
                            messages.append(reminder())
                            continue
                        break

                    # The calls eager dispatch did not announce: started late, or never run.
                    for block in tool_uses:
                        if block.id in unreadable or not dispatcher.started(block.id):
                            yield executor.tool_call_event(
                                block.name, block.id, dict(block.input or {})
                            )

                    async def execute_all(
                        joined: EagerDispatcher = dispatcher, blocks: list[Any] = tool_uses
                    ) -> list[ToolOutcome]:
                        try:
                            return await joined.collect(blocks)
                        finally:
                            progress.put_nowait(None)

                    pending = asyncio.create_task(execute_all())
                    try:
                        while (event := await progress.get()) is not None:
                            yield event
                        outcomes = await pending
                    finally:
                        # A client disconnect lands here; the join itself must not outlive
                        # the turn. The outer finally then cancels what it had started.
                        if not pending.done():
                            pending.cancel()
                            with contextlib.suppress(asyncio.CancelledError):
                                await pending
                        while not progress.empty():
                            progress.get_nowait()
                finally:
                    dispatcher.cancel()
                calls = list(zip(tool_uses, outcomes, strict=True))
                settled = {block.id: outcome for block, outcome in calls}
                for block, outcome in calls:
                    for event in outcome_events(block.name, block.id, outcome):
                        yield event
                messages.append(
                    {
                        "role": "user",
                        "content": [
                            tool_result_block(block.id, outcome) for block, outcome in calls
                        ],
                    }
                )
                settled = {}
                if self.config.close_on_presentation and round_closes_turn(
                    ((block.name, outcome) for block, outcome in calls), executor.ends_clean
                ):
                    # A change request that reaches its chips with nothing staged gets the
                    # reminder before the turn may close; the reminded round can close.
                    if remind:
                        remind = False
                        messages.append(reminder())
                        continue
                    stop_reason = "end_turn"
                    break
        finally:
            close_open_tool_uses(messages, settled)

        cleared = compact_history(
            messages, last_prompt, self.config.compact_history_above_tokens, session.session_id
        )
        yield AgentEvent.turn_complete(stop_reason, usage, elapsed_ms(turn_started), cleared)

    async def update_memory(
        self, messages: list[dict[str, Any]], session: MerchantSessionContext
    ) -> list[MemoryFact]:
        """Extract what the finished turn taught about the operation and store it. Run
        it once the reply has streamed; returns the facts written and never raises."""
        transcript = transcript_text(latest_exchange(messages, HOST_TEXTS), HOST_TEXTS)
        return await self.memory.extract(
            self.client, session.merchant_id, session.session_id, transcript
        )
