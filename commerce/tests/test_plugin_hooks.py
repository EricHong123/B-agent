# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The commerce-builder plugin's hooks, run as Claude Code runs them: the event JSON on
stdin, the verdict in the exit code, stderr, and stdout."""

import json
import subprocess
import sys
from pathlib import Path

HOOKS = Path(__file__).resolve().parents[1] / "plugins" / "commerce-builder" / "hooks"
# Built here rather than written out, so no scanner reads the fixtures as real credentials.
MODEL_KEY = "sk-ant-" + "a1" * 16
PAYMENT_KEY = "sk_" + "live_" + "b2" * 10


def run(script: str, tool_input: dict, **env: str) -> subprocess.CompletedProcess:
    event = {"hook_event_name": "PreToolUse", "tool_name": "Write", "tool_input": tool_input}
    return subprocess.run(
        [sys.executable, str(HOOKS / script)],
        input=json.dumps(event),
        capture_output=True,
        text=True,
        env={"PATH": "/usr/bin:/bin", **env},
        check=False,
    )


def test_a_hardcoded_key_is_refused_outside_a_local_env_file():
    held = run("secret_guard.py", {"file_path": "api/config.py", "content": f'KEY = "{MODEL_KEY}"'})
    assert held.returncode == 2 and "a model API key" in held.stderr
    edit = {"file_path": "api/pay.py", "old_string": "x", "new_string": PAYMENT_KEY}
    assert run("secret_guard.py", edit).returncode == 2
    template = {"file_path": ".env.example", "content": f"MODEL_API_KEY={MODEL_KEY}"}
    assert run("secret_guard.py", template).returncode == 2


def test_a_local_env_file_placeholders_and_the_switch_pass():
    assert (
        run("secret_guard.py", {"file_path": ".env", "content": f"K={MODEL_KEY}"}).returncode == 0
    )
    placeholder = {"file_path": "README.md", "content": "MODEL_API_KEY=sk-ant-..."}
    assert run("secret_guard.py", placeholder).returncode == 0
    off = {"file_path": "a.py", "content": MODEL_KEY}
    assert run("secret_guard.py", off, COMMERCE_BUILDER_HOOKS="0").returncode == 0


def test_an_edit_to_prompt_bytes_gets_a_reminder_and_other_files_do_not():
    for path in (
        "shopping-agent/core/shopping_agent/prompt.py",
        "agent/tools/registry.py",
        "shopping-agent/skills/customer-care/SKILL.md",
    ):
        result = run("prompt_bytes.py", {"file_path": path})
        context = json.loads(result.stdout)["hookSpecificOutput"]
        assert result.returncode == 0 and context["hookEventName"] == "PostToolUse"
        assert "byte-identical" in context["additionalContext"]
    for path in ("examples/retail/api/main.py", "registry.py", "docs/SKILL.md"):
        assert run("prompt_bytes.py", {"file_path": path}).stdout == ""
