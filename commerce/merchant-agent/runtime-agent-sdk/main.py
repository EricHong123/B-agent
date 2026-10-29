# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""A console for the merchant agent on the Agent SDK, over the mock ACME merchant::

    python merchant-agent/runtime-agent-sdk/main.py [--once "how did last week go"]

Needs ANTHROPIC_API_KEY or an authenticated Claude Code installation. In interactive mode the console is the approval host: it asks
y/N for each change a turn stages, and apply_change succeeds only for changes approved
here (``--no-host-approval`` accepts approval in chat instead). ``--once`` has no prompt
to ask on, so its staged changes stay staged.
"""

from __future__ import annotations

import argparse
import asyncio
import contextlib
import json
import re
import sys

from claude_agent_sdk import ClaudeSDKClient

from commerce_common.agent_sdk import TurnResult
from merchant_agent_sdk import default_config, make_options, run_turn

_BOLD = re.compile(r"\*\*(.+?)\*\*")


def _render_prose(text: str) -> str:
    """Markdown bold as ANSI bold on a tty, stripped when piped."""
    replacement = "\033[1m\\1\033[0m" if sys.stdout.isatty() else "\\1"
    return _BOLD.sub(replacement, text)


def print_turn(result: TurnResult) -> None:
    if result.text:
        print(f"\n{_render_prose(result.text)}\n")
    for event in result.ui:
        print(f"--- ui:{event['component']} ---")
        print(json.dumps(event["payload"], indent=2, default=str, ensure_ascii=False))
        print()
    if result.tool_calls:
        print(f"[tools: {', '.join(result.tool_calls)}]")
    for error in result.tool_errors:
        print(f"[tool error: {error}]")
    if result.cost_usd is not None:
        print(f"[cost: ${result.cost_usd:.4f}]")


def apply_attempts(result: TurnResult) -> set[str]:
    """The change ids the model tried to apply this turn."""
    return {
        str(arguments.get("change_id"))
        for name, arguments in zip(result.tool_calls, result.tool_inputs, strict=True)
        if name.endswith("apply_change") and arguments.get("change_id")
    }


async def confirm_staged_changes(client: ClaudeSDKClient, toolset, declined: set[str]) -> None:
    """Ask y/N for each newly staged change; a yes marks the change, asks the agent to
    apply it, and clears the mark when that turn returns; a no is remembered so the change
    is not offered again."""
    for change in toolset.pending_host_approvals():
        if change.change_id in declined:
            continue
        print(f"\n{change.change_id} — {change.summary}")
        answer = (await asyncio.to_thread(input, "approve? [y/N] ")).strip().lower()
        if answer in {"y", "yes"}:
            toolset.host_approve(change.change_id)
            try:
                result = await run_turn(
                    client,
                    f"Approved {change.change_id} through the console — apply it now.",
                    toolset=toolset,
                )
            finally:
                toolset.host_clear(change.change_id)
            print_turn(result)
        else:
            declined.add(change.change_id)
            print(f"{change.change_id} stays staged (dismiss it in chat to drop it).")


async def chat(host_approval: bool) -> None:
    config = default_config()
    if host_approval:
        config = config.model_copy(
            update={
                "require_host_approval": True,
                "approval_surface": "the y/N prompt in this console",
            }
        )
    else:
        config = config.model_copy(update={"require_host_approval": False})
    options, toolset = make_options(config=config)
    declined: set[str] = set()
    print("ACME merchant agent (Agent SDK path). Type 'exit' to quit.\n")
    async with ClaudeSDKClient(options=options) as client:
        while True:
            try:
                text = (await asyncio.to_thread(input, "operator> ")).strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not text:
                continue
            if text.lower() in {"exit", "quit", "q"}:
                break
            result = await run_turn(client, text, toolset=toolset)
            print_turn(result)
            if host_approval:
                # An apply attempt on a declined change reopens the question.
                declined.difference_update(apply_attempts(result))
                await confirm_staged_changes(client, toolset, declined)


async def once(prompt: str) -> None:
    options, toolset = make_options()
    async with ClaudeSDKClient(options=options) as client:
        result = await run_turn(client, prompt, toolset=toolset)
        print_turn(result)


def main() -> int:
    parser = argparse.ArgumentParser(description="ACME merchant agent on the Claude Agent SDK")
    parser.add_argument("--once", metavar="QUERY", help="run a single query and exit")
    parser.add_argument(
        "--no-host-approval",
        action="store_true",
        help="let a chat-text approval apply changes instead of the console's y/N prompt",
    )
    args = parser.parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(once(args.once) if args.once else chat(not args.no_host_approval))
    return 0


if __name__ == "__main__":
    sys.exit(main())
