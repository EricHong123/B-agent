# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The merchant tools as an in-process MCP server for the Agent SDK: the registry's
contracts minus ``load_skill`` and ``run_analysis`` (the SDK's Skill tool and a subagent
take those roles), every call executed by ``MerchantToolExecutor``, and presentation
payloads buffered on the toolset for the host to render after the turn. The toolset is
also the host's approval surface: ``host_approve`` marks a change for ``apply_change``;
``host_clear`` clears the mark once the apply turn returns.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field
from typing import Any

from claude_agent_sdk import McpSdkServerConfig, SdkMcpTool, create_sdk_mcp_server

from commerce_common.agent_sdk import BaseToolset, build_sdk_tools
from commerce_common.execution import LOAD_SKILL, contracts_by_name
from commerce_common.skills import SkillRegistry
from merchant_agent import (
    ChangeStatus,
    MerchantAgentConfig,
    MerchantBackend,
    MerchantSessionContext,
    MerchantSessionState,
    StagedChange,
)
from merchant_agent.analysis import ANALYSIS_TOOL
from merchant_agent.executor import MerchantToolExecutor, build_memory
from merchant_agent.tools.registry import INLINE_CONTEXT_DESCRIPTIONS, build_tools

from ._paths import REPO_ROOT

SERVER_NAME = "merchant"
SERVER_VERSION = "0.1.0"
_NOT_REGISTERED = {LOAD_SKILL, ANALYSIS_TOOL}


def tool_contracts(config: MerchantAgentConfig) -> dict[str, Any]:
    """The registry's contracts for this deployment, by name, with the descriptions that
    stand in for the absent Session context block."""
    contracts = contracts_by_name(build_tools(config, skill_names=[]))
    for name, description in INLINE_CONTEXT_DESCRIPTIONS.items():
        if name in contracts:
            contracts[name] = {**contracts[name], "description": description}
    return contracts


def tool_names(config: MerchantAgentConfig) -> list[str]:
    """What this deployment registers, in registry order."""
    return [name for name in tool_contracts(config) if name not in _NOT_REGISTERED]


def mcp_tool_name(tool_name: str) -> str:
    return f"mcp__{SERVER_NAME}__{tool_name}"


def allowed_tool_names(config: MerchantAgentConfig) -> list[str]:
    """The allow-list entries for the registered tools; under ``permission_mode
    "dontAsk"`` an unlisted tool is refused on every call."""
    return [mcp_tool_name(name) for name in tool_names(config)]


@dataclass(kw_only=True)
class MerchantToolset(BaseToolset):
    backend: MerchantBackend
    config: MerchantAgentConfig = field(default_factory=MerchantAgentConfig)
    session: MerchantSessionContext = field(
        default_factory=lambda: MerchantSessionContext(
            session_id="local", merchant_id="acme-retail", operator="demo-operator"
        )
    )
    state: MerchantSessionState = field(default_factory=MerchantSessionState)
    executor_class: type[MerchantToolExecutor] = MerchantToolExecutor

    def __post_init__(self) -> None:
        self.attach_memory(build_memory(self.config, self.memory_store, self.memory_write_filter))
        self.executor = self.executor_class(
            backend=self.backend,
            config=self.config,
            skills=SkillRegistry([]),
            session=self.session,
            state=self.state,
            memory=self.memory,
        )

    def pending_host_approvals(self) -> list[StagedChange]:
        """Staged changes this conversation knows of that carry no approval mark yet."""
        return [
            change
            for change in self.state.seen_changes.values()
            if change.status is ChangeStatus.STAGED
            and change.change_id not in self.state.approved_change_ids
        ]

    def host_approve(self, change_id: str) -> None:
        """Record the host's verification that the operator approved the change."""
        self.state.approved_change_ids.add(change_id)

    def host_clear(self, change_id: str) -> None:
        """Clear the mark once the apply turn returns, whatever its outcome, so a later turn
        cannot spend it; a change still staged is offered for approval again."""
        self.state.approved_change_ids.discard(change_id)


def load_mock_backend() -> MerchantBackend:
    """The retail example's mock merchant over its mock storefront; ``examples/`` is not
    a package, so it goes on ``sys.path`` first. Replace it with your own backend."""
    examples_dir = REPO_ROOT / "examples"
    if str(examples_dir) not in sys.path:
        sys.path.insert(0, str(examples_dir))
    from retail.api.mock_merchant import MockRetailMerchant
    from retail.api.mock_retail import MockRetail

    return MockRetailMerchant(MockRetail())


def build_merchant_sdk_tools(toolset: MerchantToolset) -> list[SdkMcpTool[Any]]:
    return build_sdk_tools(toolset, tool_contracts(toolset.config), tool_names(toolset.config))


def build_merchant_server(toolset: MerchantToolset) -> McpSdkServerConfig:
    return create_sdk_mcp_server(
        name=SERVER_NAME, version=SERVER_VERSION, tools=build_merchant_sdk_tools(toolset)
    )
