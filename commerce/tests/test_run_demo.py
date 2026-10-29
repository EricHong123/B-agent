# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""scripts/run_demo.py's helpers for the one-click start: the proxy bypass, the reloader's
watch list, the ports a vertical records for the demo hub, and which servers count as ours."""

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "run_demo.py"
spec = importlib.util.spec_from_file_location("run_demo", SCRIPT)
assert spec and spec.loader
run_demo = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = run_demo
spec.loader.exec_module(run_demo)


def test_localhost_joins_no_proxy_without_dropping_what_was_there():
    env = {"NO_PROXY": "corp.example,localhost", "HTTP_PROXY": "http://proxy:8080"}
    run_demo.bypass_proxy_for_localhost(env)
    assert env["NO_PROXY"] == "corp.example,localhost,127.0.0.1,::1"
    assert env["no_proxy"] == "localhost,127.0.0.1,::1"


def test_the_reloader_follows_data_and_skills_but_not_runtime_dot_files():
    options = run_demo.reload_options("travel")
    watched = [options[i + 1] for i, option in enumerate(options) if option == "--reload-dir"]
    assert str(run_demo.EXAMPLES_DIR / "travel" / "data") in watched
    assert str(run_demo.REPO_ROOT / "shopping-agent") in watched
    assert "SKILL.md" in options and "*.json" in options
    assert options[-2:] == ["--reload-exclude", ".*"]


def test_a_vertical_records_its_live_ports_for_the_hub(tmp_path, monkeypatch):
    monkeypatch.setattr(run_demo, "HUB_RUNTIME", tmp_path / "runtime")
    webs = [
        ("storefront", run_demo.EXAMPLES_DIR / "retail" / "storefront-web", 3004),
        ("merchant portal", run_demo.EXAMPLES_DIR / "retail" / "merchant-web", 3104),
    ]
    path = run_demo.record_ports("retail", 8013, webs)
    assert json.loads(path.read_text()) == {"api": 8013, "storefront": 3004, "portal": 3104}


def test_only_this_checkouts_servers_count_as_ours(monkeypatch):
    examples = str(run_demo.EXAMPLES_DIR)
    owners = {
        1: (f"python -m uvicorn retail.api.main:app --app-dir {examples} --port 8000", "/"),
        2: ("python -m uvicorn retail.api.main:app --app-dir /elsewhere/examples", "/elsewhere"),
        3: ("next-server (v16)", f"{examples}/retail/merchant-web"),
        4: ("next-server (v16)", "/elsewhere/examples/retail/merchant-web"),
        5: ("uvicorn app.gateway.app:app --port 8001", "/other/project"),
    }
    monkeypatch.setattr(run_demo, "process_owner", lambda pid: owners[pid])
    assert [pid for pid in owners if run_demo.ours(pid, "retail")] == [1, 3]
    assert not run_demo.ours(1, "travel")
