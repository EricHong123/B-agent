# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Presentation tools: the component spec the built-ins and deployment extensions share,
and the one runner that validates a call, enriches it, and produces its ``ui`` event.
The model selects and annotates; every fact on the component is joined server-side.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .fencing import sanitize_suggestion_chips
from .streaming import AgentEvent, ToolOutcome

# The one component that carries the turn's chips, on both roles.
CHIPS_TOOL = "present_suggestions"
CHIPS_COMPONENT = "suggestions"


class PresentationRefused(ValueError):
    """Raised by an enrich hook when the call cannot render. ``gate`` names the gate that
    held it (the result is then a held call); without a gate the result is an error."""

    def __init__(self, message: str, gate: str | None = None) -> None:
        super().__init__(message)
        self.gate = gate


class PresentationPayload(BaseModel):
    """Base of the built-in payloads. Undeclared keys are dropped, not rejected: the
    tool's input schema is what constrains the model, and a stray key (a ``status`` line
    sent to a presentation tool) is not worth a rejected card."""

    model_config = ConfigDict(extra="ignore")


class PresentSuggestionsPayload(PresentationPayload):
    """The turn's chips, the one component that carries them; sanitized here because the
    tool schemas are cache-frozen, and it fails when every chip sanitizes away, since the
    chips are its whole content."""

    suggestions: list[str] = Field(min_length=1, max_length=4)

    @field_validator("suggestions", mode="after")
    @classmethod
    def _sanitize_suggestions(cls, chips: list[str]) -> list[str]:
        return sanitize_suggestion_chips(chips)

    @model_validator(mode="after")
    def _require_a_visible_chip(self) -> PresentSuggestionsPayload:
        if not self.suggestions:
            raise ValueError(
                "every suggestion was empty after sanitization — send 1-4 short, "
                "plain-text suggestions."
            )
        return self


@dataclass(frozen=True)
class EnrichmentContext:
    """What an enrich hook works with. A hook appends to ``notes`` anything the model
    should hear about the call (ids it dropped, text it removed)."""

    backend: Any
    config: Any
    session: Any
    state: Any
    notes: list[str] = field(default_factory=list)


EnrichFn = Callable[[Any, EnrichmentContext], Awaitable[dict[str, Any]]]
# Runs on every structural change of a still-streaming call: synchronous, cheap, and
# provenance-only. Gets the tolerantly parsed prefix and the session state; returns the
# partial payload, or None while nothing is renderable.
PartialEnrichFn = Callable[[dict[str, Any], Any], "dict[str, Any] | None"]


@dataclass(frozen=True, kw_only=True)
class PresentationComponent:
    """One presentation tool: the ``component`` the host renders, the ``payload_model``
    that validates the model's arguments, and the hooks that join server data onto it.
    Without ``enrich`` the validated payload renders as sent."""

    name: str
    component: str
    payload_model: type[BaseModel]
    enrich: EnrichFn | None = None
    enrich_partial: PartialEnrichFn | None = None


@dataclass(frozen=True, kw_only=True)
class PresentationExtension(PresentationComponent):
    """A deployment-supplied component, merged into the tool surface at construction.
    ``input_schema`` is what the model sees and must describe the shape ``payload_model``
    validates. An enrich hook refuses by raising :class:`PresentationRefused` (or any
    ``ValueError``); its message goes back to the model."""

    description: str
    input_schema: dict[str, Any]

    def tool_definition(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


def invalid_payload_prefix(tool_name: str) -> str:
    """How a payload that failed validation is reported to the model; the validator's
    message follows it."""
    return f"Invalid {tool_name} payload:"


async def run_presentation(
    spec: PresentationComponent,
    tool_input: dict[str, Any],
    context: EnrichmentContext,
    displayed_text: str,
) -> ToolOutcome:
    """Validate, enrich, and emit one component. The result text is ``displayed_text``
    plus the hook's notes; the ``ui`` event carries the enriched payload."""
    try:
        payload = spec.payload_model.model_validate(tool_input)
    except ValueError as exc:
        return ToolOutcome.error(f"{invalid_payload_prefix(spec.name)} {exc}")
    if spec.enrich is None:
        enriched = payload.model_dump(exclude_none=True)
    else:
        try:
            enriched = await spec.enrich(payload, context)
        except PresentationRefused as refused:
            if refused.gate is None:
                return ToolOutcome.error(str(refused))
            return ToolOutcome.held(refused.gate, str(refused))
        except ValueError as exc:
            return ToolOutcome.error(str(exc))
    text = " ".join([displayed_text, *context.notes])
    return ToolOutcome(text, events=[AgentEvent.ui(spec.component, enriched)])


def partial_signature(payload: dict[str, Any]) -> Any:
    """What counts as a visible change while a component streams: a title appearing,
    and the length of every list on the payload, or of each entry's ``products`` list
    when the entries carry one."""
    lists = {}
    for key, value in payload.items():
        if not isinstance(value, list):
            continue
        if value and all(isinstance(item, dict) and "products" in item for item in value):
            lists[key] = [len(item.get("products") or []) for item in value]
        else:
            lists[key] = len(value)
    return (bool(payload.get("title")), lists)


def partial_ui_tool_names(
    components: Mapping[str, PresentationComponent], extensions: Sequence[PresentationExtension]
) -> frozenset[str]:
    """The tools whose calls the orchestrator renders progressively."""
    specs = [*components.values(), *extensions]
    return frozenset(spec.name for spec in specs if spec.enrich_partial is not None)


def enrich_partial(
    spec: PresentationComponent, data: dict[str, Any], state: Any
) -> tuple[str, dict[str, Any], Any] | None:
    """A still-streaming call's partial payload with its change signature, or None. A
    payload with no title whose lists are all still empty is not a frame yet."""
    if spec.enrich_partial is None:
        return None
    payload = spec.enrich_partial(data, state)
    if payload is None:
        return None
    has_title, lists = signature = partial_signature(payload)
    if not has_title and lists and not any(lists.values()):
        return None
    return spec.component, payload, signature
