#!/usr/bin/env bash
# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
#
# Install the repository's packages and their pinned dependencies into the active environment.
#
#   ./scripts/install.sh            # requirements.txt: the seven packages plus what they need
#   ./scripts/install.sh dev        # requirements-dev.txt: the above plus pytest and ruff
#
# Runs from any directory, inside a virtualenv (python3 -m venv .venv && source .venv/bin/activate).
set -euo pipefail

cd "$(dirname "$0")/.."

if ! python -c 'import sys; sys.exit(0 if sys.prefix != sys.base_prefix else 1)' 2>/dev/null; then
  echo "warning: no virtualenv active; system Pythons usually refuse global installs." >&2
fi

case "${1:-all}" in
  all) pip install -r requirements.txt ;;
  dev) pip install -r requirements-dev.txt ;;
  *) echo "usage: $0 [all|dev]" >&2; exit 2 ;;
esac
