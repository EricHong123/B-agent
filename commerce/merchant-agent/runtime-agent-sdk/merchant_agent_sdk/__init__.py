# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The merchant agent on the Claude Agent SDK::

from claude_agent_sdk import ClaudeSDKClient
from merchant_agent_sdk import make_options, run_turn

options, toolset = make_options()
async with ClaudeSDKClient(options=options) as client:
    result = await run_turn(client, "How did the store do last week?", toolset=toolset)
    print(result.text)
    for event in result.ui:
        print(event["component"], event["payload"])
"""

from ._paths import REPO_ROOT, RUNTIME_ROOT, SKILLS_DIR
from .agent import (
    ANALYSIS_AGENT_ADAPTER,
    ANALYSIS_AGENT_NAME,
    build_analysis_agent,
    build_system_prompt,
    default_config,
    ground_message,
    load_skill_registry,
    make_options,
    run_turn,
)
from .merchant_tools import (
    SERVER_NAME,
    MerchantToolset,
    allowed_tool_names,
    build_merchant_sdk_tools,
    build_merchant_server,
    load_mock_backend,
    mcp_tool_name,
    tool_contracts,
    tool_names,
)

__all__ = [
    "ANALYSIS_AGENT_ADAPTER",
    "ANALYSIS_AGENT_NAME",
    "REPO_ROOT",
    "RUNTIME_ROOT",
    "SERVER_NAME",
    "SKILLS_DIR",
    "MerchantToolset",
    "allowed_tool_names",
    "build_analysis_agent",
    "build_merchant_sdk_tools",
    "build_merchant_server",
    "build_system_prompt",
    "default_config",
    "ground_message",
    "load_mock_backend",
    "load_skill_registry",
    "make_options",
    "mcp_tool_name",
    "run_turn",
    "tool_contracts",
    "tool_names",
]
