# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

import importlib.util
from pathlib import Path

from commerce_common.testing import FakeClient, text_message, tool_use_message

SCRIPT = (
    Path(__file__).resolve().parents[2]
    / "managed-agents"
    / "scheduled-digest"
    / "run_morning_digest.py"
)


def _load_script():
    spec = importlib.util.spec_from_file_location("run_morning_digest", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_demo_agent_builds_over_the_repo_skills(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    agent = _load_script().build_demo_agent()
    assert "inventory-operations" in agent.skills.names


async def test_headless_turn_returns_the_digest_payload(monkeypatch):
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    script = _load_script()
    agent = script.build_demo_agent()
    agent.client = FakeClient(
        [
            tool_use_message(
                "present_digest",
                {"items": [{"kind": "note", "headline": "Quiet morning."}]},
            ),
            text_message("Nothing needs you today."),
        ]
    )
    result = await script.run_digest(agent)
    assert result["text"] == "Nothing needs you today."
    assert result["digest"]["items"][0]["headline"] == "Quiet morning."
    assert result["other_components"] == []


async def test_the_session_comes_from_the_merchant_environment_variables(monkeypatch):
    monkeypatch.setenv("MERCHANT_ID", "acme-outlet")
    monkeypatch.setenv("MERCHANT_OPERATOR", "night-shift")
    monkeypatch.setenv("MERCHANT_TIMEZONE", "Europe/Lisbon")
    sessions = []

    class RecordingAgent:
        async def stream_turn(self, messages, session, state):
            sessions.append(session)
            return
            yield

    await _load_script().run_digest(RecordingAgent())
    (session,) = sessions
    assert (session.merchant_id, session.operator) == ("acme-outlet", "night-shift")
    assert session.timezone == "Europe/Lisbon"
