# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The analysis delegate: a separate model loop, run inside the analysis tool call,
whose tools are the merchant read tools plus a submission tool and, per deployment, a
SELECT-only query method and the hosted code sandbox. The brief goes in and one validated
:class:`~merchant_agent.AnalysisResult` comes out; neither the conversation nor the
gathered data crosses in the other direction. Reads go through the ordinary executor,
and only the snapshot and series they gather reach the session: listing and campaign ids
feed the staged-write gates, which an analysis run must not widen.
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, cast

from anthropic import AsyncAnthropic
from pydantic import BaseModel, ValidationError

from commerce_common.delegation import DelegateExtension, DelegationContext
from commerce_common.execution import without_status
from commerce_common.prompt_assembly import with_tool_cache_control
from commerce_common.skills import SkillRegistry
from commerce_common.streaming import AgentEvent
from commerce_common.turn import accumulate_usage, log_model_call
from merchant_agent import (
    AnalysisResult,
    AnalysisTable,
    MerchantAgentConfig,
    MerchantBackend,
    MerchantSessionState,
    check_analysis_sql,
)
from merchant_agent.analysis import (
    ANALYSIS_QUERY_TOOL,
    ANALYSIS_READ_TOOLS,
    ANALYSIS_TOOL,
    CODE_EXECUTION_TOOL_TYPE,
    REPORT_PROGRESS_TOOL,
    SUBMIT_ANALYSIS_TOOL,
    build_analysis_query_tool,
    build_analysis_system_prompt,
    build_analysis_tool_definition,
    build_report_progress_tool,
    build_submit_analysis_tool,
    cap_analysis_table,
    derive_metrics_payload,
    summarize_result_for_model,
)
from merchant_agent.executor import MerchantToolExecutor
from merchant_agent.fencing import MERCHANT_FENCE
from merchant_agent.tools.registry import build_tools

logger = logging.getLogger(__name__)

# Step lines are composed from this map only; model-authored lines arrive through
# report_progress, which sanitizes them. Keys are names of client tool_use blocks; the
# sandbox's own server_tool_use blocks are not collected, so a step that only ran code
# reads "working".
_STEP_VERBS = {
    "get_business_snapshot": "reading the snapshot",
    "query_metrics": "querying metrics",
    "get_campaign_performance": "reading campaigns",
    "search_listings": "scanning listings",
    ANALYSIS_QUERY_TOOL: "running a query",
}

# Responses that only report progress are free this many times, then count as iterations.
_PROGRESS_ONLY_GRACE = 3


def present_analysis(result: BaseModel, context: DelegationContext) -> tuple[Any, list[AgentEvent]]:
    """The result recorded on the session and rendered as a metrics card from the record."""
    analysis = cast(AnalysisResult, result)
    context.state.remember_analysis(analysis)
    return summarize_result_for_model(analysis), [
        AgentEvent.ui("metrics", derive_metrics_payload(analysis))
    ]


def build_analysis_delegate(
    client: AsyncAnthropic, backend: MerchantBackend, config: MerchantAgentConfig
) -> DelegateExtension:
    definition = build_analysis_tool_definition()
    runner = AnalysisRunner(client=client, backend=backend, config=config)
    return DelegateExtension(
        name=ANALYSIS_TOOL,
        description=definition["description"],
        input_schema=definition["input_schema"],
        result_model=AnalysisResult,
        run=runner.run,
        present=present_analysis,
    )


def backend_supports_analysis_query(backend: MerchantBackend) -> bool:
    return type(backend).execute_analysis_query is not MerchantBackend.execute_analysis_query


class AnalysisRunner:
    """Builds the delegate's tool surface once per deployment and runs one loop per call."""

    def __init__(
        self, *, client: AsyncAnthropic, backend: MerchantBackend, config: MerchantAgentConfig
    ) -> None:
        self._client = client
        self._backend = backend
        self._config = config
        self._system = build_analysis_system_prompt(config)
        self._sql_supported = backend_supports_analysis_query(backend)
        self._tools = self._build_tools()

    def _build_tools(self) -> list[dict[str, Any]]:
        registry = build_tools(self._config, [])
        # With query support, analysis_sql_only leaves the per-series reads off the
        # surface; without it, the reads are the only data source.
        sql_only = self._sql_supported and self._config.analysis_sql_only
        # Nobody watches the delegate's calls, so its reads carry no status line.
        tools = (
            []
            if sql_only
            else [
                without_status(tool) for tool in registry if tool.get("name") in ANALYSIS_READ_TOOLS
            ]
        )
        tools.append(build_submit_analysis_tool())
        tools.append(build_report_progress_tool())
        if self._sql_supported:
            tools.append(build_analysis_query_tool())
        if self._config.analysis_use_code_execution:
            # The sandbox calls the tools itself, so bulk data stays out of the delegate's text.
            for tool in tools:
                tool["allowed_callers"] = [CODE_EXECUTION_TOOL_TYPE]
            tools.append({"type": CODE_EXECUTION_TOOL_TYPE, "name": "code_execution"})
        return with_tool_cache_control(tools)

    async def _task_brief(self, session: Any, args: dict[str, Any]) -> str:
        """The opening message: the brief, plus the backend's schema notes when queries
        are supported. The brief's strings are cut to size again here; the schema's limits
        describe what the model was asked to send, not what it sent."""

        def _clamp(value: Any, limit: int = 300) -> Any:
            if isinstance(value, str):
                return value[:limit]
            if isinstance(value, list):
                return [_clamp(item, 80) for item in value[:8]]
            return value

        brief = {key: _clamp(value) for key, value in args.items() if value}
        text = "Analysis task:\n" + json.dumps(brief, ensure_ascii=False, indent=2)
        if self._sql_supported:
            try:
                schema = await self._backend.get_analysis_schema(session)
            except Exception:  # the run proceeds without schema notes
                logger.warning("get_analysis_schema failed; briefing without it", exc_info=True)
                schema = None
            if schema:
                text += "\n\nQueryable tables (reference data):\n" + MERCHANT_FENCE.fence_payload(
                    {"schema": schema}, self._config.max_fenced_chars
                )
        return text

    async def run(self, context: DelegationContext, args: dict[str, Any]) -> AnalysisResult:
        """The validated submission. Raises ``ValueError``, naming what was gathered,
        when the iteration or wall-clock budget runs out first."""
        trace: list[str] = []
        series_names: list[str] = []
        try:
            async with asyncio.timeout(self._config.analysis_timeout_s):
                return await self._run_loop(context, args, trace, series_names)
        except TimeoutError:
            raise ValueError(
                f"the analysis run hit its {self._config.analysis_timeout_s:g}s time "
                f"budget before submitting. Iterations so far: {'; '.join(trace) or 'none'}; "
                f"series fetched: {', '.join(series_names) or 'none'}. "
                "Reuse what is already gathered or ask a narrower question."
            ) from None

    async def _run_loop(
        self,
        context: DelegationContext,
        args: dict[str, Any],
        trace: list[str],
        series_names: list[str],
    ) -> AnalysisResult:
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": await self._task_brief(context.session, args)}
        ]
        nudged = False
        # Once a response has run code, later requests must name its container.
        container_id: str | None = None
        iterations = 0
        progress_grace_used = 0
        step = 0
        last_tool_names: list[str] = []

        while iterations < self._config.max_analysis_iterations:
            step += 1
            self._auto_progress(context, step, last_tool_names)
            request: dict[str, Any] = {
                "model": self._config.analysis_model or self._config.model,
                "max_tokens": self._config.analysis_max_tokens,
                "system": [
                    {
                        "type": "text",
                        "text": self._system,
                        "cache_control": {"type": "ephemeral"},
                    }
                ],
                "tools": self._tools,
                "messages": messages,
                **self._config.thinking_request_fields(),
            }
            if container_id is not None:
                request["container"] = container_id
            call_started = time.monotonic()
            response = await self._client.messages.create(**request)
            log_model_call(
                logger,
                request,
                response,
                call_started,
                context.session.session_id,
                step=step,
            )
            if context.usage is not None:
                accumulate_usage(context.usage, response)
            container = getattr(response, "container", None)
            if container is not None and getattr(container, "id", None):
                container_id = container.id
            content_dicts = [
                block.model_dump(exclude_none=True, exclude={"citations"})
                for block in response.content
            ]
            if content_dicts:
                messages.append({"role": "assistant", "content": content_dicts})

            # Answered whatever the stop reason: a paused sandbox turn with a pending
            # client call is rejected on resume unless the call has its result.
            tool_uses = [block for block in response.content if block.type == "tool_use"]
            trace.append(
                f"{response.stop_reason}:"
                + (",".join(sorted({block.type for block in response.content})) or "empty")
            )
            is_progress_only = bool(tool_uses) and all(
                block.name == REPORT_PROGRESS_TOOL for block in tool_uses
            )
            if is_progress_only and progress_grace_used < _PROGRESS_ONLY_GRACE:
                progress_grace_used += 1
            else:
                iterations += 1
            last_tool_names = [block.name for block in tool_uses]
            if not tool_uses:
                if response.stop_reason == "pause_turn":
                    # The sandbox ran out of server-side iterations; resending resumes it.
                    continue
                if nudged:
                    break
                nudged = True
                messages.append(
                    {
                        "role": "user",
                        "content": (
                            f"Submit now with {SUBMIT_ANALYSIS_TOOL} — either the findings, "
                            "or a submission stating why the data cannot answer the question."
                        ),
                    }
                )
                continue

            submitted: AnalysisResult | None = None
            tool_results: list[dict[str, Any]] = []
            for block in tool_uses:
                tool_input = dict(block.input or {})
                if block.name == SUBMIT_ANALYSIS_TOOL:
                    try:
                        submitted = AnalysisResult.model_validate(tool_input)
                        result_text, is_error = "Analysis submitted.", False
                    except ValidationError as invalid:
                        issues = "; ".join(
                            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}"
                            for error in invalid.errors()
                        )
                        result_text = f"Invalid submission — {issues}. Fix and submit again."
                        is_error = True
                else:
                    result_text, is_error = await self._execute(
                        context, block.name, tool_input, series_names
                    )
                tool_results.append(
                    {
                        "type": "tool_result",
                        "tool_use_id": block.id,
                        "content": result_text,
                        "is_error": is_error,
                    }
                )
            messages.append({"role": "user", "content": tool_results})
            if submitted is not None:
                return submitted

        raise ValueError(
            "the analysis run ended without a submission — try a narrower question "
            f"(iterations: {'; '.join(trace)})"
        )

    def _auto_progress(self, context: DelegationContext, step: int, last_tools: list[str]) -> None:
        # The executor emitted the opener, so step 1 has nothing to add.
        if context.emit_status is None or step == 1:
            return
        verbs = sorted({_STEP_VERBS.get(name, "working") for name in last_tools} or {"working"})
        context.emit_status(f"analysis: step {step} — {', '.join(verbs)}")

    def _sanitize(self, text: str, max_chars: int | None) -> str:
        return MERCHANT_FENCE.sanitize_text(text, max_chars)

    def _fence(self, payload: Any) -> str:
        return MERCHANT_FENCE.fence_payload(payload, self._config.max_fenced_chars)

    async def _read(
        self,
        context: DelegationContext,
        name: str,
        tool_input: dict[str, Any],
        series_names: list[str],
    ) -> tuple[str, bool]:
        # A scratch state keeps listing and campaign ids out of the session's gates.
        scratch = MerchantSessionState()
        reads = MerchantToolExecutor(
            backend=self._backend,
            config=self._config,
            skills=SkillRegistry([]),
            session=context.session,
            state=scratch,
        )
        outcome = await reads.execute(name, tool_input)
        if scratch.latest_snapshot is not None:
            context.state.remember_snapshot(scratch.latest_snapshot)
        for series in scratch.seen_series.values():
            context.state.remember_series(series)
            series_names.append(series.metric)
        return outcome.result_text, outcome.is_error

    async def _execute(
        self,
        context: DelegationContext,
        name: str,
        tool_input: dict[str, Any],
        series_names: list[str],
    ) -> tuple[str, bool]:
        if name == REPORT_PROGRESS_TOOL:
            # Sanitized here; the executor's status channel applies the display clamp.
            message = self._sanitize(str(tool_input.get("message", "")), None)
            if message and context.emit_status is not None:
                context.emit_status(message)
            return "Noted — continue the analysis.", False
        if name in ANALYSIS_READ_TOOLS:
            return await self._read(context, name, tool_input, series_names)
        if name != ANALYSIS_QUERY_TOOL or not self._sql_supported:
            return f"Unknown tool in the analysis context: {name}", True
        try:
            return await self._run_query(context.session, str(tool_input.get("sql", "")))
        except TimeoutError:
            return (
                f"{name} timed out after {self._config.analysis_query_timeout_s:g}s. "
                "Narrow the query and try again.",
                True,
            )
        except Exception as error:  # a failed query must not end the run
            logger.warning("analysis tool %s failed", name, exc_info=True)
            return f"{name} failed: {self._sanitize(str(error), 200) or 'unavailable'}", True

    async def _run_query(self, session: Any, sql: str) -> tuple[str, bool]:
        if reason := check_analysis_sql(sql):
            return (
                f"Query refused: {reason}. Analysis queries are a single read-only "
                "SELECT statement.",
                True,
            )
        # asyncio.timeout rather than wait_for: on 3.11 wait_for can report the outer
        # run timeout's cancellation as this query's TimeoutError.
        async with asyncio.timeout(self._config.analysis_query_timeout_s):
            table = await self._backend.execute_analysis_query(session, sql)
        if table is None:
            return "SQL analysis is not supported by this deployment.", True
        capped = cap_analysis_table(
            table if isinstance(table, AnalysisTable) else AnalysisTable.model_validate(table),
            self._config,
        )
        return self._fence(capped.model_dump(mode="json", exclude_none=True)), False
