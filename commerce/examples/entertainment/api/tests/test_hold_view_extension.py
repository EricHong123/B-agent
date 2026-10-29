# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""present_hold renders the session's own holds with the real countdown."""

import pytest

from commerce_common.presentation import EnrichmentContext
from entertainment.api.hold_view import HoldViewPayload, _enrich
from entertainment.api.ticketing import HOLD_TTL_S


def _context(backend, session):
    return EnrichmentContext(backend=backend, config=None, session=session, state=None)


async def test_no_hold_means_no_card(backend, session):
    with pytest.raises(ValueError, match="No hold"):
        await _enrich(HoldViewPayload(), _context(backend, session))


async def test_card_is_built_from_the_live_hold(backend, session, clock):
    await backend.add_to_cart(session, "AT-TIX-101-LOW", 2)
    clock.advance(60)

    enriched = await _enrich(
        HoldViewPayload(note="while you find your card"), _context(backend, session)
    )

    cart = enriched["cart"]
    assert cart["item_count"] == 2
    assert cart["subtotal"] == pytest.approx(178.0)
    assert cart["items"][0]["product_id"] == "AT-TIX-101-LOW"
    assert enriched["hold"]["seconds_remaining"] == HOLD_TTL_S - 60
    assert enriched["hold"]["hold_minutes"] == HOLD_TTL_S // 60
    assert enriched["note"] == "while you find your card"
    assert "suggestions" not in enriched


async def test_expired_holds_do_not_render(backend, session, clock):
    await backend.add_to_cart(session, "AT-TIX-101-LOW", 2)
    clock.advance(HOLD_TTL_S + 1)
    with pytest.raises(ValueError, match="No hold"):
        await _enrich(HoldViewPayload(), _context(backend, session))
