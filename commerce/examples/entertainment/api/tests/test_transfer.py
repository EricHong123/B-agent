# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Transfers are owner-checked and atomic; entry codes rotate on the clock."""

import pytest

from entertainment.api.ticketing import (
    BARCODE_ROTATION_S,
    NotFoundError,
    OwnershipError,
    StateError,
    Ticket,
)


def test_owner_can_stage_a_transfer_and_cancel_it(backend):
    transfer = backend.engine.initiate_transfer("demo-user", ["AT-TKT-7001", "AT-TKT-7002"], "Sam")
    assert transfer.status == "pending"
    statuses = {t.ticket_id: t.status for t in backend.engine.tickets_for("demo-user")}
    assert statuses["AT-TKT-7001"] == statuses["AT-TKT-7002"] == "transfer_pending"

    backend.engine.cancel_transfer("demo-user", transfer.transfer_id)
    statuses = {t.ticket_id: t.status for t in backend.engine.tickets_for("demo-user")}
    assert statuses["AT-TKT-7001"] == statuses["AT-TKT-7002"] == "active"


def test_non_owner_cannot_transfer_even_with_a_real_ticket_id(backend):
    with pytest.raises(OwnershipError):
        backend.engine.initiate_transfer("demo-user-2", ["AT-TKT-7001"], "Casey")
    statuses = {t.ticket_id: t.status for t in backend.engine.tickets_for("demo-user")}
    assert statuses["AT-TKT-7001"] == "active"


def test_mixed_ownership_batch_stages_nothing(backend):
    backend.engine._tickets["AT-TKT-9999"] = Ticket(  # a second user's ticket
        ticket_id="AT-TKT-9999",
        owner_id="demo-user-2",
        product_id="AT-TIX-105-BAL",
        order_id="AT-ORD-0000",
        seat="Balcony A1",
    )
    with pytest.raises(OwnershipError):
        backend.engine.initiate_transfer("demo-user", ["AT-TKT-7001", "AT-TKT-9999"], "Sam")
    assert backend.engine._tickets["AT-TKT-7001"].status == "active"


def test_unknown_ticket_is_not_found(backend):
    with pytest.raises(NotFoundError):
        backend.engine.initiate_transfer("demo-user", ["AT-TKT-0000"], "Sam")


def test_pending_ticket_cannot_be_transferred_twice(backend):
    backend.engine.initiate_transfer("demo-user", ["AT-TKT-7001"], "Sam")
    with pytest.raises(StateError, match="not transferable"):
        backend.engine.initiate_transfer("demo-user", ["AT-TKT-7001"], "Someone Else")


def test_only_the_initiator_can_cancel(backend):
    transfer = backend.engine.initiate_transfer("demo-user", ["AT-TKT-7001"], "Sam")
    with pytest.raises(OwnershipError):
        backend.engine.cancel_transfer("demo-user-2", transfer.transfer_id)


def test_entry_code_rotates_with_the_server_clock(backend, clock):
    first = backend.engine.barcode("AT-TKT-7001")
    assert backend.engine.barcode("AT-TKT-7001") == first  # stable within a window
    clock.advance(BARCODE_ROTATION_S)
    assert backend.engine.barcode("AT-TKT-7001") != first
    assert backend.engine.barcode("AT-TKT-7002") != backend.engine.barcode("AT-TKT-7001")
