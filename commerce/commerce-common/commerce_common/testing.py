# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Scripted stand-ins for the two model-client contracts, plus a memory store that counts
its reads. ``FakeClient`` plays back ``messages.stream`` and ``FakeCreateClient`` plays back
``messages.create``; both record each request's kwargs in ``calls`` and raise once the
script runs out, so a looping agent fails a test instead of hanging it."""

from __future__ import annotations

import copy
import itertools
import json
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from commerce_common.memory import InMemoryMemoryStore
from commerce_common.types import MemoryCategory, MemoryFact

# -- content blocks and final messages ---------------------------------------------------


class FakeBlock:
    """A content block that quacks like the SDK's: attribute access plus ``model_dump``."""

    def __init__(self, **fields: Any) -> None:
        self._fields = fields
        for key, value in fields.items():
            setattr(self, key, value)

    def model_dump(self, **kwargs: Any) -> dict[str, Any]:
        del kwargs
        return dict(self._fields)


def text_block(text: str) -> FakeBlock:
    return FakeBlock(type="text", text=text)


def tool_use_block(name: str, tool_input: dict[str, Any], block_id: str = "tu-1") -> FakeBlock:
    return FakeBlock(type="tool_use", id=block_id, name=name, input=tool_input)


def _usage() -> SimpleNamespace:
    return SimpleNamespace(
        input_tokens=1, output_tokens=1, cache_read_input_tokens=0, cache_creation_input_tokens=0
    )


def text_message(text: str) -> SimpleNamespace:
    """A final message ending the turn with one text block."""
    return SimpleNamespace(stop_reason="end_turn", usage=_usage(), content=[text_block(text)])


def tool_use_message(name: str, tool_input: dict[str, Any]) -> SimpleNamespace:
    """A final message requesting one tool call."""
    return tool_calls_message((name, tool_input))


def tool_calls_message(*calls: tuple[Any, ...]) -> SimpleNamespace:
    """A final message requesting several tool calls; each call is ``(name, input)`` or
    ``(name, input, block_id)``, ids defaulting to ``tu-1``, ``tu-2``, ..."""
    content = [
        tool_use_block(call[0], call[1], call[2] if len(call) > 2 else f"tu-{index + 1}")
        for index, call in enumerate(calls)
    ]
    return SimpleNamespace(stop_reason="tool_use", usage=_usage(), content=content)


def create_response(*blocks: FakeBlock, stop_reason: str = "tool_use") -> SimpleNamespace:
    """What ``messages.create`` returns: the blocks, a stop reason, and usage."""
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason, usage=_usage())


# -- messages.stream -----------------------------------------------------------------------

# Scripted input_json_delta pieces per content-block index.
Chunks = dict[int, list[str | BaseException]]


class FakeStream:
    """The SDK stream's raw-event iteration for one scripted final message: a
    ``content_block_start`` per block, its deltas (one text delta, or the tool input as
    one JSON delta unless ``chunks`` scripts several pieces for that block index), then
    its ``content_block_stop`` — the event eager dispatch executes from. A piece that is
    an exception is raised in place of its delta, the way the SDK's accumulator rejects
    tool input that is not JSON."""

    def __init__(self, final: SimpleNamespace, chunks: Chunks | None = None) -> None:
        self._final = final
        self._chunks = chunks or {}

    async def __aenter__(self) -> FakeStream:
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        return False

    def __aiter__(self):
        async def events():
            usage = getattr(self._final, "usage", None)
            if usage is not None:
                # The stream reports cumulative counts: input side at the start, output
                # side as the message grows; a round abandoned mid-stream keeps them.
                yield SimpleNamespace(type="message_start", message=SimpleNamespace(usage=usage))
            for index, block in enumerate(self._final.content):
                yield SimpleNamespace(type="content_block_start", index=index, content_block=block)
                block_type = getattr(block, "type", None)
                if block_type == "text":
                    delta = SimpleNamespace(type="text_delta", text=block.text)
                    yield SimpleNamespace(type="content_block_delta", index=index, delta=delta)
                elif block_type == "tool_use":
                    for piece in self._chunks.get(index, [json.dumps(block.input or {})]):
                        if isinstance(piece, BaseException):
                            raise piece
                        delta = SimpleNamespace(type="input_json_delta", partial_json=piece)
                        yield SimpleNamespace(type="content_block_delta", index=index, delta=delta)
                yield SimpleNamespace(type="content_block_stop", index=index)
            if usage is not None:
                yield SimpleNamespace(type="message_delta", usage=usage)

        return events()

    async def get_final_message(self) -> SimpleNamespace:
        return self._final


class FakeClient:
    """Plays back one scripted final message per ``messages.stream`` call. ``chunks``
    applies to the first call only."""

    def __init__(self, responses: Iterable[SimpleNamespace], chunks: Chunks | None = None) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = list(responses)
        self._chunks = chunks
        self.messages = SimpleNamespace(stream=self._stream)

    def _stream(self, **kwargs: Any) -> FakeStream:
        self.calls.append(kwargs)
        if not self._responses:
            raise AssertionError("more model calls than scripted responses")
        return FakeStream(self._responses.pop(0), self._chunks if len(self.calls) == 1 else None)


# -- messages.create -----------------------------------------------------------------------


class FakeCreateClient:
    """Plays back one scripted response per ``messages.create`` call. Requests are recorded
    deep-copied, since callers extend their message lists in place between calls;
    ``before_call`` (awaited with the call index) lets a test hold or stall a call."""

    def __init__(
        self,
        responses: Iterable[SimpleNamespace],
        *,
        before_call: Callable[[int], Awaitable[object]] | None = None,
    ) -> None:
        self.calls: list[dict[str, Any]] = []
        self._responses = iter(responses)
        self._before_call = before_call
        self.messages = SimpleNamespace(create=self._create)

    async def _create(self, **kwargs: Any) -> SimpleNamespace:
        index = len(self.calls)
        self.calls.append(copy.deepcopy(kwargs))
        if self._before_call is not None:
            await self._before_call(index)
        try:
            return next(self._responses)
        except StopIteration:
            raise AssertionError("more model calls than scripted responses") from None


def extraction_client(
    proposals: Iterable[dict[str, Any]],
    *,
    before_call: Callable[[int], Awaitable[object]] | None = None,
) -> FakeCreateClient:
    """A create client whose every call proposes ``proposals`` as ``record_fact`` calls."""
    response = create_response(
        *(
            tool_use_block("record_fact", dict(proposal), f"tu-{i + 1}")
            for i, proposal in enumerate(proposals)
        )
    )
    return FakeCreateClient(itertools.repeat(response), before_call=before_call)


# -- tool results and memory -----------------------------------------------------------------


def result_text(result: Any) -> str:
    """The text of a tool result in the Agent SDK's dict shape or MCP's ``CallToolResult``."""
    blocks = result["content"] if isinstance(result, dict) else result.content
    parts = [
        block["text"] if isinstance(block, dict) else block.text
        for block in blocks
        if _is_text(block)
    ]
    return " ".join(parts)


def _is_text(block: Any) -> bool:
    return (
        block.get("type") if isinstance(block, dict) else getattr(block, "type", None)
    ) == "text"


class SpyStore(InMemoryMemoryStore):
    """An in-memory store counting the reads made through the memory tools and prompt."""

    def __init__(self) -> None:
        super().__init__()
        self.reads = 0

    async def get_facts(self, subject_id: str) -> list[MemoryFact]:
        self.reads += 1
        return await super().get_facts(subject_id)

    async def search_facts(self, subject_id: str, query: str) -> list[MemoryFact]:
        self.reads += 1
        return await super().search_facts(subject_id, query)

    def seed(self, subject_id: str, key: str, value: str, *, days_old: int = 0) -> SpyStore:
        """Plant a constraint saved ``days_old`` days ago, as if by an earlier session."""
        fact = MemoryFact(
            key=key,
            value=value,
            category=MemoryCategory.CONSTRAINT,
            updated_at=datetime.now(UTC) - timedelta(days=days_old),
        )
        self._data.setdefault(subject_id, {})[key] = fact
        return self

    def keys(self, subject_id: str) -> list[str]:
        """The keys held for ``subject_id``, read without counting."""
        return list(self._data.get(subject_id, {}))
