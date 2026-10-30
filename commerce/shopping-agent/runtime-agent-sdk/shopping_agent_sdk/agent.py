# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The shopping agent as ``ClaudeAgentOptions``: the static prompt plus the skill
adapter, the storefront server as the only tools, and the repo skills materialized for
the SDK. ``run_turn`` grounds the message the way the Messages API runtime's forced
first call does, then collects the response and the UI payloads; a hook ends the turn on
the round that carries the chips, as that runtime's loop does."""

from __future__ import annotations

from pathlib import Path

from claude_agent_sdk import ClaudeAgentOptions, ClaudeSDKClient

from commerce_common.agent_sdk import (
    SKILL_TOOL_ADAPTER,
    TurnResult,
    close_on_presentation_hook,
    collect_turn,
    ensure_project_skills,
    ground,
)
from commerce_common.skills import SkillRegistry
from shopping_agent import ShoppingAgentConfig, ShoppingSessionContext, StorefrontBackend
from shopping_agent.grounding import GROUNDING_RULES
from shopping_agent.prompt import build_static_system

from ._paths import RUNTIME_ROOT, SKILLS_DIR
from .shopping_tools import (
    SERVER_NAME,
    ShoppingToolset,
    allowed_tool_names,
    build_shopping_server,
    load_mock_backend,
)


def default_config() -> ShoppingAgentConfig:
    """The demo storefront's identity; a deployment supplies its own config."""
    return ShoppingAgentConfig(
        brand_name="ACME",
        assistant_name="ACME Assistant",
        brand_voice="warm, practical, and plain about trade-offs",
    )


def load_skill_registry(skills_dir: Path | None = None) -> SkillRegistry:
    return SkillRegistry.from_dir(SKILLS_DIR if skills_dir is None else skills_dir)


def build_system_prompt(config: ShoppingAgentConfig, skills: SkillRegistry) -> str:
    return build_static_system(config, skills) + "\n\n" + SKILL_TOOL_ADAPTER


def make_options(
    *,
    backend: StorefrontBackend | None = None,
    config: ShoppingAgentConfig | None = None,
    session_id: str = "local-session",
    user_id: str = "demo-user",
    max_turns: int = 16,
    skills_dir: Path | None = None,
) -> tuple[ClaudeAgentOptions, ShoppingToolset]:
    """The options for one conversation and the toolset behind them; the toolset is
    where the host reads provenance, session state, and the UI payloads. ``skills_dir``
    is the directory whose skills the prompt indexes and the SDK loads; it defaults to
    the repo's ``shopping-agent/skills``."""
    config = config or default_config()
    skills_root = SKILLS_DIR if skills_dir is None else skills_dir
    skills = load_skill_registry(skills_root)
    toolset = ShoppingToolset(
        backend=backend or load_mock_backend(),
        config=config,
        session=ShoppingSessionContext(session_id=session_id, user_id=user_id),
    )
    ensure_project_skills(skills_root, RUNTIME_ROOT)
    options = ClaudeAgentOptions(
        system_prompt=build_system_prompt(config, skills),
        mcp_servers={SERVER_NAME: build_shopping_server(toolset)},
        allowed_tools=allowed_tool_names(config),
        tools=["Skill"],
        skills=skills.names,
        setting_sources=["project"],
        cwd=RUNTIME_ROOT,
        # The project source is on for the skills directory; keep the CLI from also
        # loading any CLAUDE.md above cwd into the agent's context.
        env={"CLAUDE_CODE_DISABLE_CLAUDE_MDS": "1"},
        model=config.model,
        max_turns=max_turns,
        permission_mode="dontAsk",
        hooks=close_on_presentation_hook(toolset, config.close_on_presentation),
    )
    return options, toolset


async def ground_message(text: str, toolset: ShoppingToolset) -> str:
    """The customer's message with the reads the grounding rules call for appended."""
    return await ground(text, GROUNDING_RULES, toolset.config, toolset.state, toolset.executor)


async def run_turn(
    client: ClaudeSDKClient, text: str, *, toolset: ShoppingToolset | None = None
) -> TurnResult:
    """Send one message and collect the reply. With the ``toolset`` from
    :func:`make_options` the message is grounded first and the result carries the
    turn's UI payloads."""
    if toolset is not None:
        toolset.begin_turn()
        text = await ground_message(text, toolset)
    await client.query(text)
    result = await collect_turn(client)
    result.ui = toolset.drain_ui_events() if toolset is not None else []
    return result
