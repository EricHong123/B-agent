# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Both roles' prompt bytes, tool registries, presentation components, and extraction prompts."""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any

import pytest
from pydantic import BaseModel

from commerce_common.execution import LOAD_SKILL, STATUS_FIELD, STATUS_MAX_CHARS
from commerce_common.presentation import PresentationExtension, PresentationPayload
from commerce_common.prompt_assembly import with_tool_cache_control
from merchant_agent import enrichment as merchant_enrichment
from merchant_agent import prompt as merchant_prompt
from merchant_agent.memory import MERCHANT_MEMORY_EXTRACTION_PROMPT
from merchant_agent.tools import registry as merchant_registry
from shopping_agent import enrichment as shopping_enrichment
from shopping_agent import prompt as shopping_prompt
from shopping_agent.memory import SHOPPING_MEMORY_EXTRACTION_PROMPT
from shopping_agent.tools import registry as shopping_registry


@dataclass(frozen=True)
class Prompting:
    static_system: Any
    build_tools: Any
    loop_settings: tuple[str, ...]  # settings the turn loop reads and the prompt never renders
    builtin: str  # a built-in presentation tool an extension may not shadow
    components: dict[str, Any]
    everything_on: dict[str, Any]  # the settings that register every optional tool
    extraction_prompt: str
    speaker: str
    standing_key: str  # the key the prompt reserves for what the speaker is working toward


ROLES = {
    "shopping": Prompting(
        shopping_prompt.build_static_system,
        shopping_registry.build_tools,
        (
            "policy_grounding_gate",
            "policy_intent_terms",
            "order_grounding_gate",
            "catalog_grounding_gate",
            "product_id_patterns",
            "max_quantity_per_item",
            "max_cart_lines",
        ),
        "present_products",
        shopping_enrichment.PRESENTATION_COMPONENTS,
        {"enable_disclosures": True},
        SHOPPING_MEMORY_EXTRACTION_PROMPT,
        "customer",
        "current_project",
    ),
    "merchant": Prompting(
        merchant_prompt.build_static_system,
        merchant_registry.build_tools,
        (
            "metrics_grounding_gate",
            "metrics_intent_terms",
            "queue_grounding_gate",
            "staging_followthrough_gate",
            "max_price_delta_pct",
            "protected_fields",
        ),
        "present_digest",
        merchant_enrichment.PRESENTATION_COMPONENTS,
        {},
        MERCHANT_MEMORY_EXTRACTION_PROMPT,
        "operator",
        "current_goal",
    ),
}

SILENT_SETTINGS: dict[str, Any] = {
    "enable_memory": False,
    "memory_blocked_patterns": (r"(?i)\ballerg",),
    "memory_retention_days": 30,
    "eager_tool_dispatch": False,
    "rolling_conversation_cache": False,
    "eager_partial_frames": True,
    "close_on_presentation": False,
    "compact_history_above_tokens": 0,
    "thinking_effort": "medium",
    "policy_grounding_gate": False,
    "policy_intent_terms": ("overage", "roaming"),
    "order_grounding_gate": False,
    "catalog_grounding_gate": False,
    "product_id_patterns": (),
    "max_quantity_per_item": 3,
    "max_cart_lines": 5,
    "metrics_grounding_gate": False,
    "metrics_intent_terms": ("occupancy", "pacing"),
    "queue_grounding_gate": False,
    "staging_followthrough_gate": False,
    "max_price_delta_pct": 1.0,
    "protected_fields": ("listing_id", "currency", "cost"),
}


class TitleOnly(BaseModel):
    title: str


def extension(name: str, component: str = "calendar") -> PresentationExtension:
    return PresentationExtension(
        name=name,
        component=component,
        description="A deployment's own component.",
        input_schema={"type": "object", "properties": {"title": {"type": "string"}}},
        payload_model=TitleOnly,
    )


@pytest.fixture(params=list(ROLES))
def role(request) -> str:
    return request.param


@pytest.fixture
def prompting(role) -> Prompting:
    return ROLES[role]


def _bytes(prompting: Prompting, config: Any, skills: Any) -> tuple[str, str]:
    tools = prompting.build_tools(config, skills.names)
    return prompting.static_system(config, skills), json.dumps(tools, sort_keys=True)


def test_prompt_and_tools_rebuild_to_the_same_bytes_and_cache_mark_the_last_tool(
    prompting, config, skills
):
    assert _bytes(prompting, config, skills) == _bytes(prompting, config, skills)
    tools = prompting.build_tools(config, skills.names)
    marked = with_tool_cache_control(tools)
    assert "cache_control" in marked[-1] and not any(
        "cache_control" in tool for tool in marked[:-1]
    )
    assert "cache_control" not in tools[-1]


def test_loop_and_memory_settings_leave_the_bytes_unchanged(prompting, config, skills):
    baseline = _bytes(prompting, config, skills)
    silent = (
        "enable_memory",
        "memory_blocked_patterns",
        "memory_retention_days",
        "eager_tool_dispatch",
        "rolling_conversation_cache",
        "eager_partial_frames",
        "close_on_presentation",
        "compact_history_above_tokens",
        *prompting.loop_settings,
    )
    for name in silent:
        variant = config.model_copy(update={name: SILENT_SETTINGS[name]})
        assert _bytes(prompting, variant, skills) == baseline, name
    disabled = config.model_copy(update={"enable_memory": False})
    names = {tool["name"] for tool in prompting.build_tools(disabled, skills.names)}
    assert {"save_memory", "recall_memories"} <= names


def test_builtins_open_with_load_skill_and_close_with_the_presentation_tools(
    prompting, config, skills
):
    names = [tool["name"] for tool in prompting.build_tools(config, skills.names)]
    assert names[0] == LOAD_SKILL and len(names) == len(set(names))
    presentation = [name for name in names if name in prompting.components]
    assert presentation and names[-len(presentation) :] == presentation
    assert {"save_memory", "recall_memories"} <= set(names)


def test_extensions_append_after_the_builtins_and_may_not_shadow_one(prompting, config, skills):
    added = extension("present_calendar")
    first = prompting.build_tools(config, skills.names, [added])
    assert first == prompting.build_tools(config, skills.names, [added])
    base = prompting.build_tools(config, skills.names)
    assert [tool["name"] for tool in first] == [tool["name"] for tool in base] + [
        "present_calendar"
    ]
    with pytest.raises(ValueError, match="collides"):
        prompting.build_tools(config, skills.names, [extension(prompting.builtin)])


def test_every_present_tool_has_a_component_with_a_presentation_payload(prompting, config, skills):
    everything = config.model_copy(update=prompting.everything_on)
    tools = prompting.build_tools(everything, skills.names)
    names = {t["name"] for t in tools}
    assert (
        {name for name in names if name.startswith("present_")}
        <= set(prompting.components)
        <= names
    )
    for name, component in prompting.components.items():
        assert issubclass(component.payload_model, PresentationPayload), name


def test_every_tool_but_the_presentation_tools_takes_the_status_line_first(
    prompting, config, skills
):
    everything = config.model_copy(update=prompting.everything_on | {"enable_analysis": True})
    tools = prompting.build_tools(everything, skills.names, [extension("present_calendar")])
    presenting = {*prompting.components, "present_calendar"}
    with_status = [tool for tool in tools if tool["name"] not in presenting]
    assert LOAD_SKILL in {tool["name"] for tool in with_status}
    for tool in tools:
        schema = tool["input_schema"]
        if tool["name"] in presenting:
            assert STATUS_FIELD not in schema["properties"], tool["name"]
            continue
        assert next(iter(schema["properties"])) == STATUS_FIELD, tool["name"]
        assert STATUS_FIELD not in schema.get("required", []), tool["name"]
        status = schema["properties"][STATUS_FIELD]
        assert status["type"] == "string" and status["maxLength"] == STATUS_MAX_CHARS
        assert f"the {prompting.speaker} sees" in status["description"]


def test_the_extraction_prompt_is_the_template_rendered_for_the_roles_speaker(prompting):
    assert "{" not in prompting.extraction_prompt
    assert f"only what the {prompting.speaker} said" in prompting.extraction_prompt
    assert f'under the key "{prompting.standing_key}"' in prompting.extraction_prompt
