# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""PreToolUse on Write and Edit: refuse text that hardcodes a live credential (a model API
key, a live payment key, a cloud access key, a private key) in any file but a local
``.env``. A credential belongs in the environment, where the model client and the
backend read it server-side; the model never sees one. Exit 2 blocks the call and the
message on stderr tells Claude why. ``COMMERCE_BUILDER_HOOKS=0`` turns the hook off."""

from __future__ import annotations

import json
import os
import re
import sys
from pathlib import PurePath

PATTERNS = (
    ("a model API key", re.compile(r"\bsk-ant-[A-Za-z0-9_-]{20,}")),
    ("a model API key", re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{32,}")),
    ("a live payment key", re.compile(r"\b(?:sk|rk)_live_[A-Za-z0-9]{16,}")),
    ("a cloud access key", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("a private key", re.compile(r"-----BEGIN (?:[A-Z]+ )?PRIVATE KEY-----")),
)
# Local env files hold credentials by design; their committed templates do not.
_TEMPLATES = (".example", ".sample", ".template")


def written_text(tool_input: dict) -> str:
    parts = [tool_input.get("content"), tool_input.get("new_string")]
    parts += [
        edit.get("new_string") for edit in tool_input.get("edits") or [] if isinstance(edit, dict)
    ]
    return "\n".join(part for part in parts if isinstance(part, str))


def holds_credentials(path: str) -> bool:
    name = PurePath(path).name
    return name.startswith(".env") and not name.endswith(_TEMPLATES)


def finding(tool_input: dict) -> str | None:
    if holds_credentials(str(tool_input.get("file_path") or "")):
        return None
    text = written_text(tool_input)
    for label, pattern in PATTERNS:
        if pattern.search(text):
            return label
    return None


def main() -> int:
    if os.environ.get("COMMERCE_BUILDER_HOOKS", "1") == "0":
        return 0
    try:
        event = json.load(sys.stdin)
    except ValueError:
        return 0
    label = finding(event.get("tool_input") or {})
    if label is None:
        return 0
    print(
        f"commerce-builder: this write hardcodes what looks like {label}. Read it from the "
        "environment instead (the example APIs load .env; .env.example carries the variable "
        "name with an empty value), and leave the value out of code, fixtures, and docs.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    sys.exit(main())
