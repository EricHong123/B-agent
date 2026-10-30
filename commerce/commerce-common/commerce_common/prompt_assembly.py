# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Where the cache breakpoints go: after the static system text, after the last tool,
and rolling through the conversation on the newest persisted message; and where the
per-request context goes: a second system block, behind the static one's marker.

The request's stable prefix is the tool array and the static system text, and the
rolling marker makes the rounds of a turn cache reads as well. Everything per request —
the cart, the page, the clock, the memory facts — is the second system block, and it is
the same bytes from one turn to the next until the state in it changes (a cart write, a
new page, a saved fact, the next hour): a turn whose state has not moved reads the whole
conversation from cache, and a turn whose state has moved re-reads it once. The roles
decide what goes in the block (see the role prompt modules); this module owns where the
blocks and markers sit, the same on every path.
"""

from __future__ import annotations

from collections.abc import Collection
from datetime import datetime
from typing import Any


def context_clock(now: datetime) -> str:
    """The session clock as the context block carries it: the current hour, with the
    session's offset. The prompts and skills use it for the date and the time of day, and
    rendering the minutes would change the block, and so re-read the conversation, on
    nearly every turn."""
    return now.replace(minute=0, second=0, microsecond=0).isoformat(timespec="minutes")


def build_system_blocks(static_text: str, context: str) -> list[dict[str, Any]]:
    """The system prompt: the static text carrying the cache breakpoint, then the
    per-request context behind it. Nothing per request goes in the first block; a byte's
    change there would re-read the tool array and the static text on every call."""
    return [
        {"type": "text", "text": static_text, "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": context},
    ]


def with_eager_input(tools: list[dict[str, Any]], names: Collection[str]) -> list[dict[str, Any]]:
    """Ask the API to stream these tools' input as it is generated instead of one
    top-level value at a time, so a card's first item can render at its first key. The
    input then arrives as written, valid JSON or not; the turn loop answers a call whose
    input does not parse as an error (``StreamedRound``). Applied to the request copy;
    the registry's bytes stay as built."""
    return [t | {"eager_input_streaming": True} if t.get("name") in names else t for t in tools]


def with_tool_cache_control(tools: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not tools:
        return tools
    tools = [dict(t) for t in tools]
    tools[-1]["cache_control"] = {"type": "ephemeral"}
    return tools


def build_request_messages(
    messages: list[dict[str, Any]],
    *,
    rolling_breakpoint: bool = True,
) -> list[dict[str, Any]]:
    """The outgoing request's messages: a request-shaped copy of ``messages`` with the
    rolling cache breakpoint on the newest persisted content block.

    Within a turn the system blocks are constant, so the marker makes each round's prior
    rounds — the long tool results especially — a cache read instead of a reprocess. Two
    cases skip it. A bare first call (one message) would write an entry a one-shot
    session never reads, and the next call marks a later block whose span carries the
    first message anyway. And the caller passes ``rolling_breakpoint=False`` on rounds
    whose ``tool_choice`` is not ``auto``, because ``tool_choice`` keys the messages
    span: an entry written under a forced round is unreadable by the auto rounds that
    follow.

    A turn that closed on a presentation round leaves a tool_result message followed by
    the next user message; the two go out as one user message, tool_result blocks first.

    Applied per call, to the outgoing request only: the returned list shallow-copies the
    touched message and blocks, strips the marker any earlier call placed, and never
    mutates the host's persisted history. String content is lifted into a one-block list
    because ``cache_control`` lives on content blocks.
    """
    if not messages:
        return []

    def without_marker(message: dict[str, Any]) -> dict[str, Any]:
        content = message.get("content")
        if not isinstance(content, list) or not any(
            isinstance(b, dict) and "cache_control" in b for b in content
        ):
            return message
        return message | {
            "content": [
                {k: v for k, v in b.items() if k != "cache_control"} if isinstance(b, dict) else b
                for b in content
            ]
        }

    def blocks(raw: Any) -> list[Any]:
        return [{"type": "text", "text": raw}] if isinstance(raw, str) else list(raw or [])

    request: list[dict[str, Any]] = []
    for message in messages:
        message = without_marker(message)
        if request and message.get("role") == "user" and request[-1].get("role") == "user":
            request[-1] = request[-1] | {
                "content": blocks(request[-1].get("content")) + blocks(message.get("content"))
            }
        else:
            request.append(message)
    if not rolling_breakpoint or len(request) < 2:
        return request
    content = blocks(request[-1].get("content"))
    if content and isinstance(content[-1], dict):
        content[-1] = {**content[-1], "cache_control": {"type": "ephemeral"}}
        request[-1] = request[-1] | {"content": content}
    return request
