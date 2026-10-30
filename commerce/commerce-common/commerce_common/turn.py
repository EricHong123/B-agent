# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Pieces of the Messages API turn loop that both roles use the same way: reading the
conversation (latest user text, the exchange memory extraction reads, compaction), running
a round (:class:`StreamedRound`, eager dispatch, the test for a round that ends the turn on
its chips), and recording it (host events, ``tool_result`` blocks, usage, the model-call
log record). ``host_texts`` names messages the runtime itself appended as the user (a
reminder); they never count as the user's words.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import time
from collections.abc import (
    AsyncIterator,
    Awaitable,
    Callable,
    Collection,
    Iterable,
    Iterator,
    Mapping,
)
from dataclasses import dataclass, field
from types import SimpleNamespace
from typing import Any

from .presentation import CHIPS_TOOL, PresentationComponent, enrich_partial
from .streaming import AgentEvent, ToolOutcome, parse_partial_json

logger = logging.getLogger(__name__)

# Tool results longer than this collapse to "ok" in the trace, with an excerpt.
_SUMMARY_MAX_CHARS = 200
_EXCERPT_MAX_CHARS = 1200
CLEARED_RESULT = "[result cleared from an earlier turn; call the tool again if it is needed]"
# The result of a call whose streamed input never became JSON; the input is not echoed.
UNREADABLE_INPUT_TEXT = (
    "The arguments for this call did not arrive as valid JSON, so it was not run. "
    "Send the call again."
)


def _text_blocks(content: Any) -> list[str]:
    if isinstance(content, str):
        return [content]
    if not isinstance(content, list):
        return []
    return [
        str(block.get("text", ""))
        for block in content
        if isinstance(block, dict) and block.get("type") == "text"
    ]


def _is_user_text(message: dict[str, Any], host_texts: Collection[str]) -> bool:
    if message.get("role") != "user":
        return False
    texts = _text_blocks(message.get("content"))
    return bool(texts) and not all(text in host_texts for text in texts)


def latest_user_text(messages: list[dict[str, Any]], host_texts: Collection[str] = ()) -> str:
    """The most recent user-authored text; "" when the conversation has none."""
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        texts = _text_blocks(content)
        if texts and all(text in host_texts for text in texts):
            continue
        if texts:
            return "\n".join(texts)
        # A message of tool results is the loop's own; anything else ends the search.
        if isinstance(content, list) and any(
            isinstance(block, dict) and block.get("type") == "tool_result" for block in content
        ):
            continue
        return ""
    return ""


def latest_exchange(
    messages: list[dict[str, Any]], host_texts: Collection[str] = ()
) -> list[dict[str, Any]]:
    """The slice from the most recent user-authored message onward: what one turn's
    extraction pass reads, so earlier turns are not re-extracted in new words."""
    for index in range(len(messages) - 1, -1, -1):
        if _is_user_text(messages[index], host_texts):
            return messages[index:]
    return messages


def transcript_text(messages: list[dict[str, Any]], host_texts: Collection[str] = ()) -> str:
    """The user and assistant text of ``messages`` as ``role: text`` lines; tool blocks
    and host-appended messages are left out."""
    lines = []
    for message in messages:
        role = message.get("role", "")
        for text in _text_blocks(message.get("content")):
            if text and text not in host_texts:
                lines.append(f"{role}: {text}")
    return "\n".join(lines)


def session_tag(session_id: str | None) -> str:
    """What a log record carries in place of a session id, which on the example hosts is also
    the request credential: the first twelve hex digits of its SHA-256, so the lines of one
    session correlate and an operator holding the id can compute the tag, but a log reader
    cannot use it. ``None`` (no session) logs as ``-``."""
    return hashlib.sha256(session_id.encode()).hexdigest()[:12] if session_id else "-"


def prompt_tokens(response: Any) -> int:
    """The size of the prompt a call was given, as the model counted it: fresh input plus
    what was read from and written to the cache."""
    return sum(count for key, count in call_usage(response).items() if key != "output_tokens")


def compact_history(
    messages: list[dict[str, Any]], last_prompt_tokens: int, max_tokens: int, session_id: str
) -> int:
    """After a turn whose last call was given ``max_tokens`` or more, replace the oldest tool
    results in the stored conversation with ``CLEARED_RESULT`` until it is half its size, and
    return how many were cleared; ``0`` turns this off. The next turn's first round rewrites
    the cached span once and every round after reads the shorter one. Provenance lives on the
    session state, so nothing a gate checks is cleared."""
    if not max_tokens or last_prompt_tokens < max_tokens:
        return 0
    size = len(json.dumps(messages))
    target = size // 2
    cleared = 0
    results = (
        block
        for message in messages
        if isinstance(message.get("content"), list)
        for block in message["content"]
        if block.get("type") == "tool_result" and isinstance(block.get("content"), str)
    )
    for block in results:
        if size <= target:
            break
        if len(block["content"]) > len(CLEARED_RESULT):
            size -= len(block["content"]) - len(CLEARED_RESULT)
            block["content"] = CLEARED_RESULT
            cleared += 1
    logger.info(
        "history compacted session=%s prompt_tokens=%d results_cleared=%d",
        session_tag(session_id),
        last_prompt_tokens,
        cleared,
    )
    return cleared


async def fetched(coro: Any) -> Any:
    """Await a prefetch; None when it fails (logged at WARNING with its traceback) or when
    ``coro`` is None (a slot the deployment switches off), so the turn goes ahead without
    that slot."""
    if coro is None:
        return None
    name = getattr(coro, "__qualname__", type(coro).__name__)
    try:
        return await coro
    except Exception:
        logger.warning("prefetch %s failed and the turn continues without it", name, exc_info=True)
        return None


class EagerDispatcher:
    """Tool execution started mid-stream. When a ``tool_use`` block's buffered JSON
    parses at ``content_block_stop``, the call's arguments are final — the loop starts
    executing then, while the model writes the rest of the round, so tool time overlaps
    generation time. ``collect`` is the post-stream join: started calls are awaited,
    anything the stream path missed (unparseable buffer, dispatch off) executes from the
    final message's canonical args, and every call runs exactly once. ``cancel`` is the
    error and malformed-stream backstop; a started task must not outlive its turn."""

    def __init__(
        self, execute: Callable[[str, dict[str, Any]], Awaitable[ToolOutcome]], enabled: bool
    ) -> None:
        self._execute = execute
        self._enabled = enabled
        self._tasks: dict[str, asyncio.Future[ToolOutcome]] = {}

    def started(self, tool_use_id: str) -> bool:
        return tool_use_id in self._tasks

    def dispatch(self, name: str, tool_use_id: str, args: dict[str, Any] | None) -> bool:
        """Start ``name`` on ``args``; False when it did not start (dispatch off, already
        started, or no parsed args) and the join executes it later."""
        if not self._enabled or args is None or tool_use_id in self._tasks:
            return False
        self._tasks[tool_use_id] = asyncio.ensure_future(self._execute(name, args))
        return True

    def settle(self, tool_use_id: str, outcome: ToolOutcome) -> None:
        """Give ``tool_use_id`` its outcome without executing it (a call whose input
        never parsed); the join returns it in place. A started call keeps its task."""
        if tool_use_id in self._tasks:
            return
        settled: asyncio.Future[ToolOutcome] = asyncio.get_running_loop().create_future()
        settled.set_result(outcome)
        self._tasks[tool_use_id] = settled

    async def collect(self, tool_uses: list[Any]) -> list[ToolOutcome]:
        return await asyncio.gather(
            *(
                self._tasks[block.id]
                if block.id in self._tasks
                else self._execute(block.name, dict(block.input or {}))
                for block in tool_uses
            )
        )

    def cancel(self) -> None:
        for task in self._tasks.values():
            task.cancel()


@dataclass
class StreamedTool:
    """One tool block of the round while it streams. ``server`` marks a server tool
    (web search), whose input is recorded and never dispatched; ``signature`` is the
    key of the last ``ui_partial`` frame the call produced."""

    name: str
    id: str
    server: bool = False
    buffer: str = ""
    closed: bool = False
    signature: str | None = None

    def parsed(self) -> dict[str, Any] | None:
        """The buffered input as a dict once it is complete JSON, else None."""
        try:
            args = json.loads(self.buffer) if self.buffer.strip() else {}
        except ValueError:
            return None
        return args if isinstance(args, dict) else None


@dataclass
class StreamedRound:
    """The round's content blocks as the raw stream events deliver them, and the host
    events they produce on the way (:meth:`relay`). A tool's input that streams as written
    (``with_eager_input``) can arrive as text that is not JSON, which the SDK's stream
    accumulator rejects with a ``ValueError`` mid-stream; the round is then ``abandoned``
    and :meth:`salvaged` rebuilds it from what did arrive, so the turn goes on and the
    model hears which call to send again. ``usage`` is the stream's own counts, so an
    abandoned round is counted like a finished one. The first four fields configure the
    partial frames: the component specs, the tools that render while they stream, the
    session state their partial hooks read, and whether every visible change emits."""

    specs: Mapping[str, PresentationComponent] = field(default_factory=dict)
    partial_tools: Collection[str] = ()
    state: Any = None
    eager_frames: bool = False
    blocks: list[dict[str, Any]] = field(default_factory=list)
    tools: dict[int, StreamedTool] = field(default_factory=dict)
    usage: SimpleNamespace = field(default_factory=lambda: SimpleNamespace(**usage_totals()))
    # What the model-call record reports for a round the accumulator abandoned.
    stop_reason: str = "abandoned"
    abandoned: bool = False

    def feed(self, raw: Any) -> StreamedTool | None:
        """Record one raw stream event; returns the tool it touched, if any."""
        raw_type = getattr(raw, "type", "")
        if raw_type in ("message_start", "message_delta"):
            # The stream's counts are cumulative, so the latest value of each replaces ours.
            counts = getattr(raw.message if raw_type == "message_start" else raw, "usage", None)
            for key in usage_totals():
                if isinstance(value := getattr(counts, key, None), int):
                    setattr(self.usage, key, value)
            return None
        index = getattr(raw, "index", None)
        if not isinstance(index, int):
            return None
        if raw_type == "content_block_start":
            block = raw.content_block
            entry = dict(block.model_dump(exclude_none=True, exclude={"citations"}))
            kind = entry.get("type")
            # The streamed fields start empty here and grow from the deltas.
            if kind == "text":
                entry["text"] = ""
            elif kind == "thinking":
                entry["thinking"] = ""
            elif kind in ("tool_use", "server_tool_use"):
                entry["input"] = {}
                self.tools[index] = StreamedTool(
                    name=block.name, id=block.id, server=kind == "server_tool_use"
                )
            self.blocks.append(entry)
            return self.tools.get(index)
        if raw_type == "content_block_delta":
            delta = raw.delta
            delta_type = getattr(delta, "type", "")
            if (tool := self.tools.get(index)) is not None:
                if delta_type == "input_json_delta":
                    tool.buffer += delta.partial_json
                return tool
            entry = self.blocks[index] if index < len(self.blocks) else {}
            if delta_type == "text_delta":
                entry["text"] = entry.get("text", "") + delta.text
            elif delta_type == "thinking_delta":
                entry["thinking"] = entry.get("thinking", "") + delta.thinking
            elif delta_type == "signature_delta":
                entry["signature"] = delta.signature
            return None
        if raw_type == "content_block_stop" and (tool := self.tools.get(index)) is not None:
            tool.closed = True
            if tool.server and (args := tool.parsed()) is not None:
                self.blocks[index]["input"] = args
            return tool
        return None

    def tool_open(self) -> bool:
        """True while a tool's input is mid-stream: the one state in which the SDK's
        accumulator raises."""
        return any(not tool.closed for tool in self.tools.values())

    def frame(self, tool: StreamedTool) -> AgentEvent | None:
        """The ``ui_partial`` event for ``tool`` after its latest input delta, or None.
        By default a frame goes out on structural change only, so the stream stays light
        and no half-written string renders; with ``eager_frames`` every visible payload
        change emits, so text inside a card grows as it generates."""
        if tool.name not in self.partial_tools:
            return None
        parsed = parse_partial_json(tool.buffer, settle_strings=not self.eager_frames)
        partial = enrich_partial(self.specs[tool.name], parsed, self.state) if parsed else None
        if partial is None:
            return None
        component, payload, signature = partial
        key = json.dumps(payload if self.eager_frames else signature, sort_keys=True, default=str)
        if key == tool.signature:
            return None
        tool.signature = key
        return AgentEvent.ui_partial(component, payload, tool.id)

    async def relay(
        self,
        stream: Any,
        dispatcher: EagerDispatcher,
        announce: Callable[[str, str, dict[str, Any]], AgentEvent],
    ) -> AsyncIterator[AgentEvent]:
        """Feed every raw event of ``stream`` through this round and yield the host
        events it produces meanwhile: text deltas, partial frames, and ``announce``'s
        ``tool_call`` event for each call eager dispatch starts when its block closes.
        Only the SDK's rejection of an open tool's input is caught (the round ends
        ``abandoned``); anything a partial hook raises propagates."""
        events = aiter(stream)
        while True:
            try:
                raw = await anext(events)
            except StopAsyncIteration:
                return
            except ValueError:
                if not self.tool_open():
                    raise
                self.abandoned = True
                return
            tool = self.feed(raw)
            raw_type = getattr(raw, "type", "")
            if raw_type == "content_block_delta":
                delta = raw.delta
                if getattr(delta, "type", "") == "text_delta" and delta.text:
                    yield AgentEvent.text_delta(delta.text)
                elif tool is not None and (frame := self.frame(tool)) is not None:
                    yield frame
            elif raw_type == "content_block_stop" and tool is not None and not tool.server:
                args = tool.parsed()
                if dispatcher.dispatch(tool.name, tool.id, args):
                    yield announce(tool.name, tool.id, args or {})

    def salvaged(self) -> tuple[dict[str, Any] | None, list[Any], set[str]]:
        """The round as far as it streamed: the assistant message for the conversation,
        the client tool calls in it (objects with ``name``, ``id``, ``input`` like the
        SDK's blocks), and the ids whose input never parsed, recorded with ``{}`` as
        input."""
        unreadable: set[str] = set()
        tool_uses: list[Any] = []
        for index, entry in enumerate(self.blocks):
            if (tool := self.tools.get(index)) is None:
                continue
            parsed = tool.parsed() if tool.closed else None
            if parsed is not None:
                entry["input"] = parsed
            else:
                unreadable.add(tool.id)
            if not tool.server:
                tool_uses.append(SimpleNamespace(name=tool.name, id=tool.id, input=entry["input"]))
        content = [entry for entry in self.blocks if entry.get("type") != "text" or entry["text"]]
        message = {"role": "assistant", "content": content} if content else None
        return message, tool_uses, unreadable


def salvage_round(
    streamed: StreamedRound,
    dispatcher: EagerDispatcher,
    caller: logging.Logger,
    session_id: str | None,
    round_index: int,
) -> tuple[dict[str, Any] | None, list[Any], set[str]]:
    """:meth:`StreamedRound.salvaged` for a round the SDK's accumulator abandoned, with
    each unreadable client call settled on ``dispatcher`` as an error result so the model
    sends it again, and a WARNING per unreadable call on ``caller`` naming it and the size
    of what arrived, never the input."""
    reply, tool_uses, unreadable = streamed.salvaged()
    for tool in streamed.tools.values():
        if tool.id not in unreadable:
            continue
        caller.warning(
            "tool input unreadable session=%s round=%d tool=%s id=%s chars=%d",
            session_tag(session_id),
            round_index,
            tool.name,
            tool.id,
            len(tool.buffer),
            stacklevel=2,
        )
        if not tool.server:
            dispatcher.settle(tool.id, ToolOutcome.error(UNREADABLE_INPUT_TEXT))
    return reply, tool_uses, unreadable


def usage_totals() -> dict[str, int]:
    return {
        "input_tokens": 0,
        "output_tokens": 0,
        "cache_read_input_tokens": 0,
        "cache_creation_input_tokens": 0,
    }


def call_usage(response: Any) -> dict[str, int]:
    """The four counters of ``response.usage``; a :class:`StreamedRound` counts as one."""
    usage = getattr(response, "usage", None)
    return {key: getattr(usage, key, 0) or 0 for key in usage_totals()}


def accumulate_usage(totals: dict[str, int], response: Any) -> None:
    for key, count in call_usage(response).items():
        totals[key] += count


def elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def log_model_call(
    caller: logging.Logger,
    request: dict[str, Any],
    response: Any,
    started: float,
    session_id: str | None,
    **ids: Any,
) -> None:
    """The record every model call writes, on the caller's logger and attributed to the
    calling line: at INFO the session's tag and the ids the caller passes, the model, the
    stop reason, the usage, and the time taken; at DEBUG the request as sent and the
    response as received. ``docs/safety.md`` says what the bodies contain and so what a
    DEBUG log holds."""
    tags = " ".join(
        f"{key}={value}" for key, value in {"session": session_tag(session_id), **ids}.items()
    )
    usage = call_usage(response)
    caller.info(
        "model call %s model=%s stop=%s input=%d cache_read=%d cache_write=%d output=%d elapsed_ms=%d",
        tags,
        request.get("model"),
        getattr(response, "stop_reason", None),
        usage["input_tokens"],
        usage["cache_read_input_tokens"],
        usage["cache_creation_input_tokens"],
        usage["output_tokens"],
        elapsed_ms(started),
        stacklevel=2,
    )
    if caller.isEnabledFor(logging.DEBUG):
        caller.debug("model request %s %s", tags, json.dumps(request, default=str), stacklevel=2)
        body = (
            response.model_dump_json()
            if hasattr(response, "model_dump_json")
            else json.dumps({"content": response.blocks, "abandoned": True}, default=str)
        )
        caller.debug("model response %s %s", tags, body, stacklevel=2)


def assistant_message(final: Any) -> dict[str, Any] | None:
    """The final response as a message dict for the conversation, or None when empty."""
    content = [
        block.model_dump(exclude_none=True, exclude={"citations"}) for block in final.content
    ]
    return {"role": "assistant", "content": content} if content else None


def outcome_events(tool: str, tool_use_id: str, outcome: ToolOutcome) -> Iterator[AgentEvent]:
    """The host events for one finished tool call: the outcome's own events (``ui``
    events stamped with the call id), then its ``tool_result``."""
    for event in outcome.events:
        if event.type == "ui":
            event.data = {**event.data, "stream_id": tool_use_id}
        yield event
    keep_text = outcome.refused or len(outcome.result_text) < _SUMMARY_MAX_CHARS
    yield AgentEvent.tool_result(
        tool,
        tool_use_id,
        outcome.result_text if keep_text else "ok",
        outcome.is_error,
        status="blocked" if outcome.blocked else None,
        reason=outcome.blocked,
        excerpt=None if keep_text else outcome.result_text[:_EXCERPT_MAX_CHARS],
        evidence=outcome.evidence or None,
        no_match=outcome.no_match,
    )


def round_closes_turn(
    calls: Iterable[tuple[str, ToolOutcome]], clean: Callable[[str, ToolOutcome], bool]
) -> bool:
    """True when a round can end the turn with no closing model call: the chips tool
    succeeded in it and every call in it is one ``clean`` accepts (the executor's
    ``ends_clean``: a presentation call that was not refused, held, or annotated)."""
    calls = list(calls)
    return any(name == CHIPS_TOOL for name, _ in calls) and all(clean(*call) for call in calls)


def tool_result_block(tool_use_id: str, outcome: ToolOutcome) -> dict[str, Any]:
    return {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": outcome.result_text,
        "is_error": outcome.is_error,
    }


INTERRUPTED_RESULT_TEXT = (
    "The turn was interrupted before this call returned; call it again if it is still needed."
)


def close_open_tool_uses(
    messages: list[dict[str, Any]], settled: Mapping[str, ToolOutcome] | None = None
) -> int:
    """If the conversation ends on an assistant message whose ``tool_use`` blocks have no
    ``tool_result`` after them (the host closed the turn mid-round, or a round raised),
    append one result per call so the stored conversation stays valid for the next
    request: the call's real outcome when ``settled`` has it (a write that finished is
    reported as done, not as one to repeat), else an error naming the interruption.
    Returns how many results it appended."""
    if not messages or messages[-1].get("role") != "assistant":
        return 0
    content = messages[-1].get("content")
    if not isinstance(content, list):
        return 0
    ids = [
        (block.get("id") if isinstance(block, dict) else getattr(block, "id", None))
        for block in content
        if (block.get("type") if isinstance(block, dict) else getattr(block, "type", None))
        == "tool_use"
    ]
    if not ids:
        return 0
    settled = settled or {}
    messages.append(
        {
            "role": "user",
            "content": [
                tool_result_block(tool_use_id, settled[tool_use_id])
                if tool_use_id in settled
                else {
                    "type": "tool_result",
                    "tool_use_id": tool_use_id,
                    "content": INTERRUPTED_RESULT_TEXT,
                    "is_error": True,
                }
                for tool_use_id in ids
            ],
        }
    )
    return len(ids)
