# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""A console for the shopping agent on the Agent SDK, over the mock ACME storefront::

    python shopping-agent/runtime-agent-sdk/main.py [--once "find me a tent"]

Needs ANTHROPIC_API_KEY or an authenticated Claude Code installation.
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
from shopping_agent_sdk import make_options, run_turn

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


async def chat() -> None:
    options, toolset = make_options()
    print("ACME shopping agent (Agent SDK path). Type 'exit' to quit.\n")
    async with ClaudeSDKClient(options=options) as client:
        while True:
            try:
                text = (await asyncio.to_thread(input, "you> ")).strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not text:
                continue
            if text.lower() in {"exit", "quit", "q"}:
                break
            result = await run_turn(client, text, toolset=toolset)
            print_turn(result)


async def once(prompt: str) -> None:
    options, toolset = make_options()
    async with ClaudeSDKClient(options=options) as client:
        result = await run_turn(client, prompt, toolset=toolset)
        print_turn(result)


def main() -> int:
    parser = argparse.ArgumentParser(description="ACME shopping agent on the Claude Agent SDK")
    parser.add_argument("--once", metavar="QUERY", help="run a single query and exit")
    args = parser.parse_args()
    with contextlib.suppress(KeyboardInterrupt):
        asyncio.run(once(args.once) if args.once else chat())
    return 0


if __name__ == "__main__":
    sys.exit(main())
