# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

import logging

import pytest

pytest.importorskip("claude_agent_sdk")

from commerce_common.agent_sdk import (  # noqa: E402
    BaseToolset,
    TurnResult,
    build_sdk_tools,
    ensure_project_skills,
    ground,
    merge_turn_results,
    sdk_result,
)
from commerce_common.fencing import Fence  # noqa: E402
from commerce_common.grounding import GroundingRule  # noqa: E402
from commerce_common.streaming import AgentEvent, ToolOutcome  # noqa: E402

FENCE = Fence(label="test_data", notice="Data.")


class _Executor:
    """One tool per answer shape: a record, a written miss, a held call, an empty answer, a raise."""

    fence = FENCE

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict]] = []

    async def dispatch(self, name: str, args: dict) -> ToolOutcome:
        self.calls.append((name, args))
        if name == "missing":
            return ToolOutcome.error("No record with that id.")
        if name == "held":
            return ToolOutcome.held("provenance", "not yet")
        if name == "silent":
            return ToolOutcome("")
        if name == "raising":
            raise RuntimeError("backend down")
        return ToolOutcome(f"{name} result", [AgentEvent.ui("card", {"n": 1})])

    async def execute(self, name: str, args: dict) -> ToolOutcome:
        try:
            return await self.dispatch(name, args)
        except Exception as error:
            return ToolOutcome.error(str(error))


def _toolset() -> BaseToolset:
    toolset = BaseToolset()
    toolset.executor = _Executor()
    return toolset


def test_sdk_result_flags_failures_only():
    assert sdk_result(ToolOutcome("ok")) == {"content": [{"type": "text", "text": "ok"}]}
    assert sdk_result(ToolOutcome.held("g", "held")) == {
        "content": [{"type": "text", "text": "held"}]
    }
    assert sdk_result(ToolOutcome.error("bad"))["is_error"] is True


async def test_tools_execute_through_the_toolset_and_buffer_ui_payloads():
    toolset = _toolset()
    contracts = {
        "read": {"description": "Read.", "input_schema": {"type": "object", "properties": {}}}
    }
    (read,) = build_sdk_tools(toolset, contracts, ["read"])
    assert (read.name, read.description) == ("read", "Read.")
    result = await read.handler({"q": 1})
    assert result == {"content": [{"type": "text", "text": "read result"}]}
    assert toolset.executor.calls == [("read", {"q": 1})]
    assert toolset.drain_ui_events() == [{"component": "card", "payload": {"n": 1}}]
    assert toolset.drain_ui_events() == []


def _rule(tool: str) -> GroundingRule:
    """Fires when the message names the tool; the intro is the tool's name."""
    return GroundingRule(
        tool, tool, lambda c, t, s: {} if tool in t else None, lambda a: f"{tool.capitalize()}:"
    )


RULES = (
    GroundingRule("model_only", "policy", lambda c, t, s: {}),
    _rule("read"),
    _rule("missing"),
    _rule("held"),
    _rule("silent"),
    _rule("raising"),
)


async def test_ground_appends_every_answer_the_tool_wrote_and_fences_the_bare_ones():
    toolset = _toolset()
    text = "read, missing, held"
    grounded = await ground(text, RULES, None, None, toolset.executor)
    assert grounded == (
        f"{text}\n\n"
        "Read:\nread result\n\n"
        f"Missing:\n{FENCE.open}\nNo record with that id.\n{FENCE.close}\n\n"
        f"Held:\n{FENCE.open}\nnot yet\n{FENCE.close}"
    )
    assert [name for name, _ in toolset.executor.calls] == ["read", "missing", "held"]


async def test_ground_skips_a_tool_that_raises_or_answers_with_nothing(caplog):
    toolset = _toolset()
    text = "silent, raising, then read"
    with caplog.at_level(logging.WARNING, logger="commerce_common.agent_sdk"):
        grounded = await ground(text, RULES, None, None, toolset.executor)
    assert grounded == f"{text}\n\nRead:\nread result"
    assert [name for name, _ in toolset.executor.calls] == ["read", "silent", "raising"]
    (record,) = [r for r in caplog.records if r.name == "commerce_common.agent_sdk"]
    assert record.levelno == logging.WARNING and "raising" in record.getMessage()
    assert record.exc_info is not None and isinstance(record.exc_info[1], RuntimeError)


async def test_ground_leaves_a_message_no_rule_fires_on_untouched():
    toolset = _toolset()
    assert await ground("nothing here", RULES, None, None, toolset.executor) == "nothing here"
    assert toolset.executor.calls == []


def test_merge_turn_results_reports_two_passes_as_one():
    first = TurnResult("a", ["x"], [{}], cost_usd=0.1, tool_errors=["x — no"])
    second = TurnResult("b", ["y"], [{"k": 1}], is_error=True)
    merged = merge_turn_results(first, second)
    assert (merged.text, merged.tool_calls, merged.tool_inputs) == (
        "a\n\nb",
        ["x", "y"],
        [{}, {"k": 1}],
    )
    assert (
        merged.cost_usd == pytest.approx(0.1)
        and merged.is_error
        and merged.tool_errors == ["x — no"]
    )


def test_ensure_project_skills_mirrors_the_source_directory(tmp_path):
    source = tmp_path / "skills"
    for name in ("alpha", "beta"):
        (source / name).mkdir(parents=True)
        (source / name / "SKILL.md").write_text("---\nname: x\ndescription: y\n---\nbody")
    (source / "notes").mkdir()  # no SKILL.md: not a skill
    project = tmp_path / "runtime"
    (project / ".claude" / "skills" / "retired").mkdir(parents=True)

    target = ensure_project_skills(source, project)
    assert sorted(p.name for p in target.iterdir()) == ["alpha", "beta"]
    assert (target / "alpha" / "SKILL.md").read_text().endswith("body")
    assert ensure_project_skills(source, project) == target


def test_ensure_project_skills_refreshes_a_copied_skill(tmp_path, monkeypatch):
    source = tmp_path / "skills"
    (source / "alpha").mkdir(parents=True)
    (source / "alpha" / "SKILL.md").write_text("---\nname: x\ndescription: y\n---\nfirst")
    project = tmp_path / "runtime"

    def no_symlinks(self, *args, **kwargs):
        raise OSError("symlinks unavailable")

    monkeypatch.setattr(type(source), "symlink_to", no_symlinks)
    target = ensure_project_skills(source, project)
    assert not (target / "alpha").is_symlink()
    (source / "alpha" / "SKILL.md").write_text("---\nname: x\ndescription: y\n---\nsecond")
    ensure_project_skills(source, project)
    assert (target / "alpha" / "SKILL.md").read_text().endswith("second")
