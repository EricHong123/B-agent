# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

import logging
import subprocess
import sys
from pathlib import Path

import pytest

from commerce_common.manifest import ManifestError, main, resolve

REPO_ROOT = Path(__file__).resolve().parents[2]
MANIFESTS = [
    REPO_ROOT / "shopping-agent" / "managed-agents" / "shopping-agent" / "agent.yaml",
    REPO_ROOT / "merchant-agent" / "managed-agents" / "merchant-agent" / "agent.yaml",
]


@pytest.mark.parametrize("manifest", MANIFESTS, ids=lambda p: p.parent.name)
def test_repo_manifests_resolve_for_a_dry_run(manifest, caplog):
    with caplog.at_level(logging.WARNING, logger="commerce_common.manifest"):
        body = resolve(manifest)
    assert body["system"] and not body["system"].startswith("<!--")
    assert all(skill["skill_id"].startswith("skill_TO_BE_UPLOADED__") for skill in body["skills"])
    assert "${" in str(body["mcp_servers"])  # the server URL stays a placeholder
    messages = [
        record.getMessage() for record in caplog.records if record.levelno == logging.WARNING
    ]
    assert any("is not set" in message for message in messages)
    assert any("dry run only" in message for message in messages)


def test_command_line_run_writes_the_warnings_to_stderr():
    completed = subprocess.run(
        [sys.executable, "-m", "commerce_common.manifest", str(MANIFESTS[0])],
        capture_output=True,
        text=True,
        check=False,
    )
    assert completed.returncode == 0
    assert completed.stdout.lstrip().startswith("{")
    assert "WARNING: no uploaded skill_id" in completed.stderr


def _write(tmp_path: Path, text: str) -> Path:
    skill = tmp_path / "skills" / "care"
    skill.mkdir(parents=True)
    (skill / "SKILL.md").write_text("---\nname: care\ndescription: d\n---\nbody")
    (tmp_path / "system.md").write_text("<!-- repo note -->\nYou are the agent.")
    manifest = tmp_path / "agent.yaml"
    manifest.write_text(text)
    return manifest


VALID = """
name: Agent
model: claude-sonnet-5
system_file: system.md
skills:
  - path: skills/care
mcp_servers:
  - name: store
    url: ${STORE_URL}
tools:
  - type: mcp_toolset
    mcp_server_name: store
"""


def test_resolution_inlines_skills_env_and_uploaded_ids(tmp_path, monkeypatch):
    monkeypatch.setenv("STORE_URL", "https://store.example/mcp")
    body = resolve(_write(tmp_path, VALID), {"care": "skill_123"}, require_env=True)
    assert body["system"] == "You are the agent."
    assert body["skills"] == [{"type": "custom", "skill_id": "skill_123", "version": "latest"}]
    assert body["mcp_servers"][0]["url"] == "https://store.example/mcp"
    assert "system_file" not in body


def test_unset_variables_fail_only_when_required(tmp_path, monkeypatch):
    monkeypatch.delenv("STORE_URL", raising=False)
    manifest = _write(tmp_path, VALID)
    assert resolve(manifest)["mcp_servers"][0]["url"] == "${STORE_URL}"
    with pytest.raises(ManifestError, match="STORE_URL"):
        resolve(manifest, require_env=True)


@pytest.mark.parametrize(
    ("edit", "message"),
    [
        (("model: claude-sonnet-5\n", ""), "needs a `model`"),
        (("mcp_server_name: store", "mcp_server_name: other"), "undeclared"),
        (("  - type: mcp_toolset\n    mcp_server_name: store\n", ""), "not referenced"),
        (("path: skills/care", "path: skills/missing"), "does not exist"),
    ],
)
def test_api_constraints_are_checked_locally(tmp_path, edit, message):
    manifest = _write(tmp_path, VALID.replace(*edit))
    with pytest.raises(ManifestError, match=message):
        resolve(manifest)


def test_cli_lists_skills_and_reports_errors(tmp_path, capsys):
    manifest = _write(tmp_path, VALID)
    assert main([str(manifest), "--list-skills"]) == 0
    assert capsys.readouterr().out.startswith("care\t")
    assert main([str(manifest), "--skill-id", "broken"]) == 1
    assert "NAME=SKILL_ID" in capsys.readouterr().err
