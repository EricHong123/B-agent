# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The shopping tools as an in-process MCP server for the Agent SDK: the registry's
contracts minus ``load_skill`` (the SDK's Skill tool replaces it), every call executed
by ``ShoppingToolExecutor``, and presentation payloads buffered on the toolset for the
host to render after the turn.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import McpSdkServerConfig, SdkMcpTool, create_sdk_mcp_server

from commerce_common.agent_sdk import BaseToolset, build_sdk_tools
from commerce_common.execution import LOAD_SKILL, contracts_by_name
from commerce_common.skills import SkillRegistry
from shopping_agent import (
    ShoppingAgentConfig,
    ShoppingSessionContext,
    ShoppingSessionState,
    StorefrontBackend,
)
from shopping_agent.executor import ShoppingToolExecutor, build_memory
from shopping_agent.tools.registry import INLINE_CONTEXT_DESCRIPTIONS, build_tools

from ._paths import REPO_ROOT

SERVER_NAME = "storefront"
SERVER_VERSION = "0.1.0"


def tool_contracts(config: ShoppingAgentConfig) -> dict[str, Any]:
    """The registry's contracts for this deployment, by name, with the descriptions that
    stand in for the absent Session context block."""
    contracts = contracts_by_name(build_tools(config, skill_names=[]))
    for name, description in INLINE_CONTEXT_DESCRIPTIONS.items():
        if name in contracts:
            contracts[name] = {**contracts[name], "description": description}
    return contracts


def tool_names(config: ShoppingAgentConfig) -> list[str]:
    """What this deployment registers, in registry order."""
    return [name for name in tool_contracts(config) if name != LOAD_SKILL]


def mcp_tool_name(tool_name: str) -> str:
    return f"mcp__{SERVER_NAME}__{tool_name}"


def allowed_tool_names(config: ShoppingAgentConfig) -> list[str]:
    """The allow-list entries for the registered tools; under ``permission_mode
    "dontAsk"`` an unlisted tool is refused on every call."""
    return [mcp_tool_name(name) for name in tool_names(config)]


@dataclass(kw_only=True)
class ShoppingToolset(BaseToolset):
    backend: StorefrontBackend
    config: ShoppingAgentConfig = field(default_factory=ShoppingAgentConfig)
    session: ShoppingSessionContext = field(
        default_factory=lambda: ShoppingSessionContext(session_id="local", user_id="demo-user")
    )
    state: ShoppingSessionState = field(default_factory=ShoppingSessionState)
    executor_class: type[ShoppingToolExecutor] = ShoppingToolExecutor

    def __post_init__(self) -> None:
        self.attach_memory(build_memory(self.config, self.memory_store, self.memory_write_filter))
        self.executor = self.executor_class(
            backend=self.backend,
            config=self.config,
            skills=SkillRegistry([]),
            session=self.session,
            state=self.state,
            memory=self.memory,
            inline_context=True,
        )


def load_mock_backend() -> StorefrontBackend:
    """The retail example's mock storefront; ``examples/`` is not a package, so it goes
    on ``sys.path`` first. Replace it with your own ``StorefrontBackend``."""
    examples_dir = REPO_ROOT / "examples"
    if str(examples_dir) not in sys.path:
        sys.path.insert(0, str(examples_dir))
    from retail.api.mock_retail import MockRetail

    return MockRetail()


def build_shopping_sdk_tools(toolset: ShoppingToolset) -> list[SdkMcpTool[Any]]:
    return build_sdk_tools(toolset, tool_contracts(toolset.config), tool_names(toolset.config))


def build_shopping_server(toolset: ShoppingToolset) -> McpSdkServerConfig:
    return create_sdk_mcp_server(
        name=SERVER_NAME, version=SERVER_VERSION, tools=build_shopping_sdk_tools(toolset)
    )
