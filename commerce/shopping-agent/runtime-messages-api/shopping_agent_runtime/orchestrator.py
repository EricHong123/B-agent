# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The shopping agent's turn loop on the Messages API: one model call per iteration,
tools dispatched eagerly as their blocks close, presentation calls rendered while they
stream, a rolling cache breakpoint through the conversation, a round of clean
presentation calls that includes the chips ending the turn (``close_on_presentation``),
and memory extracted once the reply is out.

    agent = ShoppingAgent(backend=my_backend, skills_dir=Path("shopping-agent/skills"))
    async for event in agent.stream_turn(messages, session, state):
        ...
    await agent.update_memory(messages, session)
"""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import AsyncIterator, Sequence
from pathlib import Path
from typing import Any, cast

from anthropic import AsyncAnthropic

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
from shopping_agent.backend import StorefrontBackend
from shopping_agent.config import ShoppingAgentConfig
from shopping_agent.enrichment import PRESENTATION_COMPONENTS
from shopping_agent.executor import ShoppingToolExecutor, build_memory
from shopping_agent.grounding import GROUNDING_RULES
from shopping_agent.prompt import build_dynamic_context, build_static_system
from shopping_agent.tools.registry import build_tools
from shopping_agent.types import Cart, ShoppingSessionContext, ShoppingSessionState, UserPreferences

logger = logging.getLogger(__name__)


class ShoppingAgent:
    """One deployment of the agent. ``memory`` is its :class:`MemoryRuntime`; a host
    with its own memory routes reads and writes through ``memory.store``.
    ``executor_class`` is the seam for a deployment's own :class:`ShoppingToolExecutor`
    subclass (its own ``domain_error`` mapping or result wording)."""

    def __init__(
        self,
        *,
        backend: StorefrontBackend,
        skills: SkillRegistry | None = None,
        skills_dir: Path | None = None,
        config: ShoppingAgentConfig | None = None,
        memory_store: MemoryStore | None = None,
        memory_write_filter: MemoryWriteFilter | None = None,
        client: AsyncAnthropic | None = None,
        extra_presentation_tools: Sequence[PresentationExtension] = (),
        executor_class: type[ShoppingToolExecutor] = ShoppingToolExecutor,
    ) -> None:
        if skills is None:
            skills = SkillRegistry.from_dir(skills_dir) if skills_dir else SkillRegistry([])
        self.config = config or ShoppingAgentConfig()
        self.executor_class = executor_class
        self.backend = backend
        self.skills = skills
        self.memory: MemoryRuntime = build_memory(self.config, memory_store, memory_write_filter)
        self.client = client or AsyncAnthropic(timeout=self.config.request_timeout_s)
        self.extra_presentation_tools = tuple(extra_presentation_tools)
        self._specs: dict[str, PresentationComponent] = {
            **PRESENTATION_COMPONENTS,
            **{ext.name: ext for ext in self.extra_presentation_tools},
        }
        self._partial_ui_tools = partial_ui_tool_names(
            PRESENTATION_COMPONENTS, self.extra_presentation_tools
        )
        # Built once: the same bytes on every request of this deployment. The
        # presentation tools that render while they stream ask the API for their input
        # as it is generated.
        self._static_system = build_static_system(self.config, self.skills)
        self._tools = with_tool_cache_control(
            with_eager_input(
                build_tools(self.config, self.skills.names, self.extra_presentation_tools),
                self._partial_ui_tools,
            )
        )

    async def stream_turn(
        self,
        messages: list[dict[str, Any]],
        session: ShoppingSessionContext,
        state: ShoppingSessionState | None = None,
    ) -> AsyncIterator[AgentEvent]:
        """Run one turn. ``messages`` ends with the user's message and is extended in
        place with the turn's assistant messages and tool results, so the host stores it
        as is; ``state`` carries the session's provenance and comes back on every turn."""
        state = state if state is not None else ShoppingSessionState()
        turn_started = time.monotonic()
        preferences, cart, memory_facts, account = await self._prefetch(session)
        # The second system block, built once per turn: the same bytes across the turn's
        # rounds, and across turns until the state in it moves (prompt_assembly).
        context = build_dynamic_context(
            preferences=preferences,
            memory_facts=memory_facts,
            cart=cart,
            page=session.page,
            now=session.local_now(),
            reply_language=session.reply_language,
            account=account,
            account_max_chars=self.config.max_context_chars,
        )
        system = build_system_blocks(self._static_system, context)
        executor = self.executor_class(
            backend=self.backend,
            config=self.config,
            skills=self.skills,
            session=session,
            state=state,
            memory=self.memory,
            extensions=self.extra_presentation_tools,
        )
        forced_tool = first_forced_tool(
            GROUNDING_RULES, self.config, latest_user_text(messages), state
        )
        usage = usage_totals()
        stop_reason: str | None = None
        last_prompt = 0

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
                # This finally is the dispatcher's only backstop: a started execution must
                # not outlive its turn, and the exits that would leak one — a stream error,
                # a malformed stream, the host closing this generator at a yield — all pass
                # through it. Once ``collect`` has joined every task, cancel is a no-op, so
                # the happy path pays nothing.
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
                    if not tool_uses or force_text:
                        break

                    # The calls eager dispatch did not announce: started late, or never run.
                    for block in tool_uses:
                        if block.id in unreadable or not dispatcher.started(block.id):
                            yield executor.tool_call_event(
                                block.name, block.id, dict(block.input or {})
                            )
                    outcomes = await dispatcher.collect(tool_uses)
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
                    stop_reason = "end_turn"
                    break
        finally:
            close_open_tool_uses(messages, settled)

        cleared = compact_history(
            messages, last_prompt, self.config.compact_history_above_tokens, session.session_id
        )
        yield AgentEvent.turn_complete(stop_reason, usage, elapsed_ms(turn_started), cleared)

    async def update_memory(
        self, messages: list[dict[str, Any]], session: ShoppingSessionContext
    ) -> list[MemoryFact]:
        """Extract what the finished turn taught and store it. Run it once the reply has
        streamed; returns the facts written and never raises."""
        transcript = transcript_text(latest_exchange(messages))
        return await self.memory.extract(
            self.client, session.user_id, session.session_id, transcript
        )

    async def _prefetch(
        self, session: ShoppingSessionContext
    ) -> tuple[UserPreferences | None, Cart | None, list[MemoryFact], dict[str, Any] | None]:
        preferences, account, cart, facts = await asyncio.gather(
            fetched(self.backend.get_preferences(session)),
            fetched(self.backend.get_account_context(session)),
            fetched(self.backend.get_cart(session) if self.config.enable_cart else None),
            fetched(self.memory.tier_one(session.user_id)),
        )
        return preferences, cart, list(facts or []), account
