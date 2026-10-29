# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Semantics of the shared session gates in merchant_agent.gates."""

from datetime import UTC, datetime, timedelta

from merchant_agent import (
    ActorKind,
    Campaign,
    ChangeItem,
    ChangeKind,
    Listing,
    StagedChange,
)
from merchant_agent.gates import (
    check_apply_change,
    check_campaign_provenance,
    check_discard_change,
    check_listing_provenance,
    check_listing_record_read,
    take_discard_actor_kind,
)


def _staged_change(change_id: str = "chg-0001", *, after: float = 105.0) -> StagedChange:
    return StagedChange(
        change_id=change_id,
        kind=ChangeKind.PRICE_UPDATE,
        summary="Price move",
        items=[ChangeItem(target="L-201", field="price", before=100.0, after=after)],
        created_at=datetime.now(UTC),
        created_by="demo-operator",
    )


# -- provenance ----------------------------------------------------------------------------


def test_listing_provenance_names_the_unknown_ids(state):
    refusal = check_listing_provenance(state, ["L-201", "L-999"])
    assert refusal is not None
    assert refusal.blocked == "provenance"
    assert "L-201" in refusal.result_text and "L-999" in refusal.result_text

    state.remember_listings([Listing(listing_id="L-201", title="Planter", price=18.0)])
    refusal = check_listing_provenance(state, ["L-201", "L-999"])
    assert refusal is not None and "L-201" not in refusal.result_text
    assert check_listing_provenance(state, ["L-201"]) is None


def test_listing_record_read_gates_content_edits(state):
    # A search row grants id provenance but not record provenance.
    state.remember_listings([Listing(listing_id="L-201", title="Planter", price=18.0)])
    refusal = check_listing_record_read(state, "L-201")
    assert refusal is not None
    assert refusal.blocked == "provenance"
    assert "get_listing" in refusal.result_text

    state.remember_listing_record(Listing(listing_id="L-201", title="Planter", price=18.0))
    assert check_listing_record_read(state, "L-201") is None


def test_campaign_provenance_gates_only_existing_campaign_ids(state):
    # A new campaign has no id to check.
    assert check_campaign_provenance(state, None) is None
    assert check_campaign_provenance(state, "") is None

    refusal = check_campaign_provenance(state, "C-201")
    assert refusal is not None
    assert refusal.blocked == "provenance"
    assert "C-201" in refusal.result_text and "get_campaign_performance" in refusal.result_text

    state.remember_campaigns(
        [
            Campaign(
                campaign_id="C-201",
                name="Spring refresh",
                status="active",
                budget=400.0,
                spend=120.0,
                revenue=560.0,
            )
        ]
    )
    assert check_campaign_provenance(state, "C-201") is None


# -- the apply gate ---------------------------------------------------------------------


def test_apply_gate_refuses_unknown_change_ids(state, config):
    refusal = check_apply_change(state, config, "chg-9999")
    assert refusal is not None
    assert refusal.blocked == "provenance"
    assert "not staged or listed in this session" in refusal.result_text


def test_apply_gate_rechecks_guardrails_against_current_config(state, config):
    # 100 -> 105 is a 5% move, within the default 20% cap.
    state.remember_change(_staged_change(after=105.0))
    assert check_apply_change(state, config, "chg-0001") is None
    tightened = config.model_copy(update={"max_price_delta_pct": 1.0})
    refusal = check_apply_change(state, tightened, "chg-0001")
    assert refusal is not None
    assert refusal.blocked == "guardrail"
    assert "can no longer be applied" in refusal.result_text


def test_apply_gate_enforces_host_verified_approval(state, config):
    strict = config.model_copy(update={"require_host_approval": True})
    state.remember_change(_staged_change())
    refusal = check_apply_change(state, strict, "chg-0001")
    assert refusal is not None
    assert refusal.blocked == "approval"
    assert strict.approval_surface in refusal.result_text
    state.approved_change_ids.add("chg-0001")
    assert check_apply_change(state, strict, "chg-0001") is None


def test_apply_gate_refuses_an_expired_change_whatever_its_approval(state, config):
    change = _staged_change()
    state.remember_change(
        change.model_copy(
            update={
                "created_at": change.created_at
                - timedelta(minutes=config.staged_change_ttl_minutes)
            }
        )
    )
    state.approved_change_ids.add("chg-0001")
    refusal = check_apply_change(state, config, "chg-0001")
    assert refusal is not None
    assert refusal.blocked == "approval"
    assert "expired unapproved" in refusal.result_text


# -- discard: provenance and attribution --------------------------------------------------


def test_discard_gate_refuses_unknown_change_ids(state):
    refusal = check_discard_change(state, "chg-9999")
    assert refusal is not None
    assert refusal.blocked == "provenance"
    assert "nothing to discard" in refusal.result_text
    state.remember_change(_staged_change())
    assert check_discard_change(state, "chg-0001") is None


def test_discard_attribution_follows_host_written_state(state):
    state.remember_change(_staged_change())
    assert take_discard_actor_kind(state, "chg-0001") is ActorKind.AGENT
    # The host marker is consumed by the discard it authorized.
    state.host_action_change_ids.add("chg-0001")
    assert take_discard_actor_kind(state, "chg-0001") is ActorKind.OPERATOR
    assert "chg-0001" not in state.host_action_change_ids
    assert take_discard_actor_kind(state, "chg-0001") is ActorKind.AGENT
