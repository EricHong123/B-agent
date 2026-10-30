#!/usr/bin/env bash
# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
#
# Deploy a Managed Agent manifest to the Managed Agents API (/v1/agents).
#
# Usage: scripts/deploy_managed_agent.sh <agent.yaml or its directory> [--dry-run | --live]
#
#   scripts/deploy_managed_agent.sh shopping-agent/managed-agents/shopping-agent          # dry run (default):
#                                                                                        # print the request body
#   scripts/deploy_managed_agent.sh merchant-agent/managed-agents/merchant-agent --live   # upload skills, create the agent
#
# A dry run needs python3 with PyYAML (the repo's .venv/bin/python when it exists, else
# python3; PYTHON overrides). A live deploy also needs curl, ANTHROPIC_API_KEY, and every
# ${VAR} the manifest uses (its MCP server URL) set.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
API_BASE="${ANTHROPIC_API_URL:-https://api.anthropic.com}"
API_VERSION="2023-06-01"
AGENTS_BETA="managed-agents-2026-04-01"
SKILLS_BETA="skills-2025-10-02"

usage() { sed -n '5,15p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }

TARGET=""
MODE="dry-run"
for arg in "$@"; do
  case "$arg" in
    --dry-run) MODE="dry-run" ;;
    --live) MODE="live" ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "error: unknown flag: $arg" >&2; usage >&2; exit 2 ;;
    *) [[ -z "$TARGET" ]] || { echo "error: more than one manifest given" >&2; exit 2; }; TARGET="$arg" ;;
  esac
done
[[ -n "$TARGET" ]] || { usage >&2; exit 2; }

MANIFEST="$TARGET"
[[ -d "$MANIFEST" ]] && MANIFEST="${MANIFEST%/}/agent.yaml"
[[ -f "$MANIFEST" ]] || { echo "error: no manifest at $MANIFEST" >&2; exit 2; }
MANIFEST="$(cd "$(dirname "$MANIFEST")" && pwd)/$(basename "$MANIFEST")"

if [[ -z "${PYTHON:-}" ]]; then
  PYTHON="python3"
  [[ -x "$REPO_ROOT/.venv/bin/python" ]] && PYTHON="$REPO_ROOT/.venv/bin/python"
fi
# The resolver is a commerce_common module; the source tree serves when it is not installed.
export PYTHONPATH="$REPO_ROOT/commerce-common${PYTHONPATH:+:$PYTHONPATH}"
resolve() { "$PYTHON" -m commerce_common.manifest "$MANIFEST" "$@"; }

if [[ "$MODE" == "dry-run" ]]; then
  echo "# Dry run: the POST $API_BASE/v1/agents body for $MANIFEST. Nothing was created." >&2
  resolve
  exit 0
fi

if [[ -z "${ANTHROPIC_API_KEY:-}" ]]; then
  echo "error: set ANTHROPIC_API_KEY for --live" >&2; exit 2
fi

json_field() { "$PYTHON" -c 'import json,sys; print(json.load(sys.stdin)[sys.argv[1]])' "$1"; }

# 1. Upload each local skill: one files[] part per file, named by its path under the
#    skill directory.
SKILL_ID_ARGS=()
while IFS=$'\t' read -r skill_name skill_dir; do
  [[ -n "$skill_name" ]] || continue
  echo "Uploading skill '$skill_name' from $skill_dir ..." >&2
  file_args=()
  while IFS= read -r file; do
    file_args+=(-F "files[]=@$file;filename=$skill_name/${file#"$skill_dir"/}")
  done < <(find "$skill_dir" -type f | sort)
  if ! response=$(curl -sS --fail-with-body "$API_BASE/v1/skills" -H "x-api-key: $ANTHROPIC_API_KEY" \
      -H "anthropic-version: $API_VERSION" -H "anthropic-beta: $SKILLS_BETA" \
      -F "display_title=$skill_name" "${file_args[@]}"); then
    echo "error: skill upload failed for '$skill_name':" >&2; echo "$response" >&2; exit 1
  fi
  skill_id=$(json_field id <<<"$response")
  echo "  -> $skill_id" >&2
  SKILL_ID_ARGS+=(--skill-id "$skill_name=$skill_id")
done < <(resolve --list-skills)

# 2. Resolve with the uploaded ids; every ${VAR} must be set now.
request_body=$(resolve --require-env ${SKILL_ID_ARGS[@]+"${SKILL_ID_ARGS[@]}"})

# 3. Create the agent.
echo "Creating agent via POST $API_BASE/v1/agents ..." >&2
if ! agent_response=$(curl -sS --fail-with-body "$API_BASE/v1/agents" -H "x-api-key: $ANTHROPIC_API_KEY" \
    -H "anthropic-version: $API_VERSION" -H "anthropic-beta: $AGENTS_BETA" \
    -H "content-type: application/json" -d "$request_body"); then
  echo "error: agent creation failed:" >&2; echo "$agent_response" >&2; exit 1
fi
echo "$agent_response"
agent_id=$(json_field id <<<"$agent_response")
cat >&2 <<EOF

Created agent $agent_id. Next, following $(dirname "$MANIFEST")/../README.md:
  1. create an environment:        POST $API_BASE/v1/environments
  2. register the MCP credential:  vaults -> vault_id
  3. start a session:              POST $API_BASE/v1/sessions
     {"agent": "$agent_id", "environment_id": ..., "vault_ids": [...]}
EOF
