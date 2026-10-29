# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The shopping agent on the Claude Agent SDK::

from claude_agent_sdk import ClaudeSDKClient
from shopping_agent_sdk import make_options, run_turn

options, toolset = make_options()
async with ClaudeSDKClient(options=options) as client:
    result = await run_turn(client, "I need a tent for two people", toolset=toolset)
    print(result.text)
    for event in result.ui:
        print(event["component"], event["payload"])
"""

from ._paths import REPO_ROOT, RUNTIME_ROOT, SKILLS_DIR
from .agent import (
    build_system_prompt,
    default_config,
    ground_message,
    load_skill_registry,
    make_options,
    run_turn,
)
from .shopping_tools import (
    SERVER_NAME,
    ShoppingToolset,
    allowed_tool_names,
    build_shopping_sdk_tools,
    build_shopping_server,
    load_mock_backend,
    mcp_tool_name,
    tool_contracts,
    tool_names,
)

__all__ = [
    "REPO_ROOT",
    "RUNTIME_ROOT",
    "SERVER_NAME",
    "SKILLS_DIR",
    "ShoppingToolset",
    "allowed_tool_names",
    "build_shopping_sdk_tools",
    "build_shopping_server",
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
