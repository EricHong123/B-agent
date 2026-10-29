# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Repo paths this runtime reads at import time, resolved from this file."""

from __future__ import annotations

from pathlib import Path

RUNTIME_ROOT = Path(__file__).resolve().parents[1]  # shopping-agent/runtime-agent-sdk
AGENT_ROOT = RUNTIME_ROOT.parent  # shopping-agent
REPO_ROOT = AGENT_ROOT.parent
SKILLS_DIR = AGENT_ROOT / "skills"
