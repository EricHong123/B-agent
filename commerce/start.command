#!/usr/bin/env bash
# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
#
# One-click start: double-click in Finder (macOS opens it in Terminal) or run ./start.command.
# Stops whatever an earlier run left behind, starts the four verticals' APIs and the unified
# app on the code on disk, and opens the unified app: the five demo apps as one behind a
# rail. Arguments pass through to scripts/start_all.sh (./start.command retail,
# ./start.command --stop). Close the window or press Ctrl-C to stop.

cd "$(dirname "$0")" && exec scripts/start_all.sh --open "$@"
