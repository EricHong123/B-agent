# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Ownership checks on the hold, offer, and ticket routes, and the provenance gates on writes."""

from fastapi.testclient import TestClient

from demo_common import SESSION_HEADER
from demo_common.tests.fixtures import session_record
from entertainment.api import main


def _hold(client: TestClient, headers: dict[str, str], product_id: str, quantity: int = 1):
    body = {"product_id": product_id, "quantity": quantity}
    return client.post("/api/cart/add", json=body, headers=headers)


def _holds(headers: dict[str, str]):
    return main.engine.holds_for_session(headers[SESSION_HEADER])


def _events(headers: dict[str, str]) -> list[str]:
    return session_record(main, headers).pending_app_events


def test_the_token_decides_whose_order_and_wallet_a_read_returns(client, shopper):
    riley, casey = shopper("AT-TIX-101-LOW"), shopper(user_id="demo-user-2")
    _hold(client, riley, "AT-TIX-101-LOW")
    assert client.get("/api/cart", headers=riley).json()["item_count"] == 1
    assert client.get("/api/cart", headers=casey).json()["item_count"] == 0
    assert client.get("/api/holds", headers=casey).json()["holds"] == []
    assert client.get("/api/tickets", headers=riley).json()["tickets"]
    assert client.get("/api/tickets", headers=casey).json()["tickets"] == []
    main.backend.reset_session(riley[SESSION_HEADER])


def test_hold_button_goes_through_the_executor_and_its_provenance_gate(client, shopper):
    unseen = shopper()
    assert _hold(client, unseen, "AT-TIX-101-PIT").status_code == 400
    assert _holds(unseen) == []
    seen = shopper("AT-TIX-101-PIT")
    body = _hold(client, seen, "AT-TIX-101-PIT", quantity=2).json()
    assert body["cart"]["items"][0]["product_id"] == "AT-TIX-101-PIT"
    assert len(body["holds"]) == 1 and body["holds"][0]["seconds_remaining"] > 0
    assert "hold button" in _events(seen)[0]
    main.backend.reset_session(seen[SESSION_HEADER])


def test_hold_release_requires_ownership(client, shopper):
    owner = shopper("AT-TIX-101-LOW")
    _hold(client, owner, "AT-TIX-101-LOW")
    body = {"hold_id": _holds(owner)[0].hold_id}
    intruder = shopper(user_id="demo-user-2")
    assert client.post("/api/holds/release", json=body, headers=intruder).status_code == 403
    assert len(_holds(owner)) == 1
    assert client.post("/api/holds/release", json=body, headers=owner).status_code == 200
    assert _holds(owner) == []


def test_waitlist_join_is_provenance_gated(client, shopper):
    body = {"product_id": "AT-TIX-103-PIT", "quantity": 2}
    response = client.post("/api/waitlist/join", json=body, headers=shopper())
    assert response.status_code == 400 and "this session's results" in response.json()["detail"]


def test_waitlist_return_offer_and_claim_follow_the_offered_fan(client, shopper):
    fan = shopper("AT-TIX-103-PIT")
    body = {"product_id": "AT-TIX-103-PIT", "quantity": 2}
    assert client.post("/api/waitlist/join", json=body, headers=fan).status_code == 200
    returned = client.post("/api/demo/return", json=body).json()
    assert returned["remaining"] == 0  # the returned seats are reserved for the offer
    assert any("Return offer" in note for note in _events(fan))
    offers = client.get("/api/waitlist", headers=fan).json()["offers"]
    claim = {"offer_id": offers[0]["offer_id"]}

    intruder = shopper(user_id="demo-user-2")
    assert client.get("/api/waitlist", headers=intruder).json()["offers"] == []
    assert client.post("/api/waitlist/claim", json=claim, headers=intruder).status_code == 403
    claimed = client.post("/api/waitlist/claim", json=claim, headers=fan)
    assert claimed.status_code == 200 and claimed.json()["holds"][0]["quantity"] == 2
    main.backend.reset_session(fan[SESSION_HEADER])


def test_transfers_are_owner_only_to_stage_and_to_cancel(client, shopper):
    transfer = {"ticket_ids": ["AT-TKT-7003"], "recipient": "Sam"}
    intruder = shopper(user_id="demo-user-2")
    assert client.post("/api/tickets/transfer", json=transfer, headers=intruder).status_code == 403

    owner = shopper()
    staged = client.post("/api/tickets/transfer", json=transfer, headers=owner).json()["transfer"]
    cancel = {"transfer_id": staged["transfer_id"]}
    wallet = {
        t["ticket_id"]: t for t in client.get("/api/tickets", headers=owner).json()["tickets"]
    }
    assert wallet["AT-TKT-7003"]["status"] == "transfer_pending"
    assert wallet["AT-TKT-7003"]["transfer_recipient"] == "Sam"
    assert wallet["AT-TKT-7004"]["transfer_recipient"] is None
    assert (
        wallet["AT-TKT-7004"]["entry_code"] and wallet["AT-TKT-7004"]["entry_code_rotates_s"] == 60
    )

    assert (
        client.post("/api/tickets/transfer/cancel", json=cancel, headers=intruder).status_code
        == 403
    )
    assert (
        client.post("/api/tickets/transfer/cancel", json=cancel, headers=owner).status_code == 200
    )
    wallet = {
        t["ticket_id"]: t for t in client.get("/api/tickets", headers=owner).json()["tickets"]
    }
    assert wallet["AT-TKT-7003"]["status"] == "active"


def test_reset_releases_only_the_callers_own_holds(client, shopper):
    owner = shopper("AT-TIX-101-LOW")
    _hold(client, owner, "AT-TIX-101-LOW")
    other = shopper(user_id="demo-user-2")
    assert client.post("/api/reset", json={}, headers=other).status_code == 200
    assert len(_holds(owner)) == 1
    assert client.post("/api/reset", json={}, headers=owner).status_code == 200
    assert _holds(owner) == []
