# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Plumbing the two reference MCP servers share: one executor per connection, the
registry's descriptions, the outcome-to-result mapping, and the loopback-only bind.
The servers verify no credential of their own, so they refuse to bind off loopback
unless the operator states that an authenticating gateway sits in front. Importing this
module requires ``mcp``.
"""

from __future__ import annotations

import json
import logging
import os
from collections.abc import Callable, Mapping
from typing import Any
from weakref import WeakKeyDictionary

from mcp.server.fastmcp import Context, FastMCP

from .streaming import ToolOutcome

logger = logging.getLogger(__name__)

_LOOPBACK_HOSTS = {"127.0.0.1", "localhost", "::1"}


def enforce_local_only_bind(host: str, *, server: str, unsafe_env_var: str) -> None:
    """Exit unless ``host`` is loopback or ``unsafe_env_var`` is set to ``1``."""
    if host in _LOOPBACK_HOSTS or os.environ.get(unsafe_env_var) == "1":
        return
    raise SystemExit(
        f"refusing to bind the {server} MCP server to '{host}': this reference server "
        "has no inbound authentication, and a caller that reaches the port directly "
        "bypasses the platform's approval step. Keep it on 127.0.0.1 behind your own "
        f"authenticating gateway, and set {unsafe_env_var}=1 only once that gateway exists."
    )


def result_text(outcome: ToolOutcome) -> str:
    """The tool's text; a failure raises so the client sees ``isError``, while a held
    call returns its text like any other result."""
    if outcome.is_error:
        raise ValueError(outcome.result_text)
    return outcome.result_text


class ConnectionExecutors:
    """One executor, and so one provenance record, per client connection; entries go
    away with the connection."""

    def __init__(self, factory: Callable[[], Any]) -> None:
        self._factory = factory
        self._executors: WeakKeyDictionary[Any, Any] = WeakKeyDictionary()

    def get(self, ctx: Context) -> Any:
        executor = self._executors.get(ctx.session)
        if executor is None:
            executor = self._executors[ctx.session] = self._factory()
        return executor

    async def call(self, ctx: Context, name: str, arguments: dict[str, Any]) -> str:
        return result_text(await self.get(ctx).execute(name, arguments))


def registrar(
    server: FastMCP, contracts: Mapping[str, Mapping[str, Any]], overrides: Mapping[str, str]
) -> Callable[[str], Callable[[Any], Any]]:
    """``register(name)`` decorates a handler as the MCP tool ``name`` under the registry's
    description (or the documented hosted-path override) and the registry's input schema,
    so ``list_tools`` publishes the same contract the other two paths send. A tool the
    deployment's config switches off is absent from ``contracts`` and is left unregistered.
    The handler's signature still parses the arguments at call time; the ``status``
    property is dropped because nothing on the hosted path shows the line."""

    def register(name: str) -> Callable[[Any], Any]:
        if name not in contracts:
            return lambda handler: handler
        decorate = server.tool(
            name=name, description=overrides.get(name, str(contracts[name]["description"]))
        )

        def wrap(handler: Any) -> Any:
            registered = decorate(handler)
            tool = server._tool_manager.get_tool(name)
            if tool is not None:
                tool.parameters = published_schema(contracts[name]["input_schema"])
            return registered

        return wrap

    return register


def published_schema(input_schema: Mapping[str, Any]) -> dict[str, Any]:
    """The registry's schema as the MCP server publishes it: a copy without ``status``."""
    schema = json.loads(json.dumps(input_schema))
    schema.get("properties", {}).pop("status", None)
    if "required" in schema:
        schema["required"] = [name for name in schema["required"] if name != "status"]
    return schema


def run(server: FastMCP, *, url: str, warning: str) -> None:
    """Serve over streamable HTTP. ``FastMCP`` configures root logging when it is built,
    so both lines reach stderr."""
    logger.info("MCP server on %s", url)
    logger.warning("%s", warning)
    server.run(transport="streamable-http")
