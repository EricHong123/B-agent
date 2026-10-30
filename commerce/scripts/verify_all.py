# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The full verification loop: lint, format check, check.py, pytest, deploy dry-runs, the eight
web builds, and (with --live) a scripted conversation against the API.

    python scripts/verify_all.py            # everything that runs without API access
    python scripts/verify_all.py --live     # adds the live smoke conversation
    python scripts/verify_all.py --skip-web # no node available

Steps run cheapest first and in the interpreter that runs this script; the loop exits
non-zero if any step failed. The live step uses the ambient credentials.
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
import time
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
PYTHON = sys.executable
EXAMPLES = REPO_ROOT / "examples"
NEXT = EXAMPLES / "node_modules" / ".bin" / "next"
VERTICALS = ("retail", "travel", "telecom", "entertainment")


class Step:
    def __init__(
        self, name: str, cmd: list[str], *, cwd: Path | None = None, env: dict | None = None
    ):
        self.name = name
        self.cmd = cmd
        self.cwd = cwd or REPO_ROOT
        self.env = env
        self.passed: bool | None = None
        self.duration: float = 0.0
        self.tail: str = ""

    def run(self) -> bool:
        started = time.perf_counter()
        merged_env = {**os.environ, **(self.env or {})}
        result = subprocess.run(
            self.cmd, cwd=self.cwd, env=merged_env, capture_output=True, text=True
        )
        self.duration = time.perf_counter() - started
        self.passed = result.returncode == 0
        output = (result.stdout + result.stderr).strip()
        self.tail = "\n".join(output.splitlines()[-12:])
        return self.passed


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--live", action="store_true", help="include steps that call the Anthropic API"
    )
    parser.add_argument("--skip-web", action="store_true", help="skip the web builds")
    args = parser.parse_args()

    steps: list[Step] = [
        Step("lint (ruff check)", [PYTHON, "-m", "ruff", "check", "."]),
        Step("format (ruff format --check)", [PYTHON, "-m", "ruff", "format", "--check", "."]),
        Step("repo consistency (check.py)", [PYTHON, "scripts/check.py"]),
        Step("tests (pytest)", [PYTHON, "-m", "pytest", "-q"]),
        Step(
            "managed-agents deploy dry-run (shopping-agent)",
            [
                "bash",
                "scripts/deploy_managed_agent.sh",
                "shopping-agent/managed-agents/shopping-agent",
            ],
        ),
        Step(
            "managed-agents deploy dry-run (merchant-agent)",
            [
                "bash",
                "scripts/deploy_managed_agent.sh",
                "merchant-agent/managed-agents/merchant-agent",
            ],
        ),
    ]

    if not args.skip_web:
        if shutil.which("npm"):
            if not NEXT.exists():
                steps.append(
                    Step(
                        "web workspace deps (npm ci)",
                        ["npm", "ci", "--no-audit", "--no-fund"],
                        cwd=EXAMPLES,
                    )
                )
            for vertical in VERTICALS:
                for app in ("storefront-web", "merchant-web"):
                    steps.append(
                        Step(
                            f"{vertical} {app} (next build)",
                            [str(NEXT), "build"],
                            cwd=EXAMPLES / vertical / app,
                        )
                    )
            # The one app over five (examples/unified-web) builds with webpack: its "@/" resolver
            # is a webpack plugin.
            steps.append(
                Step(
                    "unified-web (next build)",
                    [str(NEXT), "build", "--webpack"],
                    cwd=EXAMPLES / "unified-web",
                )
            )
        else:
            print("note: npm not found; skipping web builds (use --skip-web to silence)")

    if args.live:
        steps.append(Step("live smoke conversation", [PYTHON, "scripts/smoke_chat.py"]))

    print(f"verify_all: {len(steps)} steps\n")
    failures = []
    for step in steps:
        sys.stdout.write(f"  {step.name:<48} ... ")
        sys.stdout.flush()
        ok = step.run()
        print(f"{'PASS' if ok else 'FAIL'}  ({step.duration:.1f}s)")
        if not ok:
            failures.append(step)

    print()
    if failures:
        print(f"verify_all: {len(failures)} step(s) FAILED\n")
        for step in failures:
            print(f"--- {step.name} (last lines) ---")
            print(step.tail)
            print()
        return 1
    print("verify_all: all steps passed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
