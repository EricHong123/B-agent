# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Shared fixtures: a toolset over the mock backend and its registered SDK tools."""

from __future__ import annotations

from typing import Any

import pytest
from claude_agent_sdk import SdkMcpTool

from merchant_agent_sdk import (
    MerchantToolset,
    build_merchant_sdk_tools,
    default_config,
    load_mock_backend,
)


@pytest.fixture
def toolset() -> MerchantToolset:
    """A toolset bound to a fresh mock ACME merchant backend and an empty session."""
    # The host-approval mode has its own tests.
    config = default_config().model_copy(update={"require_host_approval": False})
    return MerchantToolset(backend=load_mock_backend(), config=config)


@pytest.fixture
def handlers(toolset: MerchantToolset) -> dict[str, SdkMcpTool[Any]]:
    """The registered SDK tools for ``toolset``, indexed by tool name."""
    return {t.name: t for t in build_merchant_sdk_tools(toolset)}
