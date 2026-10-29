# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Each role's runtime, SDK, and MCP paths: one registry, the same bytes, the same memory settings."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from typing import Any

import merchant_mcp_server
import pytest
import storefront_mcp_server
from claude_agent_sdk import ClaudeAgentOptions
from mcp.shared.memory import create_connected_server_and_client_session

import merchant_agent_sdk
import shopping_agent_sdk
from commerce_common.agent_sdk import SKILL_TOOL_ADAPTER
from commerce_common.execution import LOAD_SKILL, STATUS_FIELD
from commerce_common.fencing import Fence
from commerce_common.manifest import load_manifest
from commerce_common.memory import (
    MEMORY_DISABLED_TEXT,
    MEMORY_WRITE_REJECTED_TEXT,
    InMemoryMemoryStore,
    MemoryWriteFilter,
)
from commerce_common.testing import (
    FakeClient,
    SpyStore,
    extraction_client,
    result_text,
    text_message,
    tool_use_message,
)
from merchant_agent.executor import MerchantToolExecutor
from merchant_agent.fencing import MERCHANT_FENCE
from merchant_agent.prompt import build_static_system as merchant_static_system
from merchant_agent_runtime import MerchantAgent
from shopping_agent.executor import ShoppingToolExecutor
from shopping_agent.fencing import STOREFRONT_FENCE
from shopping_agent.prompt import build_static_system as shopping_static_system
from shopping_agent_runtime import ShoppingAgent

REPO_ROOT = Path(__file__).resolve().parents[1]
KEY, VALUE = "preferred_hours", "prefers mornings"
IDENTIFIER = "card on file 4000 1234 5678 9010"
TURN = [{"role": "user", "content": "remember that"}]
NO_MATCH = "a query nothing in the fixture matches"
STATUS = "Checking"  # the line the person waiting sees; the executor drops it


@dataclass(frozen=True)
class Role:
    agent: type
    executor: type
    sdk: ModuleType
    toolset: type
    sdk_tools: Callable[[Any], list]
    static_system: Callable[..., str]
    server: ModuleType
    manifest: Path
    fence: Fence
    subject_of: Callable[[Any], str]
    mcp_subject: str
    search: tuple[str, str]  # the search tool and a query the fake backend answers


ROLES = {
    "shopping": Role(
        agent=ShoppingAgent,
        executor=ShoppingToolExecutor,
        sdk=shopping_agent_sdk,
        toolset=shopping_agent_sdk.ShoppingToolset,
        sdk_tools=shopping_agent_sdk.build_shopping_sdk_tools,
        static_system=shopping_static_system,
        server=storefront_mcp_server,
        manifest=REPO_ROOT / "shopping-agent" / "managed-agents" / "shopping-agent" / "agent.yaml",
        fence=STOREFRONT_FENCE,
        subject_of=lambda session: session.user_id,
        mcp_subject=storefront_mcp_server.DEMO_USER_ID,
        search=("search_products", "tent"),
    ),
    "merchant": Role(
        agent=MerchantAgent,
        executor=MerchantToolExecutor,
        sdk=merchant_agent_sdk,
        toolset=merchant_agent_sdk.MerchantToolset,
        sdk_tools=merchant_agent_sdk.build_merchant_sdk_tools,
        static_system=merchant_static_system,
        server=merchant_mcp_server,
        manifest=REPO_ROOT / "merchant-agent" / "managed-agents" / "merchant-agent" / "agent.yaml",
        fence=MERCHANT_FENCE,
        subject_of=lambda session: session.merchant_id,
        mcp_subject=merchant_mcp_server.DEMO_MERCHANT_ID,
        search=("search_listings", "decals"),
    ),
}


@pytest.fixture(params=list(ROLES))
def role(request) -> str:
    return request.param


@pytest.fixture
def spec(role) -> Role:
    return ROLES[role]


# -- one handle per path -----------------------------------------------------------------


@dataclass
class Handle:
    """``call`` runs a tool; ``subject`` is the path's memory key; ``surface`` lists its tools."""

    call: Callable[[str, dict[str, Any]], Awaitable[tuple[str, bool]]]
    subject: str
    surface: Callable[[], Awaitable[list[tuple[str, str | None, dict[str, Any]]]]] | None = None


def _runtime(spec: Role, f: Any, store: Any, write_filter: Any, config: Any) -> Handle:
    agent = spec.agent(
        backend=f.backend,
        skills=f.skills,
        config=config,
        memory_store=store,
        memory_write_filter=write_filter,
        client=FakeClient([]),
    )
    executor = spec.executor(
        backend=f.backend,
        config=config,
        skills=f.skills,
        session=f.session,
        state=f.state,
        memory=agent.memory,
    )

    async def call(name: str, args: dict[str, Any]) -> tuple[str, bool]:
        outcome = await executor.execute(name, {"status": STATUS, **args})
        return outcome.result_text, outcome.is_error

    return Handle(call, spec.subject_of(f.session))


def _sdk(spec: Role, f: Any, store: Any, write_filter: Any, config: Any) -> Handle:
    toolset = spec.toolset(
        backend=f.backend,
        config=config,
        session=f.session,
        memory_store=store,
        memory_write_filter=write_filter,
    )
    handlers = {tool.name: tool for tool in spec.sdk_tools(toolset)}

    async def call(name: str, args: dict[str, Any]) -> tuple[str, bool]:
        result = await handlers[name].handler({"status": STATUS, **args})
        return result_text(result), bool(result.get("is_error"))

    async def surface():
        return [(t.name, t.description, t.input_schema) for t in handlers.values()]

    return Handle(call, spec.subject_of(f.session), surface)


def _mcp(spec: Role, f: Any, store: Any, write_filter: Any, config: Any) -> Handle:
    server = spec.server.build_server(f.backend, store, config, memory_write_filter=write_filter)

    async def call(name: str, args: dict[str, Any]) -> tuple[str, bool]:
        async with create_connected_server_and_client_session(server) as client:
            result = await client.call_tool(name, args)
        return result_text(result), bool(result.isError)

    async def surface():
        async with create_connected_server_and_client_session(server) as client:
            listed = (await client.list_tools()).tools
        return [(t.name, t.description, t.inputSchema) for t in listed]

    return Handle(call, spec.mcp_subject, surface)


PATHS = {"runtime": _runtime, "sdk": _sdk, "mcp": _mcp}


@pytest.fixture
def builders(spec, backend, skills, config, session, state):
    """``builders[path](store, write_filter=..., **config_updates)`` -> a Handle over the shared backend."""
    fixtures = SimpleNamespace(backend=backend, skills=skills, session=session, state=state)

    def builder(path: str):
        def build(store: Any = None, *, write_filter: Any = None, **updates: Any) -> Handle:
            configured = config.model_copy(update=updates) if updates else config
            return PATHS[path](
                spec, fixtures, store or InMemoryMemoryStore(), write_filter, configured
            )

        return build

    return {path: builder(path) for path in PATHS}


@pytest.fixture(params=list(PATHS))
def build(request, builders):
    return builders[request.param]


# -- registration ----------------------------------------------------------------------


def test_sdk_registers_the_registry_under_its_contracts_and_allows_exactly_those(spec):
    options, toolset = spec.sdk.make_options()
    handlers = {tool.name: tool for tool in spec.sdk_tools(toolset)}
    contracts = spec.sdk.tool_contracts(toolset.config)
    assert list(handlers) == spec.sdk.tool_names(toolset.config)
    assert LOAD_SKILL in contracts and LOAD_SKILL not in handlers
    for name, handler in handlers.items():
        assert handler.description == contracts[name]["description"]
        assert handler.input_schema == contracts[name]["input_schema"]
    assert options.allowed_tools == [spec.sdk.mcp_tool_name(name) for name in handlers]
    assert options.allowed_tools == spec.sdk.allowed_tool_names(toolset.config)


def test_sdk_options_mount_only_the_in_process_server_over_the_static_prompt(spec):
    options, toolset = spec.sdk.make_options()
    assert isinstance(options, ClaudeAgentOptions)
    assert options.model == toolset.config.model
    assert options.permission_mode == "dontAsk" and options.max_turns == 16
    assert set(options.mcp_servers) == {spec.sdk.SERVER_NAME}
    assert options.mcp_servers[spec.sdk.SERVER_NAME]["type"] == "sdk"
    assert options.tools == ["Skill"] and options.setting_sources == ["project"]
    assert Path(options.cwd) == spec.sdk.RUNTIME_ROOT
    static = spec.static_system(toolset.config, spec.sdk.load_skill_registry())
    assert options.system_prompt.startswith(static) and options.system_prompt.endswith(
        SKILL_TOOL_ADAPTER
    )


def test_sdk_materializes_the_skill_directories_as_the_project_skills(spec):
    options, _ = spec.sdk.make_options()
    source_names = sorted(
        p.name for p in spec.sdk.SKILLS_DIR.iterdir() if (p / "SKILL.md").is_file()
    )
    assert options.skills == source_names
    project_skills = Path(options.cwd) / ".claude" / "skills"
    assert sorted(p.name for p in project_skills.iterdir()) == source_names
    for name in source_names:
        materialized = (project_skills / name / "SKILL.md").read_text(encoding="utf-8")
        assert materialized == (spec.sdk.SKILLS_DIR / name / "SKILL.md").read_text(encoding="utf-8")


def _manifest_mcp_tools(manifest: Path) -> set[str]:
    return {
        config["name"]
        for entry in load_manifest(manifest)["tools"]
        if entry.get("type") == "mcp_toolset"
        for config in entry["configs"]
        if config.get("enabled")
    }


async def test_mcp_server_lists_the_manifests_tools_under_registry_contracts(
    spec, builders, config
):
    listed = await builders["mcp"]().surface()
    names = {name for name, _, _ in listed}
    assert names == _manifest_mcp_tools(spec.manifest)
    assert not any(name.startswith("present_") for name in names) and LOAD_SKILL not in names
    # Contracts for the same config the server was built with: bounds such as maxItems come
    # from it.
    registry = spec.sdk.tool_contracts(config)
    overrides = spec.server.HOSTED_DESCRIPTION_OVERRIDES
    assert set(overrides) <= names
    for name, description, schema in listed:
        assert description == overrides.get(name, registry[name]["description"]), name
        # Nothing on the hosted path shows the status line, so the tools do not take it.
        assert STATUS_FIELD not in schema["properties"], name
        # The published schema is the registry's (enums, bounds, field descriptions), not
        # one derived from the handler's signature.
        expected = dict(registry[name]["input_schema"]["properties"])
        expected.pop(STATUS_FIELD, None)
        assert schema["properties"] == expected, name


def test_mcp_server_exposes_the_streamable_http_transport(spec, backend):
    assert (
        spec.server.build_server(backend, InMemoryMemoryStore()).streamable_http_app() is not None
    )


async def test_every_path_takes_a_deployments_own_executor_class(
    spec, backend, skills, config, session, state
):
    class Wording(spec.executor):
        unavailable_text = "{name} is switched off for maintenance."

    async def down(*args, **kwargs):
        raise RuntimeError("maintenance")

    tool, query = spec.search
    setattr(backend, tool, down)
    script = [tool_use_message(tool, {"query": query}), text_message("It is down.")]
    agent = spec.agent(
        backend=backend,
        skills=skills,
        config=config,
        client=FakeClient(script),
        executor_class=Wording,
    )
    events = [
        e async for e in agent.stream_turn([{"role": "user", "content": "hi"}], session, state)
    ]
    (result,) = [e.data for e in events if e.type == "tool_result"]
    assert result["summary"] == f"{tool} is switched off for maintenance."
    toolset = spec.toolset(backend=backend, config=config, executor_class=Wording)
    assert isinstance(toolset.executor, Wording)
    handlers = {t.name: t for t in spec.sdk_tools(toolset)}
    assert result_text(await handlers[tool].handler({"query": query})) == (
        f"{tool} is switched off for maintenance."
    )
    server = spec.server.build_server(
        backend, InMemoryMemoryStore(), config, executor_class=Wording
    )
    async with create_connected_server_and_client_session(server) as client:
        result = await client.call_tool(tool, {"query": query})
    assert result.isError
    assert result_text(result).endswith(f"{tool} is switched off for maintenance.")


# -- result bytes ----------------------------------------------------------------------


async def test_search_results_are_byte_identical_across_the_paths(spec, builders):
    tool, query = spec.search
    for text in (query, NO_MATCH):
        replies = [await builders[path]().call(tool, {"query": text}) for path in PATHS]
        assert replies[0] == replies[1] == replies[2] and not replies[0][1], text
    assert query in (await builders["runtime"]().call(tool, {"query": query}))[0].lower()


# -- memory settings -------------------------------------------------------------------


async def test_disabled_memory_answers_both_tools_without_touching_the_store(build):
    store = SpyStore()
    handle = build(store, enable_memory=False)
    store.seed(handle.subject, KEY, VALUE)
    saved = await handle.call("save_memory", {"key": "other", "value": "prefers evenings"})
    recalled = await handle.call("recall_memories", {"topic": "hours"})
    assert saved == recalled == (MEMORY_DISABLED_TEXT, False)
    assert store.reads == 0 and store.keys(handle.subject) == [KEY]


async def test_enabled_memory_recalls_what_earlier_sessions_saved_inside_the_roles_fence(
    spec, build
):
    store = SpyStore()
    handle = build(store)
    store.seed(handle.subject, KEY, VALUE)
    text, is_error = await handle.call("recall_memories", {"topic": "hours"})
    assert VALUE in text and text.startswith(spec.fence.open) and not is_error
    nothing, is_error = await handle.call("recall_memories", {"topic": "unrelated"})
    assert VALUE not in nothing and not is_error


async def test_save_memory_runs_the_write_filter_and_stores_the_rest(build):
    store = SpyStore()
    handle = build(store)
    text, is_error = await handle.call("save_memory", {"key": "card", "value": IDENTIFIER})
    assert is_error and MEMORY_WRITE_REJECTED_TEXT in text and "4000" not in text
    _, is_error = await handle.call("save_memory", {"key": KEY, "value": VALUE})
    assert not is_error and store.keys(handle.subject) == [KEY]
    # The status line the runtime and SDK calls carry is not part of what is stored.
    (fact,) = await store.get_facts(handle.subject)
    assert (fact.key, fact.value) == (KEY, VALUE) and STATUS not in fact.model_dump_json()


async def test_deployment_patterns_or_a_host_filter_extend_the_write_filter(build):
    store = SpyStore()
    patterned = build(store, memory_blocked_patterns=(r"(?i)\bmornings\b",))
    _, refused = await patterned.call("save_memory", {"key": KEY, "value": VALUE})
    detector = MemoryWriteFilter.build(checks=[lambda key, value: "employer" in value])
    hosted = build(store, write_filter=detector)
    _, detected = await hosted.call(
        "save_memory", {"key": "job", "value": "works for a named employer"}
    )
    assert refused and detected and store.keys(hosted.subject) == []


async def test_retention_hides_expired_facts_and_the_next_write_drops_them(build):
    store = SpyStore()
    handle = build(store, memory_retention_days=30)
    store.seed(handle.subject, KEY, VALUE, days_old=45)
    text, _ = await handle.call("recall_memories", {"topic": "hours"})
    assert VALUE not in text
    await handle.call("save_memory", {"key": "other", "value": "prefers evenings"})
    assert store.keys(handle.subject) == ["other"]

    unlimited = SpyStore()
    kept = build(unlimited)
    unlimited.seed(kept.subject, KEY, VALUE, days_old=400)
    text, _ = await kept.call("recall_memories", {"topic": "hours"})
    assert VALUE in text


@pytest.mark.parametrize("path", ["sdk", "mcp"])
async def test_registered_tools_are_identical_with_memory_on_or_off(builders, path):
    listed = await builders[path]().surface()
    assert listed == await builders[path](enable_memory=False).surface()
    assert {"save_memory", "recall_memories"} <= {name for name, _, _ in listed}


# -- the runtimes: injection and extraction --------------------------------------------


@pytest.fixture
def make_agent(spec, backend, skills, config):
    def _make(store: Any, client: Any, *, write_filter: Any = None, **updates: Any):
        return spec.agent(
            backend=backend,
            skills=skills,
            config=config.model_copy(update=updates),
            memory_store=store,
            memory_write_filter=write_filter,
            client=client,
        )

    return _make


@pytest.fixture
def subject(spec, session) -> str:
    return spec.subject_of(session)


async def _context_of(agent: Any, session: Any, state: Any) -> str:
    """The per-request context: the second system block of the request."""
    async for _ in agent.stream_turn(list(TURN), session, state):
        pass
    return json.dumps(agent.client.calls[0]["system"][1])


async def test_saved_facts_join_the_request_context_only_while_live(
    make_agent, subject, session, state
):
    cases = (({}, True), ({"enable_memory": False}, False), ({"memory_retention_days": 30}, False))
    for updates, injected in cases:
        store = SpyStore().seed(subject, KEY, VALUE, days_old=45)
        agent = make_agent(store, FakeClient([text_message("Noted.")]), **updates)
        assert (VALUE in await _context_of(agent, session, state)) is injected, updates
        assert (store.reads > 0) is updates.get("enable_memory", True)


async def test_extraction_runs_the_configured_filter_and_skips_when_disabled(
    make_agent, subject, session
):
    proposals = [
        {"key": "job", "value": "works for a named employer", "category": "context"},
        {"key": "wool", "value": "allergic to wool", "category": "constraint"},
        {"key": KEY, "value": VALUE, "category": "preference"},
    ]
    patterned = make_agent(
        SpyStore(), extraction_client(proposals), memory_blocked_patterns=(r"(?i)allerg",)
    )
    assert [f.key for f in await patterned.update_memory(list(TURN), session)] == ["job", KEY]

    detector = MemoryWriteFilter.build(checks=[lambda key, value: "employer" in value])
    store = SpyStore()
    hosted = make_agent(store, extraction_client(proposals), write_filter=detector)
    assert [f.key for f in await hosted.update_memory(list(TURN), session)] == ["wool", KEY]
    assert store.keys(subject) == ["wool", KEY]

    client = extraction_client(proposals)
    disabled = make_agent(SpyStore(), client, enable_memory=False)
    assert await disabled.update_memory(list(TURN), session) == [] and client.calls == []


async def test_a_purge_landing_during_extraction_wins(make_agent, subject, session):
    gate = asyncio.Event()
    proposal = {"key": KEY, "value": VALUE, "category": "preference"}
    client = extraction_client([proposal], before_call=lambda _: gate.wait())
    store = SpyStore().seed(subject, "older", "kept until now")
    extraction = asyncio.create_task(make_agent(store, client).update_memory(list(TURN), session))
    await asyncio.sleep(0)
    assert len(client.calls) == 1
    await store.clear(subject)  # the host's purge route
    gate.set()
    assert await extraction == [] and store.keys(subject) == []
