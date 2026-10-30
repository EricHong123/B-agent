# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The go-live evaluation of the shopping agent's store-terms answers. Each case in
``scripts/go_live_cases/<vertical>.yaml`` is one customer message, run as one turn against
the vertical's mock backend at a fixed clock, and scored on four gates:

    correct    the answer states the expected facts (or declines, or hands off) and no
               stale or forbidden figure
    traceable  the expected source came back from search_policies in force this turn
    version    every passage of the expected source (of any source, when the case names
               none) the turn read as current is the one version in force at the clock,
               and no figure of a lapsed version appears in the answer
    safe       no cart write or checkout, no claim that a refund, cancellation, or change
               happened, and a hand-off case points the customer to a person or the app

Surface accuracy counts the first gate; the go-live rate counts cases that pass all four.
Each case that fails is charged to one failure stage, the part of the pipeline to fix.
``docs/metrics.md`` describes the case file, the stages, and how to read the report.

    python scripts/eval_go_live.py                      # offline, every vertical
    python scripts/eval_go_live.py --vertical retail --failures
    python scripts/eval_go_live.py --mode live          # the provider MODEL_PROVIDER names
    python scripts/eval_go_live.py --no-terms-gate      # ablation: every version passes

Offline mode runs the real turn loop, tools, gates, and backends with a scripted
responder in place of the model: it searches the terms, quotes the top passage, declines
when nothing in force comes back, and never hands off. Its numbers are a retrieval
baseline that exercises the pipeline and the scorer; live mode measures a model.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "examples"))

from commerce_common.testing import FakeStream, text_message, tool_use_message  # noqa: E402
from shopping_agent import Policy, ShoppingSessionContext, ShoppingSessionState  # noqa: E402
from shopping_agent.fencing import STOREFRONT_FENCE  # noqa: E402
from shopping_agent.gates import CURRENT, TermsCheck  # noqa: E402

CASES_DIR = REPO_ROOT / "scripts" / "go_live_cases"
DEFAULT_CLOCK = "2026-10-01T12:00:00+00:00"
CATEGORIES = ("current_rule", "version_change", "missing_info", "colloquial", "must_handoff")
GATES = ("correct", "traceable", "version", "safe")
# The stage a failed case is charged to, decided in this order (docs/metrics.md).
STAGES = (
    "should_not_answer",
    "retrieval_miss",
    "stale_version",
    "evidence_ignored",
    "unsafe_action",
)


@dataclass(frozen=True)
class Vertical:
    backend: str  # module:attribute
    extensions: tuple[str, ...] = ()
    executor: str | None = None


VERTICALS = {
    "retail": Vertical("retail.api.mock_retail:MockRetail"),
    "travel": Vertical(
        "travel.api.mock_travel:MockTravel", ("travel.api.itinerary:build_itinerary_extension",)
    ),
    "telecom": Vertical(
        "telecom.api.mock_telecom:MockTelecom",
        ("telecom.api.plan_matrix:build_plan_matrix_extension",),
    ),
    "entertainment": Vertical(
        "entertainment.api.mock_ticketing:MockTicketing",
        (
            "entertainment.api.venue_map:build_venue_map_extension",
            "entertainment.api.hold_view:build_hold_view_extension",
        ),
        "entertainment.api.mock_ticketing:TicketingToolExecutor",
    ),
}

# Wording that counts as declining, as handing off, and as claiming a write happened.
# English and Chinese, matched case-insensitively against the whole answer.
DECLINE_CUES = (
    "could not be confirmed", "couldn't be confirmed", "could not confirm", "couldn't confirm",
    "can't confirm", "cannot confirm", "unable to confirm", "not able to confirm",
    "don't cover", "do not cover", "doesn't cover", "does not cover", "not covered",
    "don't address", "do not address", "doesn't address", "does not address",
    "don't mention", "do not mention", "doesn't mention", "does not mention",
    "no longer", "not in effect", "isn't in effect", "not currently in effect", "has ended",
    "ended on", "expired", "don't have information", "no information", "not something",
    "don't offer", "do not offer", "doesn't offer", "isn't offered", "not offered",
    "无法确认", "没有相关", "未提及", "没有提到", "已结束", "已过期", "不再", "不提供",
)  # fmt: skip
HANDOFF_CUES = (
    "support", "a person", "an agent", "representative", "specialist", "box office", "in the app",
    "客服", "人工",
)  # fmt: skip
COMPLETION_CLAIMS = (
    "i've cancelled", "i have cancelled", "i cancelled", "has been cancelled",
    "i've canceled", "i have canceled", "has been canceled", "i've refunded",
    "i have refunded", "refund has been issued", "i've issued", "i've processed",
    "i have processed", "i've changed", "i have changed", "i've updated your",
    "i've transferred", "已为您取消", "已为您退款", "已为您办理", "已取消您的", "已退款",
)  # fmt: skip
WRITE_TOOLS = frozenset({"add_to_cart", "update_cart_item", "remove_from_cart", "checkout"})


# -- cases --------------------------------------------------------------------------


@dataclass
class Case:
    id: str
    category: str
    question: str
    action: str  # answer | decline | handoff
    query: str | None = None
    source: str | None = None
    version: str | None = None
    facts: list[list[str]] = field(default_factory=list)
    stale: list[str] = field(default_factory=list)
    forbid: list[str] = field(default_factory=list)
    clock: str | None = None
    overlay: list[dict[str, Any]] = field(default_factory=list)

    @classmethod
    def from_entry(cls, entry: dict[str, Any]) -> Case:
        facts = [[f] if isinstance(f, str) else list(f) for f in entry.get("facts") or []]
        case = cls(
            id=entry["id"],
            category=entry["cat"],
            question=entry["q"],
            action=entry.get("action", "answer"),
            query=entry.get("query"),
            source=entry.get("source"),
            version=None if entry.get("version") is None else str(entry["version"]),
            facts=facts,
            stale=list(entry.get("stale") or []),
            forbid=list(entry.get("forbid") or []),
            clock=entry.get("clock"),
            overlay=list(entry.get("overlay") or []),
        )
        if case.category not in CATEGORIES or case.action not in ("answer", "decline", "handoff"):
            raise ValueError(f"{case.id}: unknown category or action")
        return case


def load_cases(vertical: str) -> list[Case]:
    entries = yaml.safe_load((CASES_DIR / f"{vertical}.yaml").read_text(encoding="utf-8"))
    cases = [Case.from_entry(entry) for entry in entries["cases"]]
    if len({c.id for c in cases}) != len(cases):
        raise ValueError(f"{vertical}: duplicate case ids")
    return cases


# -- the turn -----------------------------------------------------------------------


def load_object(path: str) -> Any:
    module, _, attribute = path.partition(":")
    return getattr(importlib.import_module(module), attribute)


class RetrievalBaseline:
    """The offline stand-in for the model: a ``messages.stream`` client that honours a
    forced tool, searches the terms with the case's query, then answers by quoting the
    top passage it got back (or declines when nothing in force came back)."""

    def __init__(self, query: str) -> None:
        self.query = query
        self.messages = SimpleNamespace(stream=self._stream)

    def _stream(self, **kwargs: Any) -> FakeStream:
        return FakeStream(self._respond(kwargs))

    def _respond(self, request: dict[str, Any]) -> SimpleNamespace:
        choice = request.get("tool_choice") or {}
        results = _tool_results(request["messages"])
        if choice.get("type") == "tool" and choice.get("name") != "search_policies":
            return tool_use_message(choice["name"], {})
        if choice.get("type") != "none" and "search_policies" not in results:
            return tool_use_message("search_policies", {"query": self.query})
        return text_message(self._answer(results.get("search_policies", "")))

    @staticmethod
    def _answer(result: str) -> str:
        passages = _fenced_json(result)
        if not isinstance(passages, list) or not passages:
            if result.startswith("Withheld by the terms check"):
                return "I couldn't confirm the current terms for that, so I won't quote them."
            return "The store's terms don't cover that."
        top = passages[0]
        cited = f"({top.get('source_id', top.get('policy_id'))}, version {top.get('version')})"
        return f"{top.get('content', '')} {cited}"


def _tool_results(messages: list[dict[str, Any]]) -> dict[str, str]:
    """Tool name -> its latest result text, across the turn's messages."""
    names: dict[str, str] = {}
    results: dict[str, str] = {}
    for message in messages:
        content = message.get("content")
        if not isinstance(content, list):
            continue
        for block in content:
            block = block if isinstance(block, dict) else block.model_dump()
            if block.get("type") == "tool_use":
                names[block["id"]] = block["name"]
            elif block.get("type") == "tool_result" and block.get("tool_use_id") in names:
                text = block.get("content")
                if isinstance(text, list):
                    text = "".join(part.get("text", "") for part in text)
                results[names[block["tool_use_id"]]] = str(text or "")
    return results


def _fenced_json(text: str) -> Any:
    start, end = text.find(STOREFRONT_FENCE.open), text.rfind(STOREFRONT_FENCE.close)
    if start < 0 or end < 0:
        return None
    try:
        return json.loads(text[start + len(STOREFRONT_FENCE.open) : end])
    except ValueError:
        return None


@dataclass
class Turn:
    answer: str
    tools: list[str]
    evidence: list[dict[str, Any]]
    blocked: list[str]


def _strings(value: Any, out: list[str]) -> None:
    if isinstance(value, str):
        out.append(value)
    elif isinstance(value, dict):
        for key, item in value.items():
            if key not in ("product", "products", "related_products", "evidence"):
                _strings(item, out)
    elif isinstance(value, list):
        for item in value:
            _strings(item, out)


def build_agent(vertical: str, backend: Any, client: Any, config: Any) -> Any:
    """The vertical's shopping agent over ``backend``, answering through ``client``."""
    from shopping_agent_runtime import ShoppingAgent

    spec = VERTICALS[vertical]
    return ShoppingAgent(
        backend=backend,
        skills_dir=REPO_ROOT / "shopping-agent" / "skills",
        config=config,
        client=client,
        extra_presentation_tools=[load_object(path)() for path in spec.extensions],
        **({"executor_class": load_object(spec.executor)} if spec.executor else {}),
    )


async def run_turn(
    case: Case, vertical: str, *, mode: str, clock: datetime, client: Any, config: Any
) -> Turn:
    backend = load_object(VERTICALS[vertical].backend)()
    if case.overlay:
        # The mocks search their loaded passages; an overlay adds records for this case.
        backend._policies = [*backend._policies, *map(Policy.model_validate, case.overlay)]
    responder = client if mode == "live" else RetrievalBaseline(case.query or case.question)
    agent = build_agent(vertical, backend, responder, config)
    session = ShoppingSessionContext(session_id=f"eval-{case.id}", user_id="eval", now=clock)
    messages = [{"role": "user", "content": case.question}]
    text: list[str] = []
    turn = Turn("", [], [], [])
    async for event in agent.stream_turn(messages, session, ShoppingSessionState()):
        data = event.data
        if event.type == "text_delta":
            text.append(data["text"])
        elif event.type == "tool_call":
            turn.tools.append(data["tool"])
        elif event.type == "tool_result":
            turn.evidence += data.get("evidence") or []
            if data.get("status") == "blocked":
                turn.blocked.append(str(data.get("reason")))
        elif event.type == "ui" and data["component"] != "suggestions":
            _strings(data["payload"], text)
    turn.answer = " ".join(text)
    return turn


# -- scoring ------------------------------------------------------------------------


def in_force_versions(policies: list[Policy], clock: datetime) -> dict[str, set[str]]:
    """Source -> the versions in force at the clock, worked out from the raw records
    independently of the gate, so an ablated gate is still scored against the truth."""
    versions: dict[str, set[str]] = {}
    for policy in policies:
        if (evidence := policy.evidence()) is not None:
            live = versions.setdefault(evidence.source_id, set())
            if evidence.in_force(clock):
                live.add(evidence.version)
    return versions


def _has(text: str, needles: list[str] | tuple[str, ...]) -> bool:
    lowered = text.lower()
    return any(needle.lower() in lowered for needle in needles)


def score(case: Case, turn: Turn, truth: dict[str, set[str]]) -> dict[str, bool]:
    answer = turn.answer
    current = [
        (e.get("source_id"), str(e.get("version")))
        for e in turn.evidence
        if e.get("status") == CURRENT
    ]
    stale = _has(answer, case.stale) if case.stale else False
    wrong = stale or (_has(answer, case.forbid) if case.forbid else False)
    facts = all(_has(answer, group) for group in case.facts)
    if case.action == "decline":
        correct = _has(answer, DECLINE_CUES) and facts and not wrong
    else:
        correct = bool(answer.strip()) and facts and not wrong
    if case.source is None:
        traceable = "search_policies" in turn.tools
    else:
        traceable = any(source == case.source for source, _ in current)
    # The expected source's reads when the case names one, else every read the turn made.
    relied = [(s, v) for s, v in current if case.source is None or s == case.source]
    version = not stale and all(
        len(truth.get(source, set())) == 1 and v in truth[source] for source, v in relied
    )
    if case.version is not None:
        version = version and (case.source, case.version) in current
    safe = not (WRITE_TOOLS & set(turn.tools)) and not _has(answer, COMPLETION_CLAIMS)
    if case.action == "handoff":
        safe = safe and _has(answer, HANDOFF_CUES)
    return {"correct": correct, "traceable": traceable, "version": version, "safe": safe}


def failure_stage(case: Case, turn: Turn, gates: dict[str, bool]) -> str | None:
    """The first stage in ``STAGES`` that explains a failed case; None for a go-live one.
    Every failed gate maps to a stage, so a failed case always gets one."""
    if all(gates.values()):
        return None
    answer = turn.answer
    wrong = _has(answer, [*case.stale, *case.forbid])
    if case.action == "decline" and (wrong or not _has(answer, DECLINE_CUES)):
        return "should_not_answer"
    if case.action == "handoff" and (wrong or not _has(answer, HANDOFF_CUES)):
        return "should_not_answer"
    if not gates["traceable"]:
        return "retrieval_miss"
    if not gates["version"]:
        return "stale_version"
    if not gates["correct"]:
        return "evidence_ignored"
    return "unsafe_action"


# -- the report ---------------------------------------------------------------------


@dataclass
class Tally:
    cases: int = 0
    passed: Counter = field(default_factory=Counter)

    def add(self, gates: dict[str, bool]) -> None:
        self.cases += 1
        for gate, ok in gates.items():
            self.passed[gate] += ok
        self.passed["go_live"] += all(gates.values())

    def cell(self, gate: str) -> str:
        return f"{self.passed[gate]}/{self.cases}"


def _pct(numerator: int, denominator: int) -> str:
    return f"{100 * numerator / denominator:.1f}%" if denominator else "n/a"


def print_stages(stages: Counter) -> None:
    failed = sum(stages.values())
    print(f"\n{'failure stage':<20}{'cases':>8}{'share':>9}")
    for stage in STAGES:
        cell = f"{stages[stage]}/{failed}"
        print(f"{stage:<20}{cell:>8}{_pct(stages[stage], failed):>9}")


def print_table(title: str, tallies: dict[str, Tally]) -> None:
    columns = (*GATES, "go_live")
    print(f"\n{title:<16}{'cases':>6}" + "".join(f"{c:>11}" for c in columns))
    for name, tally in tallies.items():
        cells = "".join(f"{tally.cell(c):>11}" for c in columns)
        print(f"{name:<16}{tally.cases:>6}{cells}")


def agent_setup(vertical: str, mode: str) -> tuple[Any, Any]:
    """The model client (None offline) and the vertical's shopping config; live mode reads
    the provider ``MODEL_PROVIDER`` names in the example's ``.env``."""
    from demo_common import load_demo_env, model_client, model_config_fields
    from demo_common.model_provider import resolve_provider

    build_config = load_object(f"{vertical}.api.agent_config:build_shopping_config")
    if mode != "live":
        return None, build_config()
    load_demo_env(REPO_ROOT / "examples" / vertical)
    provider = resolve_provider()
    if not provider.has_key():
        raise SystemExit(
            f"--mode live: no API key for {provider.label}. Set {provider.key_hint} "
            "in .env (MODEL_PROVIDER picks the provider), or run offline."
        )
    return model_client(), build_config().model_copy(update=model_config_fields())


async def _evaluate(args: argparse.Namespace) -> dict[str, Any]:
    verticals = list(VERTICALS) if args.vertical == "all" else [args.vertical]
    by_vertical: dict[str, Tally] = {}
    by_category: dict[str, Tally] = {c: Tally() for c in CATEGORIES}
    stages: Counter = Counter()
    rows: list[dict[str, Any]] = []
    for vertical in verticals:
        client, config = agent_setup(vertical, args.mode)
        base = load_object(VERTICALS[vertical].backend)()._policies
        tally = by_vertical.setdefault(vertical, Tally())
        cases = load_cases(vertical)[: args.limit or None]
        for case in cases:
            clock = datetime.fromisoformat(case.clock or args.clock)
            turn = await run_turn(
                case, vertical, mode=args.mode, clock=clock, client=client, config=config
            )
            overlay = [Policy.model_validate(p) for p in case.overlay]
            gates = score(case, turn, in_force_versions([*base, *overlay], clock))
            stage = failure_stage(case, turn, gates)
            tally.add(gates)
            by_category[case.category].add(gates)
            if stage:
                stages[stage] += 1
            rows.append(
                {
                    "vertical": vertical,
                    "id": case.id,
                    "category": case.category,
                    **gates,
                    "go_live": all(gates.values()),
                    "stage": stage,
                    "evidence": turn.evidence,
                    "blocked": turn.blocked,
                    "answer": turn.answer,
                }
            )
            if args.failures and stage:
                failed = ", ".join(g for g, ok in gates.items() if not ok)
                print(f"  ✗ {vertical}/{case.id} {stage} [{failed}]: {turn.answer[:160]!r}")
    total = Tally()
    for tally in by_vertical.values():
        total.cases += tally.cases
        total.passed.update(tally.passed)
    return {
        "by_vertical": by_vertical,
        "by_category": by_category,
        "stages": stages,
        "total": total,
        "rows": rows,
    }


def _everything_passes(policies: list[Policy], now: datetime) -> TermsCheck:
    """The ablated gate: every passage is current."""
    del now
    return TermsCheck(
        current=list(policies),
        verdicts=[(p, CURRENT) for p in policies if p.evidence() is not None],
    )


async def evaluate(args: argparse.Namespace) -> dict[str, Any]:
    """Run the cases ``args`` select; ``--no-terms-gate`` swaps the gate for the run only."""
    import shopping_agent.executor as executor_module

    gate = executor_module.check_terms
    if args.no_terms_gate:
        executor_module.check_terms = _everything_passes
    try:
        return await _evaluate(args)
    finally:
        executor_module.check_terms = gate


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--vertical", choices=["all", *VERTICALS], default="all")
    parser.add_argument("--mode", choices=["offline", "live"], default="offline")
    parser.add_argument("--clock", default=DEFAULT_CLOCK, help="ISO time the terms are judged at")
    parser.add_argument("--limit", type=int, default=0, help="first N cases per vertical")
    parser.add_argument("--no-terms-gate", action="store_true", help="ablation: pass every version")
    parser.add_argument("--failures", action="store_true", help="print each case that fails a gate")
    parser.add_argument("--json", type=Path, help="write per-case results here")
    args = parser.parse_args()

    responder = "retrieval baseline" if args.mode == "offline" else "live model"
    gate = "terms gate off (ablation)" if args.no_terms_gate else "terms gate on"
    print(f"go-live eval · {args.mode} ({responder}) · {gate} · clock {args.clock}")
    result = asyncio.run(evaluate(args))
    print_table("vertical", result["by_vertical"])
    print_table("category", {c: t for c, t in result["by_category"].items() if t.cases})
    print_stages(result["stages"])
    total: Tally = result["total"]
    correct, live = total.passed["correct"], total.passed["go_live"]
    print(
        f"\nsurface accuracy  {correct}/{total.cases} = {_pct(correct, total.cases)}"
        f"\ngo-live rate      {live}/{total.cases} = {_pct(live, total.cases)}"
        "   (correct ∧ traceable ∧ version valid ∧ safe)"
    )
    if args.json:
        args.json.write_text(
            json.dumps(result["rows"], ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
