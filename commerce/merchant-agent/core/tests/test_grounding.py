# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Which read the grounding rules pin a turn to, and which turns count as change requests."""

import pytest

from commerce_common.grounding import first_forced_tool
from merchant_agent import MerchantSessionState, StagedChange
from merchant_agent.grounding import GROUNDING_RULES, change_requested

APPLY_TURN = "There's a price change we settled on yesterday, go ahead and put it through."


def forced(config, text: str, state: MerchantSessionState | None = None) -> str | None:
    return first_forced_tool(GROUNDING_RULES, config, text, state or MerchantSessionState())


@pytest.mark.parametrize(
    ("text", "tool"),
    [
        ("How were sales last week?", "get_business_snapshot"),
        ("What's the conversion trend?", "get_business_snapshot"),
        (APPLY_TURN, "get_pending_changes"),
        ("Set the planter price to $17.50; we're applying it today.", "get_pending_changes"),
        ("Drop the price on the planter, then APPLY it.", "get_pending_changes"),
    ],
)
def test_performance_questions_and_apply_requests_each_force_their_read(config, text, tool):
    assert forced(config, text) == tool


@pytest.mark.parametrize(
    "text",
    [
        "Anything urgent this morning?",
        "Set the planter price to $17.50.",  # a change request without an apply phrase
        "The price we settled on yesterday, applying it now.",  # "set" only inside "settled"
        "Go ahead and stage the markdown you think gets them moving.",  # asks for staging
        "Update the planter description to mention the drainage hole.",
    ],
)
def test_operational_turns_are_not_pinned(config, text):
    assert forced(config, text) is None


def test_a_performance_question_outranks_the_queue_rule(config):
    text = "How did sales do after we set the new price? Apply the rest."
    assert forced(config, text) == "get_business_snapshot"


def test_the_queue_rule_yields_once_the_session_holds_a_staged_change(config):
    state = MerchantSessionState()
    state.seen_changes["chg-1"] = StagedChange.model_validate(
        {
            "change_id": "chg-1",
            "kind": "price_update",
            "status": "staged",
            "summary": "Planter to $17.50",
            "created_at": "2026-07-15T00:00:00Z",
            "created_by": "demo-operator",
        }
    )
    assert forced(config, APPLY_TURN, state) is None


@pytest.mark.parametrize(
    ("setting", "text"),
    [("metrics_grounding_gate", "How were sales last week?"), ("queue_grounding_gate", APPLY_TURN)],
)
def test_each_rule_has_a_config_switch(config, setting, text):
    assert forced(config, text) is not None
    assert forced(config.model_copy(update={setting: False}), text) is None


@pytest.mark.parametrize(
    ("text", "requested"),
    [
        ("Lower the price on the canvas tote", True),
        (
            "Take the storage bins from $29 down to $26 for the campaign.",
            True,
        ),  # amounts stand in for a term
        ("cut the tote by 15% for the weekend", True),
        ("Looks right, apply it.", False),  # approval verbs are not change cues
        ("The bins are $29 right now", False),  # an amount without a cue
        (
            "Update the planter description to mention the drainage hole",
            True,
        ),  # listing content counts
        ("Move the weekly review to Tuesday", False),  # a cue without a term
        ("How were sales last week?", False),
    ],
)
def test_change_requests_pair_a_change_cue_with_a_term_or_an_amount(config, text, requested):
    assert change_requested(config, text) is requested
    switched_off = config.model_copy(update={"staging_followthrough_gate": False})
    assert change_requested(switched_off, text) is False
