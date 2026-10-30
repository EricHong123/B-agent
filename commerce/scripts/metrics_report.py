# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The operations metrics of docs/metrics.md, computed from the example APIs' operations
logs (examples/demo_common/analytics.py), one table per vertical and role.

    python scripts/metrics_report.py                     # every log under examples/*/data/.analytics
    python scripts/metrics_report.py --lang zh           # metric names in Chinese
    python scripts/metrics_report.py --sample 10         # plus the turns to review first
    python scripts/metrics_report.py --json              # the numbers as JSON
    python scripts/metrics_report.py path/to/storefront.jsonl ...

Every rate states its numerator and denominator; a rate whose denominator is zero prints
as a dash.
"""

from __future__ import annotations

import argparse
import json
import random
import statistics
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFINITIONS_VERSION = "1.1"
# The terms-gate statuses that withhold a source (shopping_agent.gates.WITHHELD).
WITHHELD = frozenset({"expired", "not_in_force", "conflict"})
TOP_SOURCES = 10

NAMES = {
    "effective_sessions": ("Effective sessions", "有效接待会话数"),
    "turns": ("Turns", "对话轮次"),
    "resolution_rate": ("Resolution rate", "问题解决率"),
    "first_turn_resolution_rate": ("First-turn resolution rate", "一次解决率"),
    "self_service_rate": ("Effective self-service rate", "有效自助率"),
    "handoff_rate": ("Handoff rate", "转人工率"),
    "negative_feedback_rate": ("Negative feedback rate", "负反馈率"),
    "grounded_turn_rate": ("Grounded turn rate", "有据回答率"),
    "system_error_rate": ("System error rate", "系统异常率"),
    "latency_p50_ms": ("Latency p50 (ms)", "响应时延 P50（毫秒）"),
    "latency_p95_ms": ("Latency p95 (ms)", "响应时延 P95（毫秒）"),
    "tokens_per_turn": ("Tokens per turn", "每轮 Token"),
}
REVIEW_REASONS = {
    "negative_feedback": ("👎", "负反馈"),
    "system_error": ("system error", "系统异常"),
    "gate_refusal": ("gate refusal", "门禁拦截"),
    "random": ("random draw", "随机抽样"),
}
HANDOFF_REASONS = {
    "user_requested": ("asked by the user", "用户主动要求"),
    "after_negative_feedback": ("after a 👎", "差评后转接"),
    "after_error": ("after a system error", "系统异常后转接"),
    "rule_triggered": ("after a rule held the answer", "规则触发转接"),
}


@dataclass
class Session:
    turns: list[dict[str, Any]] = field(default_factory=list)
    votes: list[dict[str, Any]] = field(default_factory=list)
    handoffs: list[dict[str, Any]] = field(default_factory=list)
    actions: list[dict[str, Any]] = field(default_factory=list)

    def effective(self) -> bool:
        return any(turn.get("error") is None for turn in self.turns)

    def completion_turns(self) -> list[int]:
        """Indexes of the turns that carry a completion signal: a 👍, a write the turn
        made (cart or staged change), or a successful checkout call. An applied change
        from the portal counts for the session's last turn."""
        helpful = {vote["turn_id"] for vote in self.votes if vote.get("helpful")}
        found = []
        for index, turn in enumerate(self.turns):
            checkout = any(
                tool.get("name") == "checkout" and tool.get("status") == "ok"
                for tool in turn.get("tools", [])
            )
            if turn["turn_id"] in helpful or turn.get("writes") or checkout:
                found.append(index)
        if self.turns and any(a.get("name") == "apply_change" for a in self.actions):
            found.append(len(self.turns) - 1)
        return sorted(set(found))

    def disliked(self) -> bool:
        latest: dict[str, bool] = {}
        for vote in self.votes:
            latest[vote["turn_id"]] = bool(vote.get("helpful"))
        return any(value is False for value in latest.values())


def load(paths: list[Path]) -> dict[tuple[str, str], dict[str, Session]]:
    groups: dict[tuple[str, str], dict[str, Session]] = defaultdict(lambda: defaultdict(Session))
    for path in paths:
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                record = json.loads(line)
            except ValueError:
                print(f"{path}:{number}: skipped, not JSON", file=sys.stderr)
                continue
            session = groups[(record.get("vertical", "?"), record.get("role", "?"))][
                record.get("session", "?")
            ]
            kind = record.get("kind")
            if kind == "turn":
                session.turns.append(record)
            elif kind == "feedback":
                session.votes.append(record)
            elif kind == "handoff":
                session.handoffs.append(record)
            elif kind == "action":
                session.actions.append(record)
    return groups


def ratio(numerator: int, denominator: int) -> dict[str, Any]:
    return {
        "value": numerator / denominator if denominator else None,
        "numerator": numerator,
        "denominator": denominator,
    }


def percentile(values: list[int], q: float) -> int | None:
    if not values:
        return None
    if len(values) == 1:
        return values[0]
    return round(statistics.quantiles(values, n=100, method="inclusive")[int(q) - 1])


def model_of(turn: dict[str, Any]) -> str:
    """``provider/model`` as the turn record names them; a record without them (written
    before they were logged) counts as ``unknown``."""
    provider, model = turn.get("provider"), turn.get("model")
    if not provider and not model:
        return "unknown"
    return f"{provider or '?'}/{model or '?'}"


def compute(sessions: dict[str, Session]) -> dict[str, Any]:
    effective = [s for s in sessions.values() if s.effective()]
    turns = [turn for s in sessions.values() for turn in s.turns]
    answered = [turn for turn in turns if turn.get("error") is None]
    resolved = [s for s in effective if s.completion_turns()]
    first = [s for s in resolved if s.completion_turns()[0] == 0]
    self_served = [s for s in resolved if not s.handoffs and not s.disliked()]
    handed = [s for s in effective if s.handoffs]
    votes = [vote for s in sessions.values() for vote in s.votes]
    grounded = [
        turn
        for turn in answered
        if any(tool.get("status") == "ok" for tool in turn.get("tools", []))
    ]
    latencies = [turn["elapsed_ms"] for turn in answered if isinstance(turn.get("elapsed_ms"), int)]
    tokens = [sum((turn.get("usage") or {}).values()) for turn in answered if turn.get("usage")]
    reasons = Counter(h.get("reason") for s in handed for h in s.handoffs[:1])
    return {
        "effective_sessions": len(effective),
        "turns": len(turns),
        "resolution_rate": ratio(len(resolved), len(effective)),
        "first_turn_resolution_rate": ratio(len(first), len(effective)),
        "self_service_rate": ratio(len(self_served), len(effective)),
        "handoff_rate": ratio(len(handed), len(effective)),
        "handoff_reasons": dict(reasons),
        "negative_feedback_rate": ratio(sum(not v.get("helpful") for v in votes), len(votes)),
        "grounded_turn_rate": ratio(len(grounded), len(answered)),
        "system_error_rate": ratio(len(turns) - len(answered), len(turns)),
        "errors": dict(Counter(turn["error"] for turn in turns if turn.get("error"))),
        "gate_refusals": dict(
            Counter(
                f"{b.get('tool')}: {b.get('reason')}" for t in turns for b in t.get("blocked", [])
            )
        ),
        "latency_p50_ms": percentile(latencies, 50),
        "latency_p95_ms": percentile(latencies, 95),
        "tokens_per_turn": round(statistics.mean(tokens)) if tokens else None,
        "models": dict(Counter(model_of(turn) for turn in turns)),
        "terms_gaps": terms_gaps(sessions),
    }


def terms_gaps(sessions: dict[str, Session]) -> dict[str, Any]:
    """What the terms could not answer: the sources withheld most often (each counted once
    per turn), the turns whose terms read found nothing, and the rule-triggered handoffs
    split by the fallback reason of the turn they were opened from."""
    turns = [turn for s in sessions.values() for turn in s.turns]
    withheld = Counter(
        source
        for turn in turns
        for source in {
            e.get("source_id")
            for e in turn.get("evidence_versions", [])
            if e.get("status") in WITHHELD
        }
    )
    fallback = {turn["turn_id"]: turn.get("fallback_reason") for turn in turns}
    triggered = Counter(
        fallback.get(h.get("turn_id")) or "unknown"
        for s in sessions.values()
        for h in s.handoffs[:1]
        if s.effective() and h.get("reason") == "rule_triggered"
    )
    return {
        "withheld_sources": dict(withheld.most_common(TOP_SOURCES)),
        "no_terms_match_turns": sum(t.get("fallback_reason") == "no_terms_match" for t in turns),
        "rule_triggered_handoffs": dict(triggered),
    }


def review_sample(sessions: dict[str, Session], size: int, seed: int) -> list[dict[str, str]]:
    """The turns a reviewer reads first: every 👎, then errors, then gate refusals, then a
    random draw from the rest, ``size`` in all."""
    disliked = {v["turn_id"] for s in sessions.values() for v in s.votes if not v.get("helpful")}
    turns = [turn for s in sessions.values() for turn in s.turns]
    tiers: list[tuple[str, list[dict[str, Any]]]] = [
        ("negative_feedback", [t for t in turns if t["turn_id"] in disliked]),
        ("system_error", [t for t in turns if t.get("error")]),
        ("gate_refusal", [t for t in turns if t.get("blocked")]),
    ]
    picked: list[dict[str, str]] = []
    seen: set[str] = set()
    for why, group in tiers:
        for turn in group:
            if len(picked) < size and turn["turn_id"] not in seen:
                picked.append({"turn_id": turn["turn_id"], "session": turn["session"], "why": why})
                seen.add(turn["turn_id"])
    rest = [t for t in turns if t["turn_id"] not in seen]
    random.Random(seed).shuffle(rest)
    for turn in rest[: max(size - len(picked), 0)]:
        picked.append({"turn_id": turn["turn_id"], "session": turn["session"], "why": "random"})
    return picked


def render(group: tuple[str, str], metrics: dict[str, Any], zh: bool) -> str:
    index = 1 if zh else 0
    lines = [f"## {group[0]} · {group[1]}", ""]
    header = (
        ("指标", "数值", "分子 / 分母") if zh else ("Metric", "Value", "Numerator / denominator")
    )
    lines += [f"| {header[0]} | {header[1]} | {header[2]} |", "|---|---|---|"]
    for key, names in NAMES.items():
        value = metrics[key]
        if isinstance(value, dict):
            shown = "—" if value["value"] is None else f"{value['value']:.1%}"
            basis = f"{value['numerator']} / {value['denominator']}"
        else:
            shown, basis = ("—" if value is None else f"{value:,}"), ""
        lines.append(f"| {names[index]} | {shown} | {basis} |")
    for title, counts in (
        ("转人工原因" if zh else "Handoff reasons", metrics["handoff_reasons"]),
        ("系统异常" if zh else "System errors", metrics["errors"]),
        ("门禁拦截" if zh else "Gate refusals", metrics["gate_refusals"]),
        ("生成模型" if zh else "Models", metrics["models"]),
    ):
        if counts:
            labels = {k: v[index] for k, v in HANDOFF_REASONS.items()}
            parts = ", ".join(f"{labels.get(k, k)} {n}" for k, n in sorted(counts.items()))
            lines.append(f"\n{title}: {parts}")
    gaps = metrics["terms_gaps"]
    if not any(gaps.values()):
        return "\n".join(lines)
    lines += ["", f"### {'条款缺口' if zh else 'Terms gaps'}", ""]
    sources = ", ".join(f"{k} {n}" for k, n in gaps["withheld_sources"].items())
    triggered = ", ".join(f"{k} {n}" for k, n in sorted(gaps["rule_triggered_handoffs"].items()))
    for label, shown in (
        ("最常被拦截的条款来源" if zh else "Sources withheld most often", sources or "—"),
        (
            "条款无匹配的轮次" if zh else "Turns with no matching terms",
            gaps["no_terms_match_turns"],
        ),
        (
            "规则触发转接，按回退原因" if zh else "Rule-triggered handoffs by fallback reason",
            triggered or "—",
        ),
    ):
        lines.append(f"- {label}: {shown}")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description=(__doc__ or "").partition("\n")[0])
    parser.add_argument("paths", nargs="*", type=Path)
    parser.add_argument("--lang", choices=("en", "zh"), default="en")
    parser.add_argument("--json", action="store_true")
    parser.add_argument("--sample", type=int, default=0, metavar="N", help="list N turns to review")
    parser.add_argument("--seed", type=int, default=0)
    args = parser.parse_args()
    paths = args.paths or sorted((REPO_ROOT / "examples").glob("*/data/.analytics/*.jsonl"))
    if not paths:
        print("No operations logs yet: chat with an example first (scripts/run_demo.py).")
        return 1
    groups = load(paths)
    report = {
        f"{vertical}/{role}": {
            "metrics": compute(sessions),
            **({"review": review_sample(sessions, args.sample, args.seed)} if args.sample else {}),
        }
        for (vertical, role), sessions in sorted(groups.items())
    }
    if args.json:
        print(
            json.dumps({"definitions": DEFINITIONS_VERSION, **report}, ensure_ascii=False, indent=2)
        )
        return 0
    zh = args.lang == "zh"
    print(
        f"# {'运营指标' if zh else 'Operations metrics'} (docs/metrics.md v{DEFINITIONS_VERSION})\n"
    )
    for key, entry in report.items():
        vertical, role = key.split("/")
        print(render((vertical, role), entry["metrics"], zh) + "\n")
        if entry.get("review"):
            print(f"{'待质检轮次' if zh else 'Turns to review'}:")
            for item in entry["review"]:
                why = REVIEW_REASONS[item["why"]][1 if zh else 0]
                print(f"- {item['turn_id']} (session {item['session']}, {why})")
            print()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
