# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The delegate contract: an isolated model call behind a tool. A delegate receives a
task brief and the session handles, never the conversation or the executor, and returns
one schema-validated result; it cannot write, present, or invoke other delegates.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel

from .streaming import AgentEvent


@dataclass(frozen=True)
class DelegationContext:
    """The handles a delegate's ``run`` receives. ``emit_status`` accepts a plain string
    that renders to the human as a progress line and never enters model context; ``usage``
    is the turn's token totals, which the delegate adds each of its model calls to."""

    backend: Any
    config: Any
    session: Any
    state: Any
    emit_status: Callable[[str], None] | None = None
    usage: dict[str, int] | None = None


DelegateFn = Callable[[DelegationContext, "dict[str, Any]"], Awaitable[BaseModel]]
# Turns a validated result into what the model reads (a payload the executor fences)
# and the events the host receives; the default fences the result record itself.
DelegatePresentFn = Callable[[BaseModel, DelegationContext], "tuple[Any, list[AgentEvent]]"]


@dataclass(frozen=True)
class DelegateExtension:
    """A delegate registered on the tool surface. The model sees ``description`` and
    ``input_schema``; the executor validates what ``run`` returns against
    ``result_model``. ``run`` raises ``ValueError`` when it cannot complete, and the
    executor returns the message as a tool error."""

    name: str
    description: str
    input_schema: dict[str, Any]
    result_model: type[BaseModel]
    run: DelegateFn
    present: DelegatePresentFn | None = None

    def tool_definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }
