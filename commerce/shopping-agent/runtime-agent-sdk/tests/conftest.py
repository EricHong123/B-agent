# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures: a toolset over the mock backend and its registered SDK tools."""

from __future__ import annotations

from typing import Any

import pytest
from claude_agent_sdk import SdkMcpTool

from shopping_agent_sdk import (
    ShoppingToolset,
    build_shopping_sdk_tools,
    default_config,
    load_mock_backend,
)


@pytest.fixture
def toolset() -> ShoppingToolset:
    """A toolset bound to a fresh mock ACME retailer and an empty session."""
    return ShoppingToolset(backend=load_mock_backend(), config=default_config())


@pytest.fixture
def handlers(toolset: ShoppingToolset) -> dict[str, SdkMcpTool[Any]]:
    """The registered SDK tools for ``toolset``, indexed by tool name."""
    return {t.name: t for t in build_shopping_sdk_tools(toolset)}
