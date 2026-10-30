# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Which read the shopping grounding rules pin a turn to, under the default lexicons."""

import pytest

from commerce_common.grounding import first_forced_tool
from shopping_agent import Product, ShoppingAgentConfig, ShoppingSessionState
from shopping_agent.grounding import GROUNDING_RULES


def forced(text: str, config: ShoppingAgentConfig | None = None, state=None) -> str | None:
    return first_forced_tool(
        GROUNDING_RULES, config or ShoppingAgentConfig(), text, state or ShoppingSessionState()
    )


@pytest.mark.parametrize(
    ("text", "tool"),
    [
        ("How do returns work for opened items?", "search_policies"),
        ("Is there a restocking fee if I send the blender back?", "search_policies"),
        ("Where's my order?", "get_orders"),
        ("Just cancel the dog bed order, I'm done waiting.", "get_orders"),
        ("Add AR-1602 to my cart.", "get_product_details"),
        ("is AL-STAY-101 available in June?", "get_product_details"),
        ("transfer AT-TIX-104-GAF to my sister", "get_product_details"),
    ],
)
def test_terms_questions_order_asks_and_unseen_ids_each_force_their_read(text, tool):
    assert forced(text) == tool


@pytest.mark.parametrize(
    "text",
    [
        "show me lightweight tents under $200",
        "let's return to the tent options",  # a policy term without a question cue
        "add two of the camp mugs to my cart",
    ],
)
def test_shopping_turns_are_not_pinned(text):
    assert forced(text) is None


def test_five_digit_order_ids_are_not_product_ids():
    orders_off = ShoppingAgentConfig(order_grounding_gate=False)
    assert forced("What's the status of order AR-78214?", orders_off) is None


def test_precedence_runs_terms_then_orders_then_catalog():
    assert forced("Can I return my order?") == "search_policies"
    assert forced("What's the status of my order for AR-1602?") == "get_orders"


def test_an_id_the_session_already_saw_is_not_re_read():
    state = ShoppingSessionState()
    state.remember_products([Product(product_id="AR-1602", title="Lantern", price=39.0)])
    assert forced("add ar-1602 to my cart", state=state) is None
    assert forced("add AR-1603 to my cart", state=state) == "get_product_details"


@pytest.mark.parametrize(
    ("setting", "text"),
    [
        ("policy_grounding_gate", "How do returns work?"),
        ("order_grounding_gate", "Where's my order?"),
        ("catalog_grounding_gate", "Add AR-1602 to my cart."),
    ],
)
def test_each_rule_has_a_config_switch(setting, text):
    assert forced(text) is not None
    assert forced(text, ShoppingAgentConfig(**{setting: False})) is None


def test_a_deployment_extends_the_terms_lexicon():
    text = "how do data overage charges work on my plan?"
    assert forced(text) is None
    extended = ShoppingAgentConfig(
        policy_intent_terms=(*ShoppingAgentConfig().policy_intent_terms, "overage")
    )
    assert forced(text, extended) == "search_policies"
