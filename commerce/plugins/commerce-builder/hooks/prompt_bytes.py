# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""PostToolUse on Write and Edit: after an edit to a file the static prompt, the tool list,
a skill, or a fence notice is built from, remind Claude what that edit owes: the bytes
stay identical across requests (per-request data goes after the cache breakpoint), the
Managed Agents system.md is re-derived, and the eval replay is re-recorded. The reminder
reaches Claude as additional context and blocks nothing. ``COMMERCE_BUILDER_HOOKS=0``
turns the hook off."""

from __future__ import annotations

import json
import os
import sys
from pathlib import PurePath

# Path shapes of the reference layout (shopping_agent/, merchant_agent/, skills/) and of the
# agents /scaffold-commerce-agent writes.
_NAMES = {"prompt.py", "fencing.py", "registry.py", "SKILL.md", "agent.yaml"}


def watched(path: str) -> bool:
    parts = PurePath(path).parts
    if not parts or parts[-1] not in _NAMES:
        return False
    if parts[-1] == "registry.py":
        return "tools" in parts
    if parts[-1] == "SKILL.md":
        return "skills" in parts
    return True


REMINDER = (
    "commerce-builder: {name} feeds the static prompt or the tool list. Keep its output "
    "byte-identical across requests (per-request data goes in the context block after the "
    "cache breakpoint), re-derive the Managed Agents system.md if this agent deploys there "
    "(scripts/check.py compares them in the reference repo), and re-record the eval replay "
    "before shipping."
)


def main() -> int:
    if os.environ.get("COMMERCE_BUILDER_HOOKS", "1") == "0":
        return 0
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    path = str((event.get("tool_input") or {}).get("file_path") or "")
    if not watched(path):
        return 0
    output = {
        "hookSpecificOutput": {
            "hookEventName": "PostToolUse",
            "additionalContext": REMINDER.format(name=PurePath(path).name),
        }
    }
    print(json.dumps(output))
    return 0


if __name__ == "__main__":
    sys.exit(main())
