# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""scripts/metrics_report.py over a hand-built log: each rate's numerator and denominator
as docs/metrics.md defines them."""

import importlib.util
import json
import sys
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "metrics_report.py"
spec = importlib.util.spec_from_file_location("metrics_report", SCRIPT)
assert spec and spec.loader
report = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = report  # dataclasses resolve their module through sys.modules
spec.loader.exec_module(report)


def turn(
    session,
    turn_id,
    *,
    tools=(),
    writes=(),
    error=None,
    elapsed=1000,
    blocked=(),
    versions=(),
    fallback=None,
    model=("anthropic", "acme-large"),
):
    return {
        "kind": "turn",
        "vertical": "retail",
        "role": "storefront",
        "session": session,
        "turn_id": turn_id,
        "tools": [{"name": name, "status": status} for name, status in tools],
        "writes": list(writes),
        "blocked": list(blocked),
        "error": error,
        "evidence_versions": list(versions),
        "fallback_reason": fallback,
        "provider": model[0],
        "model": model[1],
        "elapsed_ms": elapsed,
        "usage": {"input_tokens": 100, "output_tokens": 20},
    }


def other(kind, session, **fields):
    return {"kind": kind, "vertical": "retail", "role": "storefront", "session": session, **fields}


def test_rates_follow_the_definitions(tmp_path):
    records = [
        # s1: resolved on its first turn by a cart write, no handoff.
        turn("s1", "t1", tools=[("search_products", "ok")], writes=["cart"]),
        # s2: resolved on its second turn by a 👍.
        turn("s2", "t2", tools=[("search_products", "ok")]),
        turn("s2", "t3"),
        other("feedback", "s2", turn_id="t3", helpful=True),
        # s3: unresolved; the user disliked a reply and asked for a person.
        turn(
            "s3",
            "t4",
            tools=[("add_to_cart", "blocked")],
            blocked=[{"tool": "add_to_cart", "reason": "provenance"}],
        ),
        other("feedback", "s3", turn_id="t4", helpful=False),
        other("handoff", "s3", turn_id="t4", reason="after_negative_feedback", ticket="H-1"),
        # s4: every turn failed: not an effective session.
        turn("s4", "t5", error="no_key"),
    ]
    path = tmp_path / "storefront.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n")
    metrics = report.compute(report.load([path])[("retail", "storefront")])

    assert metrics["effective_sessions"] == 3
    assert metrics["resolution_rate"] == {"value": 2 / 3, "numerator": 2, "denominator": 3}
    assert metrics["first_turn_resolution_rate"]["numerator"] == 1
    assert metrics["self_service_rate"]["numerator"] == 2
    assert metrics["handoff_rate"]["numerator"] == 1
    assert metrics["handoff_reasons"] == {"after_negative_feedback": 1}
    assert metrics["negative_feedback_rate"] == {"value": 0.5, "numerator": 1, "denominator": 2}
    assert metrics["grounded_turn_rate"] == {"value": 0.5, "numerator": 2, "denominator": 4}
    assert metrics["system_error_rate"]["numerator"] == 1
    assert metrics["errors"] == {"no_key": 1}
    assert metrics["gate_refusals"] == {"add_to_cart: provenance": 1}
    assert metrics["tokens_per_turn"] == 120
    assert metrics["models"] == {"anthropic/acme-large": 5}


def test_turns_are_counted_by_the_model_that_produced_them(tmp_path):
    older = turn("s1", "t0")
    del older["provider"], older["model"]
    records = [
        older,
        turn("s1", "t1", model=("deepseek", "deepseek-chat")),
        turn("s1", "t2", model=("deepseek", "deepseek-chat")),
        turn("s2", "t3", model=("ollama", None)),
    ]
    path = tmp_path / "storefront.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records))
    metrics = report.compute(report.load([path])[("retail", "storefront")])
    assert metrics["models"] == {"unknown": 1, "deepseek/deepseek-chat": 2, "ollama/?": 1}
    rendered = report.render(("retail", "storefront"), metrics, zh=False)
    assert "Models: deepseek/deepseek-chat 2, ollama/? 1, unknown 1" in rendered


def test_the_review_sample_puts_dislikes_errors_and_refusals_first(tmp_path):
    records = [
        turn("s1", "ok-1"),
        turn("s1", "err", error="generic"),
        turn("s2", "bad"),
        other("feedback", "s2", turn_id="bad", helpful=False),
        turn("s3", "held", blocked=[{"tool": "checkout", "reason": "cap"}]),
    ]
    path = tmp_path / "storefront.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records))
    sessions = report.load([path])[("retail", "storefront")]
    picked = report.review_sample(sessions, 4, seed=0)
    assert [item["why"] for item in picked] == [
        "negative_feedback",
        "system_error",
        "gate_refusal",
        "random",
    ]


def version(source_id, status):
    return {"source_id": source_id, "version": "1", "status": status}


def test_terms_gaps_count_withheld_sources_misses_and_rule_triggered_handoffs(tmp_path):
    promo, returns = "retail/promo", "retail/returns"
    records = [
        # A source withheld twice in one turn counts once for that turn.
        turn(
            "s1",
            "t1",
            versions=[version(promo, "expired"), version(promo, "conflict")],
            fallback="terms_withheld",
        ),
        other("handoff", "s1", turn_id="t1", reason="rule_triggered", ticket="H-1"),
        turn(
            "s2",
            "t2",
            versions=[version(promo, "not_in_force"), version(returns, "current")],
            fallback="terms_withheld",
        ),
        turn("s3", "t3", tools=[("search_policies", "ok")], fallback="no_terms_match"),
        other("handoff", "s3", turn_id="t3", reason="rule_triggered", ticket="H-2"),
        turn("s4", "t4", versions=[version(returns, "superseded"), version(returns, "current")]),
        other("handoff", "s4", turn_id="t4", reason="user_requested", ticket="H-3"),
    ]
    path = tmp_path / "storefront.jsonl"
    path.write_text("\n".join(json.dumps(r) for r in records))
    metrics = report.compute(report.load([path])[("retail", "storefront")])

    assert metrics["terms_gaps"] == {
        "withheld_sources": {promo: 2},
        "no_terms_match_turns": 1,
        "rule_triggered_handoffs": {"terms_withheld": 1, "no_terms_match": 1},
    }
    assert metrics["handoff_reasons"] == {"rule_triggered": 2, "user_requested": 1}
    shown = report.render(("retail", "storefront"), metrics, zh=False)
    assert "### Terms gaps" in shown and f"{promo} 2" in shown
    assert "after a rule held the answer 2" in shown


def test_a_group_without_terms_gaps_prints_no_section(tmp_path):
    path = tmp_path / "storefront.jsonl"
    path.write_text(json.dumps(turn("s1", "t1", writes=["cart"])))
    metrics = report.compute(report.load([path])[("retail", "storefront")])
    assert "Terms gaps" not in report.render(("retail", "storefront"), metrics, zh=False)
