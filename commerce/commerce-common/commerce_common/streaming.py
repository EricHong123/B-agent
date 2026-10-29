# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The events an agent turn yields to its host, and the outcome type every tool call
produces. Hosts render the event types below and ignore any they do not know.

==================  ==========================================================
``text_delta``      ``{"text"}``: incremental assistant text.
``tool_call``       ``{"tool", "id", "input"[, "label"]}``; ``label`` is the model's few
                    words for the person waiting while the call runs (the call's
                    ``status`` argument), absent on presentation calls.
``tool_result``     ``{"tool", "id", "summary", "is_error", "status"[, "reason", "excerpt",
                    "evidence", "no_match"]}``; ``status`` is ``ok``, ``error``, or
                    ``blocked`` (a gate held the call; ``reason`` names the gate);
                    ``evidence`` lists the versioned sources the read returned or withheld,
                    one ``{"source_id", "version", "effective_at", "status"}`` each
                    (the host shows the current ones as the reply's sources); ``no_match`` is
                    ``true`` when a read found nothing to return.
``ui``              ``{"component", "payload"}``: a validated, enriched component.
``ui_partial``      The same, plus ``stream_id``, while the call is still being
                    generated; the final ``ui`` event carries the same ``stream_id``.
``cart_update``     ``{"cart"}``: the whole cart.
``change_update``   ``{"change"}``: a staged change's whole record after it moved.
``progress``        ``{"message"[, "tool", "step"]}``: a status line to replace the
                    previous one and clear on that tool's ``tool_result``.
``turn_complete``   ``{"stop_reason", "usage", "elapsed_ms", "results_cleared"}``: ``usage``
                    sums the turn's model calls, the analysis delegate's included;
                    ``results_cleared`` counts earlier tool results the turn compacted, so a
                    host that appends its transcript rewrites it when this is nonzero.
``error``           ``{"message"}``, safe to show; emitted by the host when ``stream_turn``
                    raises (the example hosts map API errors to it).
==================  ==========================================================
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any, Literal

from pydantic import BaseModel, Field

EventType = Literal[
    "text_delta",
    "tool_call",
    "tool_result",
    "ui",
    "ui_partial",
    "cart_update",
    "change_update",
    "progress",
    "turn_complete",
    "error",
]


class AgentEvent(BaseModel):
    type: EventType
    data: dict[str, Any] = Field(default_factory=dict)

    @classmethod
    def text_delta(cls, text: str) -> AgentEvent:
        return cls(type="text_delta", data={"text": text})

    @classmethod
    def tool_call(
        cls, tool: str, tool_use_id: str, input_data: dict[str, Any], label: str | None = None
    ) -> AgentEvent:
        data: dict[str, Any] = {"tool": tool, "id": tool_use_id, "input": input_data}
        if label:
            data["label"] = label
        return cls(type="tool_call", data=data)

    @classmethod
    def tool_result(
        cls,
        tool: str,
        tool_use_id: str,
        summary: str,
        is_error: bool = False,
        status: str | None = None,
        reason: str | None = None,
        excerpt: str | None = None,
        evidence: list[dict[str, Any]] | None = None,
        no_match: bool = False,
    ) -> AgentEvent:
        data: dict[str, Any] = {
            "tool": tool,
            "id": tool_use_id,
            "summary": summary,
            "is_error": is_error,
            "status": status or ("error" if is_error else "ok"),
        }
        if reason:
            data["reason"] = reason
        if excerpt is not None:
            data["excerpt"] = excerpt
        if evidence:
            data["evidence"] = evidence
        if no_match:
            data["no_match"] = True
        return cls(type="tool_result", data=data)

    @classmethod
    def ui(cls, component: str, payload: dict[str, Any]) -> AgentEvent:
        return cls(type="ui", data={"component": component, "payload": payload})

    @classmethod
    def ui_partial(cls, component: str, payload: dict[str, Any], stream_id: str) -> AgentEvent:
        return cls(
            type="ui_partial",
            data={"component": component, "payload": payload, "stream_id": stream_id},
        )

    @classmethod
    def cart_update(cls, cart: dict[str, Any]) -> AgentEvent:
        return cls(type="cart_update", data={"cart": cart})

    @classmethod
    def change_update(cls, change: dict[str, Any]) -> AgentEvent:
        return cls(type="change_update", data={"change": change})

    @classmethod
    def progress(cls, message: str, tool: str | None = None, step: int | None = None) -> AgentEvent:
        data: dict[str, Any] = {"message": message}
        if tool:
            data["tool"] = tool
        if step is not None:
            data["step"] = step
        return cls(type="progress", data=data)

    @classmethod
    def turn_complete(
        cls, stop_reason: str | None, usage: dict[str, int], elapsed_ms: int, results_cleared: int
    ) -> AgentEvent:
        return cls(
            type="turn_complete",
            data={
                "stop_reason": stop_reason,
                "usage": usage,
                "elapsed_ms": elapsed_ms,
                "results_cleared": results_cleared,
            },
        )

    @classmethod
    def error(cls, message: str) -> AgentEvent:
        return cls(type="error", data={"message": message})


@dataclass
class ToolOutcome:
    """One tool call's product: ``result_text`` for the model, ``events`` for the host.
    ``blocked`` names the gate that held the call; ``is_error`` marks a failure;
    ``evidence`` names the versioned sources a read rested on, and ``no_match`` marks a
    read that found nothing, both for the host's trace."""

    result_text: str
    events: list[AgentEvent] = field(default_factory=list)
    is_error: bool = False
    blocked: str | None = None
    evidence: list[dict[str, Any]] = field(default_factory=list)
    no_match: bool = False

    @classmethod
    def error(cls, text: str) -> ToolOutcome:
        return cls(text, is_error=True)

    @classmethod
    def held(cls, gate: str, text: str) -> ToolOutcome:
        return cls(text, blocked=gate)

    @property
    def refused(self) -> bool:
        return self.is_error or self.blocked is not None


def to_sse(event: AgentEvent) -> str:
    """One Server-Sent Events frame: ``event:`` is the ``AgentEvent.type``, ``data:`` its JSON
    payload on one line, then a blank line. ``examples/web-shared/protocol.ts`` reads it."""
    return f"event: {event.type}\ndata: {json.dumps(event.data, ensure_ascii=False)}\n\n"


def _before_open_string(text: str, opened: int) -> str:
    """``text`` cut back to before the string that opens at ``opened``: over the key and
    colon when the string is a value, and over the comma that introduced it."""
    head = text[:opened].rstrip()
    if head.endswith(":"):
        head = head[:-1].rstrip()
        if head.endswith('"'):
            index = len(head) - 2
            while index > 0 and not (head[index] == '"' and head[index - 1] != "\\"):
                index -= 1
            head = head[:index].rstrip()
    if head.endswith(","):
        head = head[:-1]
    return head


def parse_partial_json(buffer: str, *, settle_strings: bool = True) -> dict[str, Any] | None:
    """The object a still-arriving tool input describes so far, or None. Open arrays and
    objects are closed; a dangling comma or colon is dropped and closing tried again. A
    string still being written is left out together with its key (or its array slot), so
    a title, a label, or an id appears only once complete; with ``settle_strings=False``
    it is closed where it stands instead, so text grows as it generates."""
    text = buffer.strip()
    if not text.startswith("{"):
        return None
    try:
        return json.loads(text)
    except (ValueError, TypeError):
        pass

    def closers_for(source: str) -> tuple[str, bool, int]:
        stack: list[str] = []
        in_string = escape = False
        opened = -1
        for index, char in enumerate(source):
            if escape:
                escape = False
                continue
            if in_string:
                if char == "\\":
                    escape = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                opened = index
            elif char in "{[":
                stack.append(char)
            elif char in "}]" and stack:
                stack.pop()
        closing = "".join("}" if open_ != "[" else "]" for open_ in reversed(stack))
        return closing, in_string, opened

    candidates: list[str] = []
    closing, in_string, opened = closers_for(text)
    if in_string and settle_strings:
        text = _before_open_string(text, opened)
        closing, in_string, opened = closers_for(text)
    candidates.append(text + ('"' if in_string else "") + closing)
    trimmed = text.rstrip()
    while trimmed and trimmed[-1] in ",:":
        trimmed = trimmed[:-1].rstrip()
    if trimmed != text:
        closing, in_string, opened = closers_for(trimmed)
        candidates.append(trimmed + ('"' if in_string else "") + closing)
    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
        except (ValueError, TypeError):
            continue
        if isinstance(parsed, dict):
            return parsed
    return None
