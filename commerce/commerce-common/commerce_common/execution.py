# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The executor frame both roles extend. A role executor supplies its fence, its handler
table, and its wording; this module owns dispatch, the failure ladder, skills,
presentation, delegates, memory, and the ``status`` line a non-presentation call may
carry for the person waiting, so every tool result is built in one place and the
Messages API runtime, the Agent SDK toolset, and the MCP server all call ``execute``.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from typing import Any, TypeVar

from pydantic import BaseModel, ValidationError

from .delegation import DelegateExtension, DelegationContext
from .fencing import Fence, sanitize_label, truncate_display
from .memory import MemoryRuntime
from .presentation import (
    EnrichmentContext,
    PresentationComponent,
    PresentationExtension,
    run_presentation,
)
from .skills import SkillRegistry
from .streaming import AgentEvent, ToolOutcome

logger = logging.getLogger(__name__)

LOAD_SKILL = "load_skill"

# Every tool that is not a presentation tool takes an optional ``status`` first: a few
# words the person waiting sees while the call runs. It is the model's, so it is
# sanitized like any display string; it never reaches a backend, a gate, memory, or a
# tool result.
STATUS_FIELD = "status"
STATUS_MAX_CHARS = 60

Handler = Callable[[dict[str, Any]], Awaitable[ToolOutcome]]
ArgumentT = TypeVar("ArgumentT", bound=BaseModel)


class InvalidArguments(ValueError):
    """A tool argument failed its schema; ``execute`` answers by naming the fields."""

    def __init__(self, invalid: ValidationError) -> None:
        super().__init__(str(invalid))
        self.invalid = invalid


def parse_argument(model: type[ArgumentT], value: Any) -> ArgumentT:
    """Validate one model-supplied argument. Only a failure raised here is reported as
    bad arguments; a ``ValidationError`` from anywhere else in a handler (a backend
    building its own models) is a backend failure like any other."""
    try:
        return model.model_validate(value)
    except ValidationError as invalid:
        raise InvalidArguments(invalid) from invalid


def clamp_limit(raw: Any, default: int, ceiling: int) -> int:
    """A model-supplied count clamped to ``1..ceiling``; missing or zero means ``default``."""
    return max(1, min(int(raw or default), ceiling))


def with_status(tool: dict[str, Any], reader: str) -> dict[str, Any]:
    """``tool`` with ``status`` as its first property, optional; ``reader`` is who sees
    the line ("the customer", "the operator")."""
    schema = dict(tool["input_schema"])
    status = {
        "type": "string",
        "maxLength": STATUS_MAX_CHARS,
        "description": f"A few plain words {reader} sees while this runs, saying what you "
        "are doing for them; no tool or system names.",
    }
    schema["properties"] = {STATUS_FIELD: status, **schema.get("properties", {})}
    return {**tool, "input_schema": schema}


def without_status(tool: Mapping[str, Any]) -> dict[str, Any]:
    """``tool`` with the ``status`` property left out, for a caller whose line nobody
    sees (the analysis delegate's reads, the MCP servers)."""
    schema = dict(tool["input_schema"])
    schema["properties"] = {
        key: value for key, value in schema.get("properties", {}).items() if key != STATUS_FIELD
    }
    return {**tool, "input_schema": schema}


def contracts_by_name(tools: Sequence[Mapping[str, Any]]) -> dict[str, Mapping[str, Any]]:
    """The registry's client tools indexed by name (server tools carry no input schema)."""
    return {str(tool["name"]): tool for tool in tools if "input_schema" in tool}


def invalid_arguments_text(name: str, invalid: ValidationError) -> str:
    issues = "; ".join(
        f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
        for error in invalid.errors()
    )
    return f"{name} arguments were invalid — {issues}. Adjust and call it again."


class BaseToolExecutor:
    """One session's tools. Subclasses set the class attributes and implement
    :meth:`handlers` and :attr:`memory_subject`; ``execute`` never raises."""

    fence: Fence
    components: Mapping[str, PresentationComponent]
    displayed_text: str
    unavailable_text: str  # formatted with {name}
    # A tool the config switches off: the system does not exist here, which is not an outage.
    absent_text: str = "{name} is not something offered here; say so plainly and do not suggest it."
    # Delegates: the per-turn cap comes from the role config's max_delegate_calls_per_turn.
    delegate_repeat_text: str = "{name} already ran {count} times this turn; reuse its result."
    progress_max_chars: int = 140

    def __init__(
        self,
        *,
        backend: Any,
        config: Any,
        skills: SkillRegistry,
        session: Any,
        state: Any,
        memory: MemoryRuntime,
        extensions: Sequence[PresentationExtension] = (),
        delegates: Sequence[DelegateExtension] = (),
        progress: Callable[[AgentEvent], None] | None = None,
        usage: dict[str, int] | None = None,
    ) -> None:
        self._backend = backend
        self._config = config
        self._absent = config.absent_tools()
        self._skills = skills
        self._session = session
        self._state = state
        self._memory = memory
        self._extensions = {extension.name: extension for extension in extensions}
        self._delegates = {delegate.name: delegate for delegate in delegates}
        self._progress = progress
        self._usage = usage
        self._delegate_calls = 0
        self._handlers: dict[str, Handler] = {
            **self.handlers(),
            "save_memory": self._save_memory,
            "recall_memories": self._recall_memories,
        }

    # -- role hooks -------------------------------------------------------------

    def handlers(self) -> dict[str, Handler]:
        raise NotImplementedError

    @property
    def memory_subject(self) -> str:
        raise NotImplementedError

    def domain_error(self, error: Exception) -> ToolOutcome | None:
        """A role's own exception classes mapped to outcomes; None for the generic ladder."""
        return None

    # -- helpers for handlers -----------------------------------------------------

    def _sanitize(self, value: Any, max_chars: int | None) -> str:
        return self.fence.sanitize_text(str(value or ""), max_chars)

    def _fenced(self, payload: Any, events: Sequence[AgentEvent] = ()) -> ToolOutcome:
        return ToolOutcome(
            self.fence.fence_payload(payload, self._config.max_fenced_chars), list(events)
        )

    def _search_limit(self, raw: Any) -> int:
        return clamp_limit(raw, self._config.max_search_results, self._config.max_search_results)

    # -- dispatch --------------------------------------------------------------------

    def presents(self, name: str) -> bool:
        """True when ``name`` is a presentation tool, built-in or extension."""
        return name in self.components or name in self._extensions

    def split_status(
        self, name: str, tool_input: dict[str, Any]
    ) -> tuple[dict[str, Any], str | None]:
        """The call's arguments without the ``status`` line, and that line sanitized for
        the host (None on a presentation tool and on a call without the field)."""
        if self.presents(name) or STATUS_FIELD not in tool_input:
            return tool_input, None
        arguments = {key: value for key, value in tool_input.items() if key != STATUS_FIELD}
        # Fence markers out like any model string, then one-line label hygiene and the cap.
        status = sanitize_label(self._sanitize(tool_input[STATUS_FIELD], None), STATUS_MAX_CHARS)
        return arguments, status or None

    def tool_call_event(
        self, name: str, tool_use_id: str, tool_input: dict[str, Any]
    ) -> AgentEvent:
        """The ``tool_call`` event for the host: the arguments the tool will get, and the
        status line beside them as its ``label``."""
        arguments, status = self.split_status(name, tool_input)
        return AgentEvent.tool_call(name, tool_use_id, arguments, label=status)

    def ends_clean(self, name: str, outcome: ToolOutcome) -> bool:
        """True when a call may sit in the round that ends the turn without a closing
        model call: a presentation call that rendered and left the model nothing to
        answer (not refused or held, no note appended to its result)."""
        return (
            self.presents(name)
            and not outcome.refused
            and outcome.result_text == self.displayed_text
        )

    async def execute(self, name: str, tool_input: dict[str, Any] | None) -> ToolOutcome:
        try:
            return await self.dispatch(name, dict(tool_input or {}))
        except InvalidArguments as invalid:
            return ToolOutcome.error(invalid_arguments_text(name, invalid.invalid))
        except Exception as error:  # a tool failure must not end the turn
            if (outcome := self.domain_error(error)) is not None:
                return outcome
            logger.warning("tool %s failed and is reported as unavailable", name, exc_info=True)
            return ToolOutcome.error(self.unavailable_text.format(name=name))

    async def dispatch(self, name: str, tool_input: dict[str, Any]) -> ToolOutcome:
        """:meth:`execute` without the failure ladder: what the tool raised propagates,
        so a host prefetching a read can tell a failed tool from a result the tool wrote
        (a not-found line, a held call). The ``status`` line is dropped here, before any
        argument is validated or any handler runs; a tool the deployment's config leaves
        out of the tool list is unknown here too, whichever path calls it."""
        tool_input, _status = self.split_status(name, tool_input)
        if name in self._absent:
            return ToolOutcome.error(self.absent_text.format(name=name))
        if name == LOAD_SKILL:
            return self._load_skill(tool_input)
        if (spec := self.components.get(name) or self._extensions.get(name)) is not None:
            return await self._present(spec, tool_input)
        if (delegate := self._delegates.get(name)) is not None:
            return await self._run_delegate(delegate, tool_input)
        handler = self._handlers.get(name)
        if handler is None:
            return ToolOutcome.error(f"Unknown tool: {name}")
        return await handler(tool_input)

    def _load_skill(self, tool_input: dict[str, Any]) -> ToolOutcome:
        skill_name = str(tool_input.get("skill_name", ""))
        body = self._skills.get_instructions(skill_name)
        if body is None:
            return ToolOutcome.error(
                f"No skill named '{skill_name}'. Available: {', '.join(self._skills.names)}"
            )
        return ToolOutcome(body)

    async def _present(
        self, spec: PresentationComponent, tool_input: dict[str, Any]
    ) -> ToolOutcome:
        context = EnrichmentContext(
            backend=self._backend, config=self._config, session=self._session, state=self._state
        )
        return await run_presentation(spec, tool_input, context, self.displayed_text)

    async def _save_memory(self, tool_input: dict[str, Any]) -> ToolOutcome:
        return await self._memory.save(self.memory_subject, self._session.session_id, tool_input)

    async def _recall_memories(self, tool_input: dict[str, Any]) -> ToolOutcome:
        return await self._memory.recall(self.memory_subject, tool_input)

    async def _run_delegate(
        self, delegate: DelegateExtension, tool_input: dict[str, Any]
    ) -> ToolOutcome:
        # Counted before the first await so parallel calls in one gather count deterministically.
        if self._delegate_calls >= self._config.max_delegate_calls_per_turn:
            return ToolOutcome.error(
                self.delegate_repeat_text.format(name=delegate.name, count=self._delegate_calls)
            )
        self._delegate_calls += 1

        def emit_status(message: str) -> None:
            if self._progress is None:
                return
            text = truncate_display(str(message), self.progress_max_chars).strip()
            if text:
                self._progress(AgentEvent.progress(text, tool=delegate.name))

        # The one opener every delegate gets; delegates themselves narrate their steps.
        emit_status("starting")
        context = DelegationContext(
            backend=self._backend,
            config=self._config,
            session=self._session,
            state=self._state,
            emit_status=emit_status,
            usage=self._usage,
        )
        try:
            raw = await delegate.run(context, tool_input)
            result = (
                raw
                if isinstance(raw, delegate.result_model)
                else delegate.result_model.model_validate(raw)
            )
        except ValueError as failed:  # includes a ValidationError on the result
            return ToolOutcome.error(
                f"{delegate.name} could not complete: {truncate_display(str(failed), 400)}"
            )
        if delegate.present is None:
            return self._fenced(result.model_dump(mode="json", exclude_none=True))
        payload, events = delegate.present(result, context)
        return self._fenced(payload, events)
