# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""scripts/eval_constraints.py: the scorer on hand-built turns and records, the card text
it reads from each component, the case files, and offline runs."""

import importlib.util
import sys
from argparse import Namespace
from datetime import datetime
from pathlib import Path

from shopping_agent import ProductDetails

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "eval_constraints.py"
spec = importlib.util.spec_from_file_location("eval_constraints", SCRIPT)
assert spec and spec.loader
constraints = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = constraints  # dataclasses resolve their module through sys.modules
spec.loader.exec_module(constraints)

CLOCK = datetime.fromisoformat(constraints.DEFAULT_CLOCK)  # Thu 2026-10-01


def record(product_id, price, **fields):
    return ProductDetails(product_id=product_id, title=f"Item {product_id}", price=price, **fields)


MATTRESS = record(
    "M-1",
    300.0,
    options={"size": ["twin", "queen"]},
    variants=[
        record("M-1-T", 300.0, option_values={"size": "twin"}, variant_of="M-1"),
        record("M-1-Q", 500.0, option_values={"size": "queen"}, variant_of="M-1"),
    ],
)
RECORDS = {
    "A": record("A", 40.0, attributes={"delivery": "Get it by Sat, Oct 3"}),
    "B": record("B", 90.0, attributes={"delivery": "Get it by Mon, Oct 5"}),
    "C": record("C", 30.0, in_stock=False),
    "M-1": MATTRESS,
    **{v.product_id: v for v in MATTRESS.variants},
}


def case(query="q", **given):
    return constraints.Case.from_entry({"id": "c", "q": "?", "query": query, "constraints": given})


def turn(answer="", shown=None, added=()):
    return constraints.Turn(answer, [], dict(shown or {}), list(added))


def judge(c, t, *, fits=True):
    return constraints.score(c, t, RECORDS.get, CLOCK, fits=fits)


def test_a_product_inside_every_constraint_passes_and_one_outside_is_a_violation():
    budget = case(max_price=50)
    assert not judge(budget, turn(shown={"A": ""})).violation
    result = judge(budget, turn(shown={"A": "", "B": "Great pick"}))
    assert result.violation and result.violating == {"B": ["price"]}
    assert result.checked == ["A", "B"]


def test_a_miss_marked_on_the_products_own_card_is_flagged_not_counted():
    budget = case(max_price=50)
    result = judge(budget, turn(shown={"B": "Over your budget, but the sturdiest"}))
    assert not result.violation and result.flagged == ["B"]
    # The mark has to name the miss: a stock note does not excuse a price.
    assert judge(budget, turn(shown={"B": "Sold out soon"})).violation
    # A cart add is never a marked miss.
    assert judge(budget, turn(shown={"B": "Over your budget"}, added=["B"])).violation


def test_each_kind_of_constraint_reads_the_record():
    by_saturday = case(deliver_by="2026-10-03")
    assert judge(by_saturday, turn(shown={"B": ""})).violating == {"B": ["date"]}
    assert not judge(by_saturday, turn(shown={"A": ""})).violation
    assert judge(case(), turn(shown={"C": ""})).violating == {"C": ["stock"]}
    unknown = judge(case(max_price=10), turn(shown={"Z-404": ""}))
    assert not unknown.violation and unknown.checked == []


def test_a_family_counts_through_its_closest_variant():
    queen = case(max_price=400, require={"size": "queen"})
    # The family's "from" price is under the budget; the queen it would sell is not.
    result = judge(queen, turn(shown={"M-1": ""}))
    assert result.violation and result.violating["M-1"] in (["price"], ["option"])
    assert judge(queen, turn(shown={"M-1": "The queen is over your budget"})).flagged == ["M-1"]
    assert judge(queen, turn(shown={"M-1-Q": ""})).violating == {"M-1-Q": ["price"]}
    assert not judge(case(require={"size": "queen"}), turn(shown={"M-1": ""})).violation


def test_asked_or_declined_is_scored_only_when_nothing_fits():
    budget = case(max_price=20)
    assert judge(budget, turn("Here you go.", {"A": ""}), fits=True).asked_or_declined is None
    said = judge(budget, turn("Nothing comes in under $20."), fits=False)
    assert said.asked_or_declined
    asked = judge(budget, turn("Could you go to $40?", {"A": "Over your budget"}), fits=False)
    assert asked.asked_or_declined and asked.flagged == ["A"]
    shown_as_match = judge(budget, turn("Nothing cheaper; this fits.", {"A": ""}), fits=False)
    assert not shown_as_match.asked_or_declined


def test_the_card_text_is_the_products_own():
    carousel = {
        "title": "Over your budget",
        "items": [{"product": {"product_id": "A", "title": "A", "price": 1.0}, "reason": "Fits"}],
    }
    assert constraints.shown_products(carousel) == {"A": "Fits"}
    comparison = {
        "entries": [
            {
                "product_id": "B",
                "pros": ["Sturdy"],
                "cons": ["Over your budget"],
                "product": {"product_id": "B", "title": "B", "price": 1.0},
            }
        ]
    }
    assert "Over your budget" in constraints.shown_products(comparison)["B"]
    plan = {
        "steps": [
            {
                "label": "Sleep",
                "detail": "Sold out until next week",
                "products": [
                    {
                        "product_id": "M-1",
                        "title": "M",
                        "price": 1.0,
                        "variants": [{"product_id": "M-1-Q", "title": "Q", "price": 1.0}],
                    }
                ],
            }
        ]
    }
    assert constraints.shown_products(plan) == {"M-1": "Sleep Sold out until next week"}


def test_the_case_files_hold_ten_cases_per_vertical_with_both_outcomes():
    for vertical in constraints.VERTICALS:
        backend = constraints.build_backend(vertical, CLOCK)
        cases = constraints.load_cases(vertical)
        assert len(cases) == 10
        fits = [bool(constraints.fitting(c, backend, CLOCK)) for c in cases]
        assert any(fits) and not all(fits)


def args(**overrides):
    defaults = dict(
        vertical="retail",
        mode="offline",
        clock=constraints.DEFAULT_CLOCK,
        limit=0,
        no_filters=False,
        failures=False,
        json=None,
    )
    return Namespace(**defaults | overrides)


async def test_search_filters_lower_the_offline_violation_rate():
    filtered = (await constraints.evaluate(args()))["total"]
    words_only = (await constraints.evaluate(args(no_filters=True)))["total"]
    assert filtered.cases == words_only.cases == 10
    assert filtered.violated < words_only.violated


async def test_the_offline_responder_marks_a_retry_and_says_nothing_fits():
    tent = case("backpacking tent", max_price=5, require={"title": "Tent"})
    backend = constraints.build_backend("retail", CLOCK)
    client, config = constraints.agent_setup("retail", "offline")
    played = await constraints.run_turn(
        tent, "retail", backend, mode="offline", clock=CLOCK, client=client, config=config
    )
    assert played.tools.count("search_products") == 2 and played.shown
    result = constraints.score(tent, played, backend.product, CLOCK, fits=False)
    assert not result.violation and result.flagged and result.asked_or_declined
