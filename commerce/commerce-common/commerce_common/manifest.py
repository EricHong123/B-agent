# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Resolve a Managed Agent manifest (``agent.yaml``) into a ``/v1/agents`` request body:
``system_file`` is inlined, ``skills[].path`` entries become Skills API references
(placeholders until ``skill_ids`` supplies uploaded ids), ``${VAR}`` placeholders come
from the environment, and the constraints the API enforces are checked first.

    python -m commerce_common.manifest path/to/agent.yaml
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import re
import sys
from pathlib import Path
from typing import Any

import yaml

logger = logging.getLogger(__name__)

ENV_VAR = re.compile(r"\$\{([A-Z][A-Z0-9_]*)\}")
# A leading HTML comment in a system file documents the file for the repo; it is not
# part of the deployed prompt.
HTML_COMMENT = re.compile(r"\A\s*<!--.*?-->\s*", re.DOTALL)


class ManifestError(ValueError):
    pass


def load_manifest(path: Path) -> dict[str, Any]:
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError as error:
        raise ManifestError(f"{path}: invalid YAML: {error}") from error
    if not isinstance(data, dict):
        raise ManifestError(f"{path}: expected a YAML mapping")
    return data


def skill_entries(manifest: dict[str, Any], base: Path) -> list[tuple[str, Path]]:
    """``(name, directory)`` for every ``skills[].path`` entry; each must hold a SKILL.md."""
    entries: list[tuple[str, Path]] = []
    for entry in manifest.get("skills") or []:
        if not isinstance(entry, dict) or "path" not in entry:
            continue  # already an API-shaped entry
        skill_dir = (base / str(entry["path"])).resolve()
        if not skill_dir.is_dir():
            raise ManifestError(f"skill path does not exist: {entry['path']}")
        if not (skill_dir / "SKILL.md").exists():
            raise ManifestError(f"skill path has no SKILL.md: {entry['path']}")
        entries.append((skill_dir.name, skill_dir))
    return entries


def substitute_env(value: Any, *, require: bool) -> Any:
    """``${VAR}`` in every string replaced from the environment; an unset variable
    warns and stays as written, or fails when ``require`` is set."""
    if isinstance(value, str):

        def replace(match: re.Match[str]) -> str:
            var = match.group(1)
            resolved = os.environ.get(var)
            if resolved is not None:
                return resolved
            if require:
                raise ManifestError(f"environment variable {var} is not set")
            logger.warning("${%s} is not set; leaving the placeholder in the output", var)
            return match.group(0)

        return ENV_VAR.sub(replace, value)
    if isinstance(value, dict):
        return {key: substitute_env(item, require=require) for key, item in value.items()}
    if isinstance(value, list):
        return [substitute_env(item, require=require) for item in value]
    return value


def validate(manifest: dict[str, Any]) -> None:
    for field in ("name", "model"):
        if not manifest.get(field):
            raise ManifestError(f"manifest needs a `{field}` field")
    server_names = {
        str(server.get("name"))
        for server in manifest.get("mcp_servers") or []
        if isinstance(server, dict)
    }
    toolset_refs = {
        str(tool.get("mcp_server_name"))
        for tool in manifest.get("tools") or []
        if isinstance(tool, dict) and tool.get("type") == "mcp_toolset"
    }
    if dangling := toolset_refs - server_names:
        raise ManifestError(f"mcp_toolset references undeclared mcp_servers: {sorted(dangling)}")
    if unreferenced := server_names - toolset_refs:
        raise ManifestError(
            f"mcp_servers not referenced by any mcp_toolset: {sorted(unreferenced)} "
            "(the Agents API rejects unreferenced servers)"
        )


def resolve(
    manifest_path: Path, skill_ids: dict[str, str] | None = None, *, require_env: bool = False
) -> dict[str, Any]:
    """The request body. Raises :class:`ManifestError` for anything the API would reject."""
    skill_ids = skill_ids or {}
    base = manifest_path.parent
    manifest = load_manifest(manifest_path)

    if (system_file := manifest.pop("system_file", None)) is not None:
        system_path = (base / str(system_file)).resolve()
        if not system_path.exists():
            raise ManifestError(f"system_file does not exist: {system_file}")
        text = system_path.read_text(encoding="utf-8")
        manifest["system"] = HTML_COMMENT.sub("", text).strip()

    if manifest.get("skills"):
        skill_entries(manifest, base)
        resolved_skills: list[Any] = []
        for entry in manifest["skills"]:
            if not isinstance(entry, dict) or "path" not in entry:
                resolved_skills.append(entry)
                continue
            name = (base / str(entry["path"])).resolve().name
            skill_id = skill_ids.get(name)
            if skill_id is None:
                skill_id = f"skill_TO_BE_UPLOADED__{name}"
                logger.warning(
                    "no uploaded skill_id for '%s'; emitting a placeholder (dry run only)", name
                )
            resolved_skills.append({"type": "custom", "skill_id": skill_id, "version": "latest"})
        manifest["skills"] = resolved_skills

    manifest = substitute_env(manifest, require=require_env)
    validate(manifest)
    return manifest


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Resolve an agent.yaml into a /v1/agents body.")
    parser.add_argument("manifest", type=Path)
    parser.add_argument(
        "--list-skills",
        action="store_true",
        help="print '<name>\\t<path>' per local skill entry and exit",
    )
    parser.add_argument(
        "--skill-id",
        action="append",
        default=[],
        metavar="NAME=SKILL_ID",
        help="an uploaded Skills API id for a skill directory name (repeatable)",
    )
    parser.add_argument(
        "--require-env", action="store_true", help="fail on an unset ${VAR} placeholder"
    )
    args = parser.parse_args(argv)
    try:
        if args.list_skills:
            for name, path in skill_entries(load_manifest(args.manifest), args.manifest.parent):
                print(f"{name}\t{path}")
            return 0
        skill_ids: dict[str, str] = {}
        for pair in args.skill_id:
            name, _, skill_id = pair.partition("=")
            if not name or not skill_id:
                raise ManifestError(f"--skill-id expects NAME=SKILL_ID, got: {pair!r}")
            skill_ids[name] = skill_id
        body = resolve(args.manifest, skill_ids, require_env=args.require_env)
        print(json.dumps(body, indent=2, ensure_ascii=False))
        return 0
    except ManifestError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    # Run as a command, the resolver's warnings go to stderr beside its errors.
    logging.basicConfig(format="%(levelname)s: %(message)s")
    raise SystemExit(main())
