#!/usr/bin/env python3
# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Run the merchant agent's morning digest headlessly: one turn of ``MerchantAgent`` over
the retail example's mock merchant, printing the reply and the ``present_digest``
payload. Schedule it with any job runner; replace :func:`build_demo_agent` with your own
backend.

    python run_morning_digest.py [--out digest.json]

Everything comes from the environment: MERCHANT_ID, MERCHANT_OPERATOR, and MERCHANT_TIMEZONE
set the session; ANTHROPIC_API_KEY or ANTHROPIC_AUTH_TOKEN, else the SDK's own chain, supplies
the credential. Exit status 2 means no credential worked, 1 any other failure.
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SKILLS_DIR = REPO_ROOT / "merchant-agent" / "skills"
DIGEST_PROMPT = "Produce the morning digest: what needs attention today and why."


def build_demo_agent() -> Any:
    from merchant_agent import MerchantAgentConfig
    from merchant_agent_runtime import MerchantAgent

    examples_dir = REPO_ROOT / "examples"
    if str(examples_dir) not in sys.path:
        sys.path.insert(0, str(examples_dir))
    from retail.api.mock_merchant import MockRetailMerchant
    from retail.api.mock_retail import MockRetail

    config = MerchantAgentConfig(brand_name="ACME")
    return MerchantAgent(
        backend=MockRetailMerchant(MockRetail(), config=config),
        skills_dir=SKILLS_DIR,
        config=config,
    )


async def run_digest(agent: Any | None = None) -> dict[str, Any]:
    """The prompt, the reply text, the digest payload (None when the turn produced
    none), and any other components the turn rendered."""
    from merchant_agent import MerchantSessionContext, MerchantSessionState

    agent = agent or build_demo_agent()
    timezone = os.environ.get("MERCHANT_TIMEZONE")
    session = MerchantSessionContext(
        session_id="scheduled-digest",
        merchant_id=os.environ.get("MERCHANT_ID", "acme-retail"),
        operator=os.environ.get("MERCHANT_OPERATOR", "scheduled-digest"),
        # This machine's clock is "today" unless the deployment names a timezone.
        timezone=timezone,
        now=None if timezone else datetime.now(),
    )
    messages: list[dict[str, Any]] = [{"role": "user", "content": DIGEST_PROMPT}]
    text: list[str] = []
    digest: dict[str, Any] | None = None
    others: list[dict[str, Any]] = []
    async for event in agent.stream_turn(messages, session, MerchantSessionState()):
        if event.type == "text_delta":
            text.append(event.data.get("text", ""))
        elif event.type == "ui" and event.data.get("component") == "digest":
            digest = event.data.get("payload")
        elif event.type == "ui":
            others.append(event.data)
    return {
        "prompt": DIGEST_PROMPT,
        "text": "".join(text).strip(),
        "digest": digest,
        "other_components": others,
    }


def _is_credential_failure(error: Exception) -> bool:
    try:
        import anthropic

        if isinstance(error, anthropic.AuthenticationError):
            return True
    except ImportError:
        pass
    described = str(error).lower()
    return any(marker in described for marker in ("authentication", "credential", "api_key"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--out", type=Path, metavar="FILE", help="also write the result as JSON")
    args = parser.parse_args(argv)
    try:
        result = asyncio.run(run_digest())
    except Exception as error:  # a scheduler wants one line of stderr
        if _is_credential_failure(error):
            print(f"error: no working Anthropic credentials ({error})", file=sys.stderr)
            return 2
        print(f"error: the digest run failed: {error}", file=sys.stderr)
        return 1
    print(result["text"] or "(the agent produced no text this run)")
    print()
    if result["digest"] is None:
        print("No digest component was produced this run.")
    else:
        print("Digest payload (present_digest):")
        print(json.dumps(result["digest"], indent=2, ensure_ascii=False))
    if args.out is not None:
        args.out.write_text(
            json.dumps(result, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
        )
        print(f"\nWrote {args.out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
