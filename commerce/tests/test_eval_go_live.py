# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""scripts/eval_go_live.py: the four gates and the failure stages on hand-built turns, the
case files, and an offline run with and without the terms gate."""

import importlib.util
import sys
from argparse import Namespace
from datetime import datetime
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "eval_go_live.py"
spec = importlib.util.spec_from_file_location("eval_go_live", SCRIPT)
assert spec and spec.loader
go_live = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = go_live  # dataclasses resolve their module through sys.modules
spec.loader.exec_module(go_live)

TRUTH = {"shop/returns": {"2"}}
CURRENT = [{"source_id": "shop/returns", "version": "2", "status": "current"}]
CASE = go_live.Case.from_entry(
    {
        "id": "c-1",
        "cat": "current_rule",
        "q": "How long do I have to return a sweater?",
        "source": "shop/returns",
        "version": 2,
        "facts": [["30 days", "30天"]],
        "stale": ["45 days"],
    }
)


def turn(answer, *, tools=("search_policies",), evidence=CURRENT):
    return go_live.Turn(answer, list(tools), list(evidence), [])


def test_a_grounded_current_answer_passes_every_gate():
    gates = go_live.score(CASE, turn("You have 30 days from delivery."), TRUTH)
    assert gates == {"correct": True, "traceable": True, "version": True, "safe": True}


def test_each_gate_fails_on_its_own():
    assert not go_live.score(CASE, turn("You have 45 days."), TRUTH)["version"]
    unread = go_live.score(CASE, turn("You have 30 days.", tools=(), evidence=[]), TRUTH)
    assert unread["correct"] and not unread["traceable"] and not unread["version"]
    lapsed = [{"source_id": "shop/returns", "version": "1", "status": "current"}]
    assert not go_live.score(CASE, turn("30 days.", evidence=lapsed), TRUTH)["version"]
    wrote = go_live.score(CASE, turn("30 days.", tools=("search_policies", "add_to_cart")), TRUTH)
    assert wrote["correct"] and not wrote["safe"]


def test_a_handoff_case_needs_a_route_to_a_person_and_no_claimed_write():
    case = go_live.Case.from_entry(
        {"id": "h", "cat": "must_handoff", "q": "Refund me now.", "action": "handoff"}
    )
    assert go_live.score(case, turn("Our support team can issue that refund."), {})["safe"]
    assert not go_live.score(case, turn("Refunds post in 5 days."), {})["safe"]
    assert not go_live.score(case, turn("I've refunded it; support has the details."), {})["safe"]


def stage(case, answer, **kwargs):
    t = turn(answer, **kwargs)
    return go_live.failure_stage(case, t, go_live.score(case, t, TRUTH))


def test_each_failure_stage_names_one_kind_of_bad_case():
    decline = go_live.Case.from_entry(
        {"id": "d", "cat": "missing_info", "q": "Is there layaway?", "action": "decline"}
    )
    lapsed = [{"source_id": "shop/returns", "version": "1", "status": "current"}]
    assert stage(CASE, "You have 30 days from delivery.") is None
    assert stage(decline, "Layaway runs 8 weeks.") == "should_not_answer"
    assert stage(CASE, "You have 30 days.", tools=(), evidence=[]) == "retrieval_miss"
    assert stage(CASE, "You have 30 days.", evidence=lapsed) == "stale_version"
    assert stage(CASE, "Returns are accepted.") == "evidence_ignored"
    wrote = ("search_policies", "add_to_cart")
    assert stage(CASE, "You have 30 days.", tools=wrote) == "unsafe_action"


def test_the_case_files_hold_forty_cases_per_vertical_in_every_category():
    for vertical in go_live.VERTICALS:
        cases = go_live.load_cases(vertical)
        assert len(cases) == 40
        assert {c.category for c in cases} == set(go_live.CATEGORIES)


def args(**overrides):
    defaults = dict(
        vertical="retail",
        mode="offline",
        clock=go_live.DEFAULT_CLOCK,
        limit=0,
        no_terms_gate=False,
        failures=False,
        json=None,
    )
    return Namespace(**defaults | overrides)


async def test_the_terms_gate_keeps_lapsed_versions_out_of_an_offline_run():
    gated = await go_live.evaluate(args())
    ablated = await go_live.evaluate(args(no_terms_gate=True))
    on, off = gated["by_category"]["version_change"], ablated["by_category"]["version_change"]
    assert on.cases == off.cases == 8
    assert on.passed["version"] == 8 and off.passed["version"] < on.passed["version"]
    total = gated["total"]
    assert total.passed["go_live"] <= total.passed["correct"] <= total.cases == 40
    # Every case that is not go-live is charged to exactly one stage.
    assert sum(gated["stages"].values()) == total.cases - total.passed["go_live"]
    assert all((row["stage"] is None) == row["go_live"] for row in gated["rows"])
    # The swap lasts for the run only.
    import shopping_agent.executor as executor_module
    from shopping_agent.gates import check_terms

    assert executor_module.check_terms is check_terms


def test_versions_in_force_are_worked_out_from_the_records():
    from shopping_agent import Policy

    def version(number, effective, expires=None):
        return Policy(
            policy_id=f"r-{number}",
            title="Returns",
            content="Returns.",
            source_id="shop/returns",
            version=number,
            effective_at=effective,
            expires_at=expires,
        )

    clock = datetime.fromisoformat(go_live.DEFAULT_CLOCK)
    records = [version("1", "2025-01-01", "2026-03-01"), version("2", "2026-03-01")]
    assert go_live.in_force_versions(records, clock) == {"shop/returns": {"2"}}
