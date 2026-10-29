# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Plumbing the two Agent SDK runtimes share: registering an executor's tools as an
in-process MCP server, materializing the repo skills for the SDK, host-side grounding,
the hook that ends a turn on a chip-carrying presentation round, and collecting a turn.
Importing it requires ``claude-agent-sdk``.
"""

from __future__ import annotations

import logging
import os
import shutil
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from claude_agent_sdk import (
    AssistantMessage,
    ClaudeSDKClient,
    HookContext,
    HookJSONOutput,
    HookMatcher,
    ResultMessage,
    SdkMcpTool,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
    UserMessage,
    tool,
)

from .execution import BaseToolExecutor
from .grounding import GroundingRule
from .memory import InMemoryMemoryStore, MemoryRuntime, MemoryStore, MemoryWriteFilter
from .presentation import CHIPS_COMPONENT
from .streaming import ToolOutcome
from .turn import round_closes_turn

logger = logging.getLogger(__name__)

# Appended to the static prompt: the SDK loads skill bodies through its own Skill tool.
SKILL_TOOL_ADAPTER = """\
# Skill loading in this deployment

In this deployment, skill instructions load through the `Skill` tool (there is no
`load_skill` tool). When a request matches a skill's description in the
index above, invoke `Skill` with that skill's name before acting. Everything else
above applies unchanged."""


def ensure_project_skills(skills_dir: Path, project_root: Path) -> Path:
    """Link every skill under ``skills_dir`` into ``project_root/.claude/skills`` (copied
    where symlinks are unavailable), replacing any entry that is not a link to the current
    source, so the SDK discovers exactly the repo's skills. Returns the materialized directory."""
    target_root = project_root / ".claude" / "skills"
    target_root.mkdir(parents=True, exist_ok=True)
    current = {d.name for d in skills_dir.iterdir() if (d / "SKILL.md").is_file()}
    for entry in target_root.iterdir():
        source = skills_dir / entry.name
        if entry.name in current and entry.is_symlink() and entry.resolve() == source.resolve():
            continue
        # A retired skill, a link to another directory, or a copy from an earlier call:
        # remove it; the loop below rebuilds what the source still has.
        if entry.is_symlink() or entry.is_file():
            entry.unlink()
        else:
            shutil.rmtree(entry)
    for name in sorted(current):
        link = target_root / name
        if link.is_symlink():
            continue
        try:
            link.symlink_to(
                os.path.relpath(skills_dir / name, target_root), target_is_directory=True
            )
        except OSError:
            shutil.copytree(skills_dir / name, link)
    return target_root


def sdk_result(outcome: ToolOutcome) -> dict[str, Any]:
    """An MCP result dict. Only a failure is flagged ``is_error``; a held call is a
    plain result whose text says what the gate needs."""
    result: dict[str, Any] = {"content": [{"type": "text", "text": outcome.result_text}]}
    if outcome.is_error:
        result["is_error"] = True
    return result


# Fired once per round, after every tool call in it resolved and before the next model
# call; the SDK forwards it to the CLI, whose hook of this name carries ``tool_calls``.
CLOSE_HOOK_EVENT = "PostToolBatch"


@dataclass(kw_only=True)
class BaseToolset:
    """The per-conversation state behind one SDK server. Role subclasses add the backend,
    config, session, and state, and build ``executor``. ``ui_events`` collects the
    payloads presentation tools produced for the host to render after the turn;
    ``round_calls`` holds the calls since the last round ended and ``turn_calls`` every
    tool name this turn, for the closing hook; ``holds_turn_open``, set per turn by the
    role's ``run_turn``, is a check on ``turn_calls`` that keeps a chips round from
    closing the turn (the merchant's staging reminder is due first)."""

    memory_store: MemoryStore = field(default_factory=InMemoryMemoryStore)
    memory_write_filter: MemoryWriteFilter | None = None
    ui_events: list[dict[str, Any]] = field(default_factory=list)
    round_calls: list[tuple[str, ToolOutcome]] = field(default_factory=list)
    turn_calls: list[str] = field(default_factory=list)
    holds_turn_open: Callable[[Sequence[str]], bool] | None = None
    turn_closed: bool = False

    memory: MemoryRuntime = field(init=False)
    executor: BaseToolExecutor = field(init=False)

    def attach_memory(self, memory: MemoryRuntime) -> None:
        self.memory = memory
        self.memory_store = memory.store or self.memory_store
        self.memory_write_filter = memory.write_filter

    async def execute(self, name: str, args: dict[str, Any]) -> ToolOutcome:
        outcome = await self.executor.execute(name, args)
        self.ui_events.extend(event.data for event in outcome.events if event.type == "ui")
        self.round_calls.append((name, outcome))
        self.turn_calls.append(name)
        return outcome

    def begin_turn(self, holds_turn_open: Callable[[Sequence[str]], bool] | None = None) -> None:
        self.round_calls, self.turn_calls, self.turn_closed = [], [], False
        self.holds_turn_open = holds_turn_open

    def closes_turn(self, batch_size: int) -> bool:
        """The closing hook's verdict on the round that just ended: True when the turn
        ends here, by the Messages API loop's own test. ``batch_size`` is the CLI's count
        of the round's calls; a call that did not come through this toolset (the Skill
        tool) makes the round not a presentation round."""
        calls, self.round_calls = self.round_calls, []
        if len(calls) != batch_size:
            logger.debug(
                "close hook saw %d calls, toolset %d; the round stays open", batch_size, len(calls)
            )
            return False
        closes = round_closes_turn(calls, self.executor.ends_clean) and not (
            self.holds_turn_open and self.holds_turn_open(self.turn_calls)
        )
        self.turn_closed = self.turn_closed or closes
        return closes

    def drain_ui_events(self) -> list[dict[str, Any]]:
        """The turn's payloads in order. When the chips went out more than once (a card in
        their round was rejected and sent again with them), only the last set is kept."""
        events, self.ui_events = list(self.ui_events), []
        chips = [i for i, event in enumerate(events) if event.get("component") == CHIPS_COMPONENT]
        return [e for i, e in enumerate(events) if i not in chips[:-1]]


def close_on_presentation_hook(
    toolset: BaseToolset, enabled: bool
) -> dict[str, list[HookMatcher]] | None:
    """The ``hooks`` entry that ends the SDK's turn where the Messages API loop ends it:
    after a round in which present_suggestions succeeded and every other call was a clean
    presentation call; None when the deployment switches ``close_on_presentation`` off.
    The CLI persists the round's tool results before it stops, so the next message
    follows them as it does on that path."""
    if not enabled:
        return None

    async def hook(
        input_data: Any, _tool_use_id: str | None, _context: HookContext
    ) -> HookJSONOutput:
        if toolset.closes_turn(len(input_data.get("tool_calls") or [])):
            return {"continue_": False, "stopReason": "The reply closed on its chips."}
        return {}

    return {CLOSE_HOOK_EVENT: [HookMatcher(hooks=[hook])]}


def build_sdk_tools(
    toolset: BaseToolset, contracts: Mapping[str, Mapping[str, Any]], names: Sequence[str]
) -> list[SdkMcpTool[Any]]:
    """One ``@tool`` per name, registered under the registry's description and schema
    and executed through the toolset."""

    def register(name: str) -> SdkMcpTool[Any]:
        contract = contracts[name]

        async def handler(args: dict[str, Any]) -> dict[str, Any]:
            return sdk_result(await toolset.execute(name, args or {}))

        return tool(name, str(contract["description"]), dict(contract["input_schema"]))(handler)

    return [register(name) for name in names]


async def ground(
    text: str,
    rules: Sequence[GroundingRule],
    config: Any,
    state: Any,
    executor: BaseToolExecutor,
) -> str:
    """The prefetching form of the grounding rules: every rule that fires on the user's
    own words runs its tool now, and the tool's answer is appended under the rule's
    intro, a miss or a held call included (fenced here, since the tool writes those
    bare). A tool that raises, or answers with nothing, appends nothing; the raise is
    logged at warning level with its traceback."""
    parts = [text]
    for rule in rules:
        if rule.prefetch_intro is None or (args := rule.fires(config, text, state)) is None:
            continue
        try:
            outcome = await executor.dispatch(rule.tool, args)
        except Exception:  # grounding never breaks the turn
            logger.warning(
                "grounding prefetch of %s failed and the turn continues without it",
                rule.tool,
                exc_info=True,
            )
            continue
        if not outcome.result_text:
            continue
        body = outcome.result_text
        if outcome.refused:
            body = executor.fence.fence_payload(body)
        parts.append(f"{rule.prefetch_intro(args)}\n{body}")
    return "\n\n".join(parts)


@dataclass
class TurnResult:
    """One turn as the host sees it. ``tool_inputs`` parallels ``tool_calls``;
    ``tool_errors`` holds ``"tool — message"`` for every failed call."""

    text: str
    tool_calls: list[str] = field(default_factory=list)
    tool_inputs: list[dict[str, Any]] = field(default_factory=list)
    ui: list[dict[str, Any]] = field(default_factory=list)
    cost_usd: float | None = None
    is_error: bool = False
    tool_errors: list[str] = field(default_factory=list)


async def collect_turn(client: ClaudeSDKClient) -> TurnResult:
    """Read one complete response; the caller drains the toolset's UI events."""
    chunks: list[str] = []
    result = TurnResult(text="")
    names_by_id: dict[str, str] = {}
    async for message in client.receive_response():
        if isinstance(message, AssistantMessage):
            for block in message.content:
                if isinstance(block, TextBlock):
                    chunks.append(block.text)
                elif isinstance(block, ToolUseBlock):
                    result.tool_calls.append(block.name)
                    result.tool_inputs.append(dict(block.input or {}))
                    names_by_id[block.id] = block.name
        elif isinstance(message, UserMessage):
            content = message.content if isinstance(message.content, list) else []
            for block in content:
                if isinstance(block, ToolResultBlock) and block.is_error:
                    name = names_by_id.get(block.tool_use_id, "tool")
                    result.tool_errors.append(f"{name} — {_result_text(block.content)}")
        elif isinstance(message, ResultMessage):
            result.cost_usd = message.total_cost_usd
            result.is_error = message.is_error
    # Text blocks are separate paragraphs; joined bare they run sentences together.
    result.text = "\n\n".join(chunk.strip() for chunk in chunks if chunk.strip())
    return result


def merge_turn_results(first: TurnResult, second: TurnResult) -> TurnResult:
    """Two passes of one turn (a reminded turn) reported as one."""
    costs = [cost for cost in (first.cost_usd, second.cost_usd) if cost is not None]
    return TurnResult(
        text="\n\n".join(part for part in (first.text, second.text) if part),
        tool_calls=first.tool_calls + second.tool_calls,
        tool_inputs=first.tool_inputs + second.tool_inputs,
        cost_usd=sum(costs) if costs else None,
        is_error=first.is_error or second.is_error,
        tool_errors=first.tool_errors + second.tool_errors,
    )


def _result_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    parts = [
        str(block.get("text", ""))
        for block in content or []
        if isinstance(block, dict) and block.get("type") == "text"
    ]
    return " ".join(part.strip() for part in parts if part.strip()) or "(no detail)"
