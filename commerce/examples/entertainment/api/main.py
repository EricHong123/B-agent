# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""ACME Tickets example API: the mock box office behind the shared storefront routes, the
box-office router under /api/merchant, and the ticketing routes below.

    uvicorn entertainment.api.main:app --app-dir examples --reload --port 8003

    GET    /api/holds                    the session's holds with their expiry times
    POST   /api/holds/release            release one hold early
    POST   /api/cart/add                 the hold button
    POST   /api/waitlist/join            join a sold-out tier's waitlist
    GET    /api/waitlist                 positions and open return offers
    POST   /api/waitlist/claim           claim a return offer inside its window
    GET    /api/tickets                  the wallet, with rotating entry codes
    POST   /api/tickets/transfer         stage a transfer; /cancel takes it back
    POST   /api/demo/return              demo control: a fan returns tickets (public)

The session says who is asking; the engine then checks that the hold, offer, or ticket named
belongs to that user (403 otherwise). A waitlist join is provenance-gated like a cart add.
"""

from __future__ import annotations

from fastapi import HTTPException
from pydantic import BaseModel, Field

from commerce_common.memory import InMemoryMemoryStore
from demo_common import (
    REPO_ROOT,
    CartAddRequest,
    MemorySeeder,
    SessionRecord,
    build_storefront_host,
    load_demo_env,
    model_client,
)
from shopping_agent.fencing import STOREFRONT_FENCE
from shopping_agent_runtime import ShoppingAgent

from .agent_config import build_shopping_config
from .hold_view import build_hold_view_extension
from .merchant import create_merchant_router
from .mock_ticketing import DATA_DIR, MockTicketing, TicketingToolExecutor
from .ticketing import (
    HOLD_TTL_S,
    OFFER_CLAIM_WINDOW_S,
    NotFoundError,
    OwnershipError,
    StateError,
    TicketingError,
)
from .venue_map import build_venue_map_extension

load_demo_env(DATA_DIR.parent)

backend = MockTicketing()
engine = backend.engine
agent = ShoppingAgent(
    backend=backend,
    skills_dir=REPO_ROOT / "shopping-agent" / "skills",
    config=build_shopping_config(),
    client=model_client(),
    memory_store=InMemoryMemoryStore(),
    extra_presentation_tools=[build_venue_map_extension(), build_hold_view_extension()],
    executor_class=TicketingToolExecutor,
)


def holds_payload(record: SessionRecord) -> dict:
    return {
        "hold_minutes": HOLD_TTL_S // 60,
        "offer_window_minutes": OFFER_CLAIM_WINDOW_S // 60,
        "holds": [
            {
                "hold_id": hold.hold_id,
                "product_id": hold.product_id,
                "quantity": hold.quantity,
                "expires_at": hold.expires_at.isoformat(),
                "seconds_remaining": engine.seconds_until(hold.expires_at),
            }
            for hold in engine.holds_for_session(record.session_id)
        ],
    }


def deliver_notifications() -> None:
    """Queue the engine's proactive notices (a return offer, an expiry) on every live
    session of the user they concern; the next turn hands them to the agent."""
    for note in engine.collect_notifications():
        for record in host.sessions.sessions_for_user(note.user_id):
            record.pending_app_events.append(note.text)
            host.sessions.save(record)  # outside a request, so nothing else writes it back


host = build_storefront_host(
    title="ACME Tickets demo API",
    example_root=DATA_DIR.parent,
    backend=backend,
    agent=agent,
    memory_seeder=MemorySeeder(DATA_DIR / "memory-seed.json"),
    product_of=backend.get_live_product,
    cart_extras=holds_payload,
    before_turn=deliver_notifications,
)
app = host.app
app.include_router(create_merchant_router(backend, InMemoryMemoryStore()), prefix="/api/merchant")

_STATUS_OF_ERROR = ((OwnershipError, 403), (NotFoundError, 404), (StateError, 409))


def http_error(error: TicketingError) -> HTTPException:
    status = next((code for kind, code in _STATUS_OF_ERROR if isinstance(error, kind)), 400)
    return HTTPException(status_code=status, detail=str(error))


# ---------------------------------------------------------------------------
# Holds
# ---------------------------------------------------------------------------


@app.post("/api/cart/add")
async def cart_add(request: CartAddRequest, record: host.CurrentSession) -> dict:
    if request.product_id not in backend.products:
        raise HTTPException(status_code=404, detail="Product not found")
    return await host.direct_add(
        record,
        request,
        note=(
            "Customer tapped the hold button on {title} ({product_id}), quantity {quantity} "
            "— an 8-minute hold is now running."
        ),
    )


@app.get("/api/holds")
async def get_holds(record: host.CurrentSession) -> dict:
    return holds_payload(record)


class HoldReleaseRequest(BaseModel):
    hold_id: str = Field(min_length=1, max_length=80)


@app.post("/api/holds/release")
async def release_hold(request: HoldReleaseRequest, record: host.CurrentSession) -> dict:
    try:
        engine.release_hold_by_id(request.hold_id, record.user_id)
    except TicketingError as error:
        raise http_error(error) from error
    record.pending_app_events.append(
        f"Customer released hold {request.hold_id} early — those tickets are back on sale."
    )
    return {"ok": True, **holds_payload(record)}


# ---------------------------------------------------------------------------
# Waitlist and return offers
# ---------------------------------------------------------------------------


class WaitlistJoinRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=80)
    quantity: int = Field(default=1, ge=1, le=8)


@app.post("/api/waitlist/join")
async def waitlist_join(request: WaitlistJoinRequest, record: host.CurrentSession) -> dict:
    if request.product_id not in record.state.seen_products:
        raise HTTPException(
            status_code=400,
            detail="That tier isn't in this session's results; search for the event first.",
        )
    try:
        position = engine.join_waitlist(
            record.user_id, record.session_id, request.product_id, request.quantity
        )
    except TicketingError as error:
        raise http_error(error) from error
    record.pending_app_events.append(
        f"Customer joined the waitlist for {request.product_id} "
        f"(quantity {request.quantity}) — position {position} in line."
    )
    return {"ok": True, "position": position}


@app.get("/api/waitlist")
async def waitlist_status(record: host.CurrentSession) -> dict:
    return {
        "entries": [
            {"product_id": entry.product_id, "quantity": entry.quantity, "position": position}
            for entry, position in engine.waitlist_entries_for(record.user_id)
        ],
        "offers": [
            {
                "offer_id": offer.offer_id,
                "product_id": offer.product_id,
                "quantity": offer.quantity,
                "expires_at": offer.expires_at.isoformat(),
                "seconds_remaining": engine.seconds_until(offer.expires_at),
            }
            for offer in engine.offers_for(record.user_id)
        ],
    }


class OfferClaimRequest(BaseModel):
    offer_id: str = Field(min_length=1, max_length=80)


@app.post("/api/waitlist/claim")
async def waitlist_claim(request: OfferClaimRequest, record: host.CurrentSession) -> dict:
    try:
        hold = engine.claim_offer(request.offer_id, record.user_id, record.session_id)
    except TicketingError as error:
        raise http_error(error) from error
    # The server resolved the tier itself, so it becomes provenance for the agent's
    # follow-up actions on it.
    live = backend.get_live_product(hold.product_id)
    if live is not None:
        record.state.remember_products([live])
    record.pending_app_events.append(
        f"Customer claimed return offer {request.offer_id}: {hold.quantity} ticket(s) for "
        f"{hold.product_id} are now held with the 8-minute timer running."
    )
    return {"ok": True, **holds_payload(record)}


class DemoReturnRequest(BaseModel):
    product_id: str = Field(min_length=1, max_length=80)
    quantity: int = Field(default=2, ge=1, le=8)


@app.post("/api/demo/return")
async def demo_return(request: DemoReturnRequest) -> dict:
    """Stands in for the inventory system's returns feed, so the return-offer arc can be
    shown on demand. It acts for no user, so it takes no session; the offer still goes to
    whoever heads the waitlist, and only their session can claim it."""
    if request.product_id not in backend.products:
        raise HTTPException(status_code=404, detail="Product not found")
    try:
        engine.record_return(request.product_id, request.quantity)
    except TicketingError as error:
        raise http_error(error) from error
    deliver_notifications()
    return {"ok": True, "remaining": engine.remaining(request.product_id)}


# ---------------------------------------------------------------------------
# Tickets and transfers
# ---------------------------------------------------------------------------


@app.get("/api/tickets")
async def get_tickets(record: host.CurrentSession) -> dict:
    recipient_of = {
        ticket_id: transfer.recipient
        for transfer in engine.transfers_for(record.user_id)
        if transfer.status == "pending"
        for ticket_id in transfer.ticket_ids
    }
    tickets = []
    for ticket in engine.tickets_for(record.user_id):
        product = backend.products.get(ticket.product_id)
        attributes = product.attributes if product else {}
        tickets.append(
            {
                "ticket_id": ticket.ticket_id,
                "event": attributes.get("event_name") if product else ticket.product_id,
                "date": attributes.get("event_date"),
                "venue": attributes.get("venue"),
                "tier": attributes.get("tier"),
                "seat": ticket.seat,
                "status": ticket.status,
                "entry_code": engine.barcode(ticket.ticket_id),
                "entry_code_rotates_s": 60,
                "transfer_recipient": recipient_of.get(ticket.ticket_id),
            }
        )
    return {"tickets": tickets}


class TransferRequest(BaseModel):
    ticket_ids: list[str] = Field(min_length=1, max_length=4)
    recipient: str = Field(min_length=1, max_length=80)


@app.post("/api/tickets/transfer")
async def transfer_tickets(request: TransferRequest, record: host.CurrentSession) -> dict:
    try:
        transfer = engine.initiate_transfer(
            record.user_id, request.ticket_ids, request.recipient.strip()
        )
    except TicketingError as error:
        raise http_error(error) from error
    # The recipient is client text and the note enters model context unfenced.
    safe_recipient = STOREFRONT_FENCE.sanitize_text(transfer.recipient, max_chars=80)
    record.pending_app_events.append(
        f"Customer started transfer {transfer.transfer_id} of {len(transfer.ticket_ids)} "
        f"ticket(s) to {safe_recipient}. It stays pending (and cancelable) until accepted."
    )
    return {
        "ok": True,
        "transfer": {
            "transfer_id": transfer.transfer_id,
            "ticket_ids": transfer.ticket_ids,
            "recipient": transfer.recipient,
            "status": transfer.status,
        },
    }


class TransferCancelRequest(BaseModel):
    transfer_id: str = Field(min_length=1, max_length=80)


@app.post("/api/tickets/transfer/cancel")
async def cancel_transfer(request: TransferCancelRequest, record: host.CurrentSession) -> dict:
    try:
        transfer = engine.cancel_transfer(record.user_id, request.transfer_id)
    except TicketingError as error:
        raise http_error(error) from error
    record.pending_app_events.append(
        f"Customer cancelled transfer {transfer.transfer_id} — the tickets are back in "
        "their wallet."
    )
    return {"ok": True, "status": transfer.status}
