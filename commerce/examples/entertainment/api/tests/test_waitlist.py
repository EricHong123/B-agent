# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Waitlists are FIFO; offers belong to one fan and roll on expiry."""

import pytest

from entertainment.api.ticketing import (
    OFFER_CLAIM_WINDOW_S,
    SIM_FAN_DEPART_INTERVAL_S,
    HoldLimitError,
    OwnershipError,
    StateError,
)

SOLD_OUT = "AT-TIX-103-PIT"
# Sold out, with 2 simulated fans pre-queued by inventory.json's waitlist_sim.
SOLD_OUT_SEEDED = "AT-TIX-103-LOW"


def test_cannot_waitlist_a_tier_that_is_still_on_sale(backend):
    with pytest.raises(StateError, match="still has open tickets"):
        backend.engine.join_waitlist("demo-user", "s-1", "AT-TIX-101-PIT", 2)


def test_waitlist_is_fifo_and_dedupes_per_user(backend):
    assert backend.engine.join_waitlist("demo-user", "s-1", SOLD_OUT, 2) == 1
    assert backend.engine.join_waitlist("demo-user-2", "s-2", SOLD_OUT, 1) == 2
    # Re-joining updates the quantity without losing the place in line.
    assert backend.engine.join_waitlist("demo-user", "s-1", SOLD_OUT, 1) == 1


def test_return_creates_an_offer_for_the_head_of_the_line(backend, clock):
    backend.engine.join_waitlist("demo-user", "s-1", SOLD_OUT, 2)
    backend.engine.join_waitlist("demo-user-2", "s-2", SOLD_OUT, 2)
    offer = backend.engine.record_return(SOLD_OUT, 2)
    assert offer.user_id == "demo-user" and offer.quantity == 2
    assert any(n.user_id == "demo-user" for n in backend.engine.collect_notifications())
    assert (offer.expires_at - clock()).total_seconds() == OFFER_CLAIM_WINDOW_S
    # The returned tickets are reserved for the offer.
    assert backend.engine.remaining(SOLD_OUT) == 0


def test_claim_converts_the_offer_into_a_hold(backend):
    backend.engine.join_waitlist("demo-user", "s-1", SOLD_OUT, 2)
    offer = backend.engine.record_return(SOLD_OUT, 2)
    hold = backend.engine.claim_offer(offer.offer_id, "demo-user", "s-1")
    assert hold.product_id == SOLD_OUT and hold.quantity == 2
    assert backend.engine.remaining(SOLD_OUT) == 0  # the hold keeps them reserved


def test_only_the_offered_fan_can_claim(backend):
    backend.engine.join_waitlist("demo-user", "s-1", SOLD_OUT, 2)
    offer = backend.engine.record_return(SOLD_OUT, 2)
    with pytest.raises(OwnershipError):
        backend.engine.claim_offer(offer.offer_id, "demo-user-2", "s-2")
    backend.engine.claim_offer(offer.offer_id, "demo-user", "s-1")


def test_expired_offer_rolls_to_the_next_fan(backend, clock):
    backend.engine.join_waitlist("demo-user", "s-1", SOLD_OUT, 2)
    backend.engine.join_waitlist("demo-user-2", "s-2", SOLD_OUT, 1)
    first_offer = backend.engine.record_return(SOLD_OUT, 2)
    clock.advance(OFFER_CLAIM_WINDOW_S + 1)
    with pytest.raises(StateError, match="no longer open"):
        backend.engine.claim_offer(first_offer.offer_id, "demo-user", "s-1")
    (rolled,) = backend.engine.offers_for("demo-user-2")
    assert rolled.quantity == 1  # capped at what the next fan asked for
    notices = backend.engine.collect_notifications()
    assert [n.user_id for n in notices] == ["demo-user", "demo-user", "demo-user-2"]
    assert "went to the next fan" in notices[1].text


def test_expired_offer_with_nobody_behind_says_the_tickets_are_back_on_sale(backend, clock):
    backend.engine.join_waitlist("demo-user", "s-1", SOLD_OUT, 2)
    backend.engine.record_return(SOLD_OUT, 2)
    clock.advance(OFFER_CLAIM_WINDOW_S + 1)
    backend.engine.sweep()
    assert backend.engine.remaining(SOLD_OUT) == 2
    (offered, expired) = backend.engine.collect_notifications()
    assert "back on sale" in expired.text and "next fan" not in expired.text


def test_return_with_no_waitlist_reopens_inventory(backend):
    assert backend.engine.remaining(SOLD_OUT) == 0
    assert backend.engine.record_return(SOLD_OUT, 2) is None
    assert backend.engine.remaining(SOLD_OUT) == 2


def test_return_on_a_tier_with_nothing_sold_is_refused(backend):
    backend.engine._rows[SOLD_OUT].sold = 0
    capacity = backend.engine.capacity(SOLD_OUT)
    with pytest.raises(StateError, match="no sold tickets"):
        backend.engine.record_return(SOLD_OUT, 2)
    assert backend.engine.remaining(SOLD_OUT) == capacity


def test_seeded_sim_fans_hold_real_positions_and_depart_on_schedule(backend, clock):
    assert backend.engine.join_waitlist("demo-user", "s-1", SOLD_OUT_SEEDED, 2) == 3

    def position() -> int:
        ((_, at),) = backend.engine.waitlist_entries_for("demo-user")
        return at

    assert position() == 3
    clock.advance(SIM_FAN_DEPART_INTERVAL_S + 1)
    assert position() == 2
    clock.advance(SIM_FAN_DEPART_INTERVAL_S)
    assert position() == 1


def test_sim_fans_wait_indefinitely_until_a_real_fan_joins(backend, clock):
    clock.advance(SIM_FAN_DEPART_INTERVAL_S * 100)
    assert backend.engine.join_waitlist("demo-user", "s-1", SOLD_OUT_SEEDED, 2) == 3


def test_return_offers_skip_simulated_fans(backend):
    backend.engine.join_waitlist("demo-user", "s-1", SOLD_OUT_SEEDED, 2)
    offer = backend.engine.record_return(SOLD_OUT_SEEDED, 2)
    assert offer is not None and (offer.user_id, offer.quantity) == ("demo-user", 2)


def test_refused_claim_leaves_the_offer_open(backend):
    # 8 held after the first claim, which is the per-event cap.
    backend.engine.join_waitlist("demo-user", "s-1", SOLD_OUT, 8)
    offer = backend.engine.record_return(SOLD_OUT, 8)
    backend.engine.claim_offer(offer.offer_id, "demo-user", "s-1")
    # Claiming 2 more would exceed the cap.
    backend.engine.join_waitlist("demo-user", "s-1", SOLD_OUT, 2)
    second = backend.engine.record_return(SOLD_OUT, 2)
    with pytest.raises(HoldLimitError):
        backend.engine.claim_offer(second.offer_id, "demo-user", "s-1")
    assert second.status == "open"  # still claimable once the first hold clears
    assert backend.engine.offers_for("demo-user") == [second]


def test_waitlist_and_offers_keep_sold_together_sets_whole(backend):
    # AT-RSL-203 is a resale pair (sold_together=2) with two tickets; mark both sold.
    pair = "AT-RSL-203"
    backend.engine._rows[pair].sold = 2
    with pytest.raises(StateError, match="sets of 2"):
        backend.engine.join_waitlist("demo-user", "s-1", pair, 1)
    assert backend.engine.join_waitlist("demo-user", "s-1", pair, 2) == 1
    offer = backend.engine.record_return(pair, 2)
    assert offer.quantity == 2
    assert backend.engine.claim_offer(offer.offer_id, "demo-user", "s-1").quantity == 2


def test_a_return_smaller_than_a_set_makes_no_offer(backend):
    pair = "AT-RSL-203"
    backend.engine._rows[pair].sold = 2
    backend.engine.join_waitlist("demo-user", "s-1", pair, 2)
    # The odd ticket sits unsold until its pair comes back; the fan keeps their place.
    assert backend.engine.record_return(pair, 1) is None
    assert backend.engine.remaining(pair) == 1
    assert backend.engine.waitlist_entries_for("demo-user")[0][1] == 1
