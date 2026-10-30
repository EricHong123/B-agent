#!/usr/bin/env bash
# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0
#
# Set up the repository and start the demo: every vertical's API and the unified app, the one
# web page to open.
#
#   scripts/start_all.sh                       # APIs :8000-8003 and the unified app :3300
#   scripts/start_all.sh retail travel         # only the verticals named
#   scripts/start_all.sh --open                # and open the unified app
#   scripts/start_all.sh --separate-apps       # also each storefront (:3000-3003), each portal
#                                              # (:3100-3103), and the demo hub (:3200)
#   scripts/start_all.sh --stop                # stop what an earlier run left behind, and exit
#   scripts/start_all.sh --no-reload           # an API that does not restart on code changes
#   scripts/start_all.sh --prod --fresh-memory # other flags pass through to scripts/run_demo.py
#   scripts/start_all.sh --turbopack           # bundle with Turbopack instead of webpack
#
# Runs from any directory; start.command at the repo root runs it with --open on a double
# click. Creates .venv (Python 3.11+) and reinstalls requirements.txt whenever it or a
# package's pyproject changes, copies .env.example to .env when there is none, and reruns
# `npm ci` in examples/ whenever package-lock.json changes. It then stops this checkout's
# servers from an earlier run (anything else on a port is left alone and the server moves to
# the next free port), so what starts is always the code on disk, and runs each vertical's API
# under scripts/run_demo.py, restarting when its Python, data, or skill files change. The
# unified app (examples/unified-web, :3300) runs the retail storefront and portal, the travel
# storefront, and the telecom and ticketing portals as one app against those APIs. With
# --separate-apps each vertical runs its own storefront and portal too, and the demo hub
# (examples/hub/index.html, :3200) shows them in one page. Requests to localhost bypass any
# HTTP proxy the shell exports. Ctrl-C stops everything. The web apps bundle with webpack by default: Turbopack cannot load
# next/font/google files that Google Fonts serves from /l/font?kit=... URLs.

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ALL_VERTICALS=(retail travel telecom entertainment)
GREEN=$'\033[32m' YELLOW=$'\033[33m' RED=$'\033[31m' DIM=$'\033[2m' RESET=$'\033[0m'

usage() { sed -n '5,/^$/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'; }
step() { echo "${GREEN}==>${RESET} $*"; }
warn() { echo "${YELLOW}$*${RESET}" >&2; }
die() { echo "${RED}error:${RESET} $*" >&2; exit 1; }

VERTICALS=()
DEMO_FLAGS=()
BUNDLER=(--webpack)
RELOAD=(--reload)
STOP_ONLY=0
OPEN=0
SEPARATE=0
for arg in "$@"; do
  case "$arg" in
    -h|--help) usage; exit 0 ;;
    --turbopack) BUNDLER=() ;;
    --no-reload) RELOAD=() ;;
    --stop) STOP_ONLY=1 ;;
    --open) OPEN=1 ;;
    --separate-apps) SEPARATE=1 ;;
    --no-reuse|--restart|--reload) ;;  # what this script always does
    --merchant|--all|--api-only|--web-only|--api-port|--api-port=*|--no-install)
      die "$arg is set per vertical by this script; use scripts/run_demo.py for it" ;;
    -*) DEMO_FLAGS+=("$arg") ;;
    *)
      [[ " ${ALL_VERTICALS[*]} " == *" $arg "* ]] \
        || die "unknown vertical: $arg (one of: ${ALL_VERTICALS[*]})"
      VERTICALS+=("$arg") ;;
  esac
done
[[ ${#VERTICALS[@]} -gt 0 ]] || VERTICALS=("${ALL_VERTICALS[@]}")

cd "$REPO_ROOT"

# An HTTP proxy the shell exports must not carry calls between the local servers, nor the
# API's calls to a model server on this machine.
for name in NO_PROXY no_proxy; do
  current="${!name:-}"
  for host in localhost 127.0.0.1 ::1; do
    [[ ",$current," == *",$host,"* ]] || current="${current:+$current,}$host"
  done
  export "$name=$current"
done

# A file's content fingerprint, for "did this change since the last install".
fingerprint() { cat "$@" 2>/dev/null | shasum -a 256 | cut -d' ' -f1; }

# Python: the repo's .venv, created from the first interpreter that is 3.11 or newer.
step "Python environment"
PYTHON="$REPO_ROOT/.venv/bin/python"
if [[ ! -x "$PYTHON" ]]; then
  BASE=""
  for candidate in python3.13 python3.12 python3.11 python3; do
    if command -v "$candidate" >/dev/null 2>&1 \
      && "$candidate" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 11) else 1)'; then
      BASE="$candidate"
      break
    fi
  done
  [[ -n "$BASE" ]] || die "Python 3.11+ is required"
  echo "  creating .venv with $("$BASE" --version)"
  "$BASE" -m venv "$REPO_ROOT/.venv"
fi
MODULES="commerce_common, shopping_agent, shopping_agent_runtime, merchant_agent"
MODULES+=", merchant_agent_runtime, fastapi, uvicorn, dotenv"
PY_STAMP="$REPO_ROOT/.venv/.requirements-fingerprint"
PY_PRINT="$(fingerprint requirements.txt */pyproject.toml */*/pyproject.toml)"
if ! "$PYTHON" -c "import $MODULES" 2>/dev/null || [[ "$(cat "$PY_STAMP" 2>/dev/null)" != "$PY_PRINT" ]]; then
  echo "  installing requirements.txt (new, or changed since the last install)"
  "$PYTHON" -m pip install -q -r requirements.txt
  echo "$PY_PRINT" >"$PY_STAMP"
fi
echo "  ${DIM}$("$PYTHON" --version) at .venv${RESET}"

# This checkout's servers from an earlier run go first, so every server below runs the
# code on disk; a port held by any other program is left alone.
step "Stopping earlier servers"
for vertical in "${VERTICALS[@]}"; do
  "$PYTHON" scripts/run_demo.py "$vertical" --stop | sed 's/^/  /'
done
# The unified app's dev server from an earlier run: matched by the directory it runs in.
UNIFIED_DIR="$REPO_ROOT/examples/unified-web"
for port in $(seq 3300 3309); do
  for pid in $(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null); do
    if [[ "$(lsof -a -p "$pid" -d cwd -Fn 2>/dev/null | sed -n 's/^n//p')" == "$UNIFIED_DIR" ]]; then
      # Started in its own process group (below), so the group is the server and its children.
      group="$(ps -o pgid= -p "$pid" | tr -d ' ')"
      if [[ -n "$group" && "$group" != "$(ps -o pgid= -p $$ | tr -d ' ')" ]]; then
        kill -- "-$group" 2>/dev/null
      else
        kill "$pid" 2>/dev/null
      fi
      echo "  ${DIM}Stopped the earlier unified app on :$port.${RESET}"
    fi
  done
done
# The demo hub's static server from an earlier run: matched by the directory it serves.
HUB_DIR="$REPO_ROOT/examples/hub"
for port in $(seq 3200 3209); do
  for pid in $(lsof -nP -iTCP:"$port" -sTCP:LISTEN -t 2>/dev/null); do
    if ps -o command= -p "$pid" | grep -q -- "--directory $HUB_DIR"; then
      kill "$pid" 2>/dev/null && echo "  ${DIM}Stopped the earlier demo hub on :$port.${RESET}"
    fi
  done
done
[[ $STOP_ONLY -eq 0 ]] || exit 0

# Credentials: the example APIs read the repo-root .env.
step "Credentials"
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "  created .env from .env.example"
fi
# The provider and key the APIs will use, resolved the way they resolve them.
PROVIDER_STATUS="$("$PYTHON" - <<'PY'
import os, sys
sys.path.insert(0, "examples")
from dotenv import load_dotenv
load_dotenv(".env", override=False)
from demo_common.model_provider import resolve_provider
try:
    p = resolve_provider()
except ValueError as error:
    print(f"error|{error}")
else:
    print(f"{'ok' if p.has_key() else 'nokey'}|{p.label}|{p.model or 'default model'}|{p.key_hint}")
PY
)"
IFS='|' read -r KEY_STATE PROVIDER_LABEL PROVIDER_MODEL KEY_HINT <<<"$PROVIDER_STATUS"
case "$KEY_STATE" in
  ok) echo "  ${DIM}$PROVIDER_LABEL, $PROVIDER_MODEL; key set${RESET}" ;;
  nokey)
    warn "  No API key for $PROVIDER_LABEL: browsing and /showcase work, chat returns an error event."
    warn "  Set $KEY_HINT in $REPO_ROOT/.env (MODEL_PROVIDER picks the model) and rerun." ;;
  *) die "model settings in .env: $PROVIDER_LABEL" ;;
esac

# Node: the eight web apps share one npm workspace at examples/.
step "Web workspace"
command -v node >/dev/null 2>&1 || die "Node 22 is required"
NODE_MAJOR="$(node -p 'process.versions.node.split(".")[0]')"
[[ "$NODE_MAJOR" -ge 22 ]] || warn "  Node $(node --version) found; the web apps are built for Node 22."
NPM_STAMP="$REPO_ROOT/examples/node_modules/.lock-fingerprint"
NPM_PRINT="$(fingerprint examples/package-lock.json)"
if [[ ! -x examples/node_modules/.bin/next || "$(cat "$NPM_STAMP" 2>/dev/null)" != "$NPM_PRINT" ]]; then
  echo "  running npm ci in examples/ (new, or package-lock.json changed)"
  (cd examples && npm ci --no-audit --no-fund)
  echo "$NPM_PRINT" >"$NPM_STAMP"
fi
echo "  ${DIM}node $(node --version)${RESET}"

# API ports are assigned here so the verticals do not race for the same free port.
default_port() {
  case "$1" in retail) echo 8000 ;; travel) echo 8001 ;; telecom) echo 8002 ;; entertainment) echo 8003 ;; esac
}
port_busy() { (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; }
step "API ports"
TAKEN=" "
NEXT_PORT=8010
API_PORTS=()
for vertical in "${VERTICALS[@]}"; do
  port="$(default_port "$vertical")"
  if port_busy "$port"; then
    while port_busy "$NEXT_PORT" || [[ "$TAKEN" == *" $NEXT_PORT "* ]]; do NEXT_PORT=$((NEXT_PORT + 1)); done
    warn "  :$port is in use by another program; the $vertical API takes :$NEXT_PORT."
    port="$NEXT_PORT"
  fi
  TAKEN+="$port "
  API_PORTS+=("$port")
  echo "  ${DIM}$vertical :$port${RESET}"
done

# Start each vertical under run_demo.py, which starts its web apps and stops its own tree.
PIDS=()
OPENER=""
UNIFIED_PID=""
stop_all() {
  trap - INT TERM EXIT
  [[ -z "$OPENER" ]] || kill "$OPENER" 2>/dev/null || true
  [[ -z "$UNIFIED_PID" ]] || kill -TERM -- "-$UNIFIED_PID" 2>/dev/null || true
  [[ ${#PIDS[@]} -gt 0 ]] || return 0
  echo
  step "Stopping ${#PIDS[@]} vertical(s)"
  for pid in "${PIDS[@]}"; do kill -TERM "$pid" 2>/dev/null || true; done
  wait 2>/dev/null || true
}
trap stop_all EXIT
trap 'exit 130' INT TERM

# Each vertical's API; its own storefront and portal only with --separate-apps.
SURFACES=(--api-only)
[[ $SEPARATE -eq 0 ]] || SURFACES=(--all)
step "Starting ${VERTICALS[*]}"
for i in "${!VERTICALS[@]}"; do
  "$PYTHON" scripts/run_demo.py "${VERTICALS[$i]}" "${SURFACES[@]}" --no-install --no-reuse \
    --api-port "${API_PORTS[$i]}" ${RELOAD[@]+"${RELOAD[@]}"} \
    ${BUNDLER[@]+"${BUNDLER[@]}"} ${DEMO_FLAGS[@]+"${DEMO_FLAGS[@]}"} &
  PIDS+=("$!")
done

# The demo hub, with the separate apps: one static page that frames them at their live ports.
if [[ $SEPARATE -eq 1 ]]; then
  HUB_PORT=3200
  while port_busy "$HUB_PORT"; do HUB_PORT=$((HUB_PORT + 1)); done
  "$PYTHON" -m http.server "$HUB_PORT" --bind 127.0.0.1 --directory "$HUB_DIR" >/dev/null 2>&1 &
  PIDS+=("$!")
  echo "  ${GREEN}demo hub${RESET}         http://localhost:$HUB_PORT  ${DIM}(every storefront and portal in one page)${RESET}"
fi

# The unified app: the five hosted apps behind one rail, each talking to its vertical's API at
# the port assigned above (a vertical not started here shows as unreachable inside it).
UNIFIED_PORT=3300
while port_busy "$UNIFIED_PORT"; do UNIFIED_PORT=$((UNIFIED_PORT + 1)); done
UNIFIED_ENV=()
for i in "${!VERTICALS[@]}"; do
  name="$(echo "${VERTICALS[$i]}" | tr '[:lower:]' '[:upper:]')"
  UNIFIED_ENV+=("NEXT_PUBLIC_${name}_API_URL=http://localhost:${API_PORTS[$i]}")
done
# Its own process group (as run_demo.py gives each server), so stopping it takes its children.
(cd "$UNIFIED_DIR" && exec "$PYTHON" -c 'import os, sys; os.setsid(); os.execvp(sys.argv[1], sys.argv[1:])' \
  env "${UNIFIED_ENV[@]}" "$REPO_ROOT/examples/node_modules/.bin/next" dev --webpack --port "$UNIFIED_PORT") \
  > >(sed -u "s/^/${DIM}[unified-web]${RESET} /") 2>&1 &
UNIFIED_PID="$!"
PIDS+=("$UNIFIED_PID")
echo "  ${GREEN}unified app${RESET}      http://localhost:$UNIFIED_PORT  ${DIM}(five apps as one: rail on the left)${RESET}"

# --open: the unified app, once it answers.
if [[ $OPEN -eq 1 ]]; then
  (
    url="http://localhost:$UNIFIED_PORT"
    for _ in $(seq 1 240); do
      curl -s -o /dev/null -m 2 "$url" && break
      sleep 1
    done
    if command -v open >/dev/null 2>&1; then open "$url"; elif command -v xdg-open >/dev/null 2>&1; then xdg-open "$url"; fi
  ) &
  OPENER="$!"
fi

echo "${DIM}Each vertical prints its API's URL when it is up; Ctrl-C stops everything, and"
echo "scripts/start_all.sh --stop stops servers a closed terminal left running.${RESET}"
# A vertical that fails stops the rest; one that exits cleanly (everything reused) is dropped.
while [[ ${#PIDS[@]} -gt 0 ]]; do
  RUNNING=()
  for pid in "${PIDS[@]}"; do
    if kill -0 "$pid" 2>/dev/null; then
      RUNNING+=("$pid")
      continue
    fi
    status=0
    wait "$pid" || status=$?
    if [[ $status -ne 0 ]]; then
      warn "A vertical exited with code $status; stopping the rest."
      exit "$status"
    fi
  done
  PIDS=("${RUNNING[@]+"${RUNNING[@]}"}")
  sleep 1
done
