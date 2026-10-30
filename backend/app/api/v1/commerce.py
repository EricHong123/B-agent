"""Commerce agents API: the buyer assistant, the operations assistant and their admin.

Buyer routes accept either a buyer-portal invite token in ``X-Buyer-Token`` (the
customer's own access) or a signed-in staff user acting for a named customer. Operations routes are staff-only, and a staged
change is applied only from the console's approval route by an operator or admin; an
approval typed in chat sets nothing (``require_host_approval``).

Every session-scoped route takes the session id in ``X-Commerce-Session`` and checks that
it belongs to the caller; the record is written back with a version check when the
request ends, and a streamed turn writes it again when the stream closes.
"""

import asyncio
import hashlib
import logging
import secrets
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, AsyncIterator, Dict, List, Literal, Optional, Set
from uuid import UUID

import anthropic
from fastapi import APIRouter, Depends, Header, HTTPException, Query
from fastapi.responses import StreamingResponse
from jose import JWTError, jwt
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session
from starlette.background import BackgroundTask

from commerce_common.openai_compat import ModelAuthenticationError, ModelProviderError
from commerce_common.streaming import AgentEvent, to_sse
from merchant_agent import ChangeNotApplicable, ChangeStatus, MerchantSessionContext
from merchant_agent.executor import MerchantToolExecutor
from merchant_agent.gates import STAGING_FOLLOWTHROUGH_REMINDER
from shopping_agent import PageContext, SearchFilters, ShoppingSessionContext
from shopping_agent.fencing import STOREFRONT_FENCE
from shopping_agent.serialization import cart_payload

from app.api.v1.auth import get_current_active_user
from app.commerce.catalog import families, to_listing
from app.commerce.merchant import MERCHANT_ID
from app.commerce.operations import RequestedHandoffReason, handoff_request, metrics_report
from app.commerce.rfq import submit_rfq
from app.commerce.runtime import CommerceRuntime, get_commerce_runtime
from app.commerce.storefront import customer_subject
from app.commerce.stores import SessionConflict, SessionRecord, UnknownSession, utcnow
from app.config import settings
from app.db import get_db
from app.models.database import (
    BuyerPortalInvite,
    CatalogProduct,
    CommerceOperationEvent,
    Customer,
    TradeTerm,
    User,
)
from app.services.fulfillment import FulfillmentConflict, FulfillmentNotFound


logger = logging.getLogger(__name__)
router = APIRouter()

SESSION_HEADER = "X-Commerce-Session"
BUYER_TOKEN_HEADER = "X-Buyer-Token"
Locale = Literal["en", "zh"]
REPLY_LANGUAGES = {"en": "English", "zh": "Simplified Chinese"}
ERROR_TEXT = {
    "no_key": {
        "en": "The commerce assistants have no AI model configured. An administrator can set it in Settings (AI routing) or the COMMERCE_MODEL_* variables.",
        "zh": "商务助手尚未配置 AI 模型。请管理员在“设置 → AI 路由”或 COMMERCE_MODEL_* 环境变量中配置。",
    },
    "auth_failed": {
        "en": "The AI provider rejected the configured key. Ask an administrator to check the AI settings.",
        "zh": "AI 供应商拒绝了已配置的密钥，请联系管理员检查 AI 设置。",
    },
    "provider_error": {
        "en": "The AI provider could not complete the request ({status}). Please try again.",
        "zh": "AI 供应商暂时无法完成请求（{status}），请稍后重试。",
    },
    "generic": {
        "en": "Something went wrong on our side. Please try again.",
        "zh": "系统出了点问题，请稍后重试。",
    },
}
HANDOFF_NOTES = {
    "buyer": "The buyer asked for a person; ticket {ticket} is open and the sales team will follow up.",
    "merchant": "The operator escalated to the team; ticket {ticket} is open and a person will follow up.",
}
_background: Set[asyncio.Task] = set()


def spawn(coro) -> None:
    task = asyncio.ensure_future(coro)
    _background.add(task)
    task.add_done_callback(_background.discard)


def runtime(rt: CommerceRuntime = Depends(get_commerce_runtime)) -> CommerceRuntime:
    if not settings.COMMERCE_ENABLED:
        raise HTTPException(status_code=404, detail="Commerce assistants are disabled")
    return rt


def require_admin(current_user: User = Depends(get_current_active_user)) -> User:
    if not current_user.is_superuser:
        raise HTTPException(status_code=403, detail="Admin access required")
    return current_user


def can_approve(user: User) -> bool:
    return bool(user.is_superuser or user.role in ("admin", "operator"))


def now_utc() -> datetime:
    return datetime.now(timezone.utc)


# ---------------------------------------------------------------------------
# Principals
# ---------------------------------------------------------------------------


class BuyerPrincipal(BaseModel):
    model_config = ConfigDict(arbitrary_types_allowed=True)

    customer_id: Optional[int]
    staff: Optional[Any] = None
    invite_id: Optional[UUID] = None
    owner_user_id: int


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def optional_staff_user(
    authorization: Optional[str] = Header(default=None),
    db: Session = Depends(get_db),
) -> Optional[User]:
    """The signed-in staff user, or None; buyer routes also accept a portal token."""
    scheme, _, token = (authorization or "").partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=["HS256"])
    except JWTError:
        return None
    user = db.query(User).filter(User.id == payload.get("sub")).first()
    return user if user is not None and user.is_active else None


def buyer_principal(
    buyer_token: Optional[str] = Header(default=None, alias=BUYER_TOKEN_HEADER),
    staff: Optional[User] = Depends(optional_staff_user),
    db: Session = Depends(get_db),
) -> BuyerPrincipal:
    """A buyer-portal token in ``X-Buyer-Token`` acts for its customer; otherwise a signed-in
    staff user acts for the customer a session names."""
    if buyer_token:
        invite = (
            db.query(BuyerPortalInvite)
            .filter(BuyerPortalInvite.token_hash == _hash(buyer_token))
            .one_or_none()
        )
        if invite is None or invite.revoked_at is not None or invite.expires_at < utcnow():
            raise HTTPException(status_code=401, detail="This buyer portal link is not valid")
        invite.last_used_at = utcnow()
        db.commit()
        return BuyerPrincipal(
            customer_id=invite.customer_id,
            invite_id=invite.id,
            owner_user_id=invite.created_by_user_id,
        )
    if staff is None:
        raise HTTPException(status_code=401, detail="Sign in or open your buyer portal link")
    return BuyerPrincipal(customer_id=None, staff=staff, owner_user_id=staff.id)


def buyer_record(
    principal: BuyerPrincipal = Depends(buyer_principal),
    session_id: Optional[str] = Header(default=None, alias=SESSION_HEADER),
    rt: CommerceRuntime = Depends(runtime),
):
    if not session_id:
        raise HTTPException(status_code=401, detail="Start a buyer session first")
    try:
        record = rt.buyer_sessions.require(session_id)
    except UnknownSession as error:
        raise HTTPException(status_code=401, detail="Unknown session") from error
    owns = (
        principal.invite_id is not None and record.invite_id == principal.invite_id
    ) or (principal.staff is not None and record.user_id == principal.staff.id and record.invite_id is None)
    if not owns:
        raise HTTPException(status_code=401, detail="Unknown session")
    yield record
    try:
        rt.buyer_sessions.save(record)
    except SessionConflict as error:
        raise HTTPException(status_code=409, detail="The session changed; retry") from error


def operations_record(
    user: User = Depends(get_current_active_user),
    session_id: Optional[str] = Header(default=None, alias=SESSION_HEADER),
    rt: CommerceRuntime = Depends(runtime),
):
    if not session_id:
        raise HTTPException(status_code=401, detail="Start an operations session first")
    try:
        record = rt.merchant_sessions.require(session_id)
    except UnknownSession as error:
        raise HTTPException(status_code=401, detail="Unknown session") from error
    if record.user_id != user.id:
        raise HTTPException(status_code=401, detail="Unknown session")
    yield record
    try:
        rt.merchant_sessions.save(record)
    except SessionConflict as error:
        raise HTTPException(status_code=409, detail="The session changed; retry") from error


# ---------------------------------------------------------------------------
# Turn streaming
# ---------------------------------------------------------------------------


class ChatRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    message: str = Field(min_length=1, max_length=4000)
    page: Optional[PageContext] = None
    locale: Optional[Locale] = None


def append_user_turn(record: SessionRecord, message: str, label: str) -> None:
    if not record.pending_app_events:
        record.messages.append({"role": "user", "content": message})
        return
    note = f"[{label} since your last reply: " + " ".join(record.pending_app_events) + "]"
    record.pending_app_events.clear()
    record.messages.append(
        {"role": "user", "content": [{"type": "text", "text": note}, {"type": "text", "text": message}]}
    )


def stream_turn(rt: CommerceRuntime, role: str, record: SessionRecord, context: Any, locale: Optional[str]) -> StreamingResponse:
    agent = rt.shopping_agent if role == "buyer" else rt.merchant_agent
    store = rt.buyer_sessions if role == "buyer" else rt.merchant_sessions
    log = rt.buyer_log if role == "buyer" else rt.merchant_log
    recorder = log.turn(record.session_id, locale, model=agent.config.model, provider=rt.choice.provider)
    language = locale if locale in ("en", "zh") else "en"

    def error(kind: str, status: object = "") -> str:
        recorder.failed(kind)
        return to_sse(AgentEvent.error(ERROR_TEXT[kind][language].format(status=status)))

    async def events() -> AsyncIterator[str]:
        try:
            async for event in agent.stream_turn(record.messages, context, record.state):
                yield to_sse(recorder.observe(event))
        except (anthropic.AuthenticationError, ModelAuthenticationError) as failure:
            missing = isinstance(failure, ModelAuthenticationError) and failure.status is None
            yield error("no_key" if missing else "auth_failed")
        except ModelProviderError as failure:
            logger.exception("commerce turn failed: model provider")
            yield error("provider_error", failure.status or "")
        except Exception:
            logger.exception("commerce turn failed")
            yield error("generic")
        else:
            spawn(agent.update_memory(record.messages, context))
        finally:
            recorder.write()

    def write_back() -> None:
        try:
            store.save(record)
        except SessionConflict:
            logger.warning("commerce session write raced a turn; the turn wins")
            store.save(record, force=True)

    return StreamingResponse(
        events(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=BackgroundTask(write_back),
    )


def buyer_context(record: SessionRecord, page: Optional[PageContext] = None, locale: Optional[str] = None) -> ShoppingSessionContext:
    return ShoppingSessionContext(
        session_id=record.session_id,
        user_id=record.subject_id,
        page=page or PageContext(),
        now=now_utc(),
        reply_language=REPLY_LANGUAGES.get(locale or ""),
    )


def operations_context(record: SessionRecord, operator: str, locale: Optional[str] = None) -> MerchantSessionContext:
    return MerchantSessionContext(
        session_id=record.session_id,
        merchant_id=MERCHANT_ID,
        operator=operator,
        now=now_utc(),
        reply_language=REPLY_LANGUAGES.get(locale or ""),
    )


class FeedbackRequest(BaseModel):
    turn_id: str = Field(min_length=1, max_length=40)
    helpful: bool


class HandoffRequest(BaseModel):
    turn_id: Optional[str] = Field(default=None, max_length=40)
    reason: RequestedHandoffReason = "user_requested"


def _feedback(rt: CommerceRuntime, role: str, request: FeedbackRequest, record: SessionRecord) -> Dict[str, Any]:
    log = rt.buyer_log if role == "buyer" else rt.merchant_log
    if not log.owns(request.turn_id, record.session_id):
        raise HTTPException(status_code=404, detail="No such turn in this session")
    log.feedback(record.session_id, request.turn_id, request.helpful)
    return {"ok": True}


def _handoff(rt: CommerceRuntime, role: str, request: HandoffRequest, record: SessionRecord) -> Dict[str, Any]:
    log = rt.buyer_log if role == "buyer" else rt.merchant_log
    if request.turn_id is not None and not log.owns(request.turn_id, record.session_id):
        raise HTTPException(status_code=404, detail="No such turn in this session")
    reason = log.handoff_reason(record.session_id, request.turn_id, request.reason)
    asked = handoff_request(record.messages, (STAGING_FOLLOWTHROUGH_REMINDER,))
    ticket, brief = log.handoff(record.session_id, request.turn_id, reason, asked)
    record.pending_app_events.append(HANDOFF_NOTES[role].format(ticket=ticket))
    return {"ok": True, "ticket": ticket, "brief": brief}


async def _memory(rt: CommerceRuntime, subject_id: str) -> Dict[str, Any]:
    facts = await rt.memory_store.get_facts(subject_id)
    return {"facts": [fact.model_dump(mode="json") for fact in facts]}


# ---------------------------------------------------------------------------
# Status and metrics
# ---------------------------------------------------------------------------


@router.get("/status")
async def commerce_status(
    _: User = Depends(get_current_active_user),
    rt: CommerceRuntime = Depends(runtime),
):
    return rt.status()


@router.get("/metrics")
async def commerce_metrics(
    days: int = Query(default=30, ge=1, le=365),
    _: User = Depends(get_current_active_user),
    rt: CommerceRuntime = Depends(runtime),
):
    return metrics_report(rt.scope, days=days)


@router.get("/handoffs")
async def list_handoffs(
    include_resolved: bool = False,
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    query = db.query(CommerceOperationEvent).filter(CommerceOperationEvent.kind == "handoff")
    if not include_resolved:
        query = query.filter(CommerceOperationEvent.resolved_at.is_(None))
    rows = query.order_by(CommerceOperationEvent.id.desc()).limit(200).all()
    return [
        {
            "ticket": row.ticket,
            "role": row.role,
            "created_at": row.created_at,
            "resolved_at": row.resolved_at,
            "brief": {key: row.record_json.get(key) for key in ("request", "tried", "evidence_versions", "reason")},
        }
        for row in rows
    ]


@router.post("/handoffs/{ticket}/resolve")
async def resolve_handoff(
    ticket: str,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    row = (
        db.query(CommerceOperationEvent)
        .filter(CommerceOperationEvent.kind == "handoff", CommerceOperationEvent.ticket == ticket)
        .one_or_none()
    )
    if row is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    row.resolved_at = utcnow()
    row.resolved_by_user_id = user.id
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Buyer portal invites
# ---------------------------------------------------------------------------


class InviteCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: int = Field(gt=0)
    days: Optional[int] = Field(default=None, ge=1, le=365)


@router.post("/buyer/invites", status_code=201)
async def create_invite(
    command: InviteCreate,
    user: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    customer = db.get(Customer, command.customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    if (customer.custom_fields or {}).get("contact_suppressed"):
        raise HTTPException(status_code=409, detail="Contact is suppressed")
    token = secrets.token_urlsafe(32)
    invite = BuyerPortalInvite(
        customer_id=customer.id,
        created_by_user_id=user.id,
        token_hash=_hash(token),
        expires_at=utcnow() + timedelta(days=command.days or settings.COMMERCE_BUYER_INVITE_DAYS),
    )
    db.add(invite)
    db.commit()
    db.refresh(invite)
    return {
        "id": str(invite.id),
        "token": token,
        "portal_path": f"/portal?token={token}",
        "expires_at": invite.expires_at,
    }


@router.get("/buyer/invites")
async def list_invites(
    customer_id: int = Query(gt=0),
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    rows = (
        db.query(BuyerPortalInvite)
        .filter(BuyerPortalInvite.customer_id == customer_id)
        .order_by(BuyerPortalInvite.created_at.desc())
        .all()
    )
    return [
        {
            "id": str(row.id),
            "expires_at": row.expires_at,
            "revoked_at": row.revoked_at,
            "last_used_at": row.last_used_at,
            "created_at": row.created_at,
        }
        for row in rows
    ]


@router.post("/buyer/invites/{invite_id}/revoke")
async def revoke_invite(
    invite_id: UUID,
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    invite = db.get(BuyerPortalInvite, invite_id)
    if invite is None:
        raise HTTPException(status_code=404, detail="Invite not found")
    invite.revoked_at = invite.revoked_at or utcnow()
    db.commit()
    return {"ok": True}


# ---------------------------------------------------------------------------
# Buyer assistant
# ---------------------------------------------------------------------------


class BuyerSessionStart(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: Optional[int] = Field(default=None, gt=0)


@router.post("/buyer/session", status_code=201)
async def start_buyer_session(
    command: Optional[BuyerSessionStart] = None,
    principal: BuyerPrincipal = Depends(buyer_principal),
    rt: CommerceRuntime = Depends(runtime),
    db: Session = Depends(get_db),
):
    customer_id = principal.customer_id or (command.customer_id if command else None)
    if customer_id is None:
        raise HTTPException(status_code=422, detail="customer_id is required when staff open a buyer session")
    customer = db.get(Customer, customer_id)
    if customer is None:
        raise HTTPException(status_code=404, detail="Customer not found")
    record = rt.buyer_sessions.start(
        subject_id=customer_subject(customer.id),
        user_id=principal.staff.id if principal.staff is not None else None,
        customer_id=customer.id,
        invite_id=principal.invite_id,
    )
    return {
        "session_id": record.session_id,
        "customer_id": customer.id,
        "customer_name": customer.company_name or customer.username,
        "mode": "portal" if principal.invite_id else "assisted",
        "model_configured": rt.choice.configured,
    }


@router.post("/buyer/chat")
async def buyer_chat(
    request: ChatRequest,
    record: SessionRecord = Depends(buyer_record),
    rt: CommerceRuntime = Depends(runtime),
):
    append_user_turn(record, request.message, "Portal events")
    return stream_turn(rt, "buyer", record, buyer_context(record, request.page, request.locale), request.locale)


@router.get("/buyer/products")
async def buyer_products(
    query: str = Query(default="", max_length=200),
    category: Optional[str] = Query(default=None, max_length=100),
    limit: int = Query(default=24, ge=1, le=50),
    record: SessionRecord = Depends(buyer_record),
    rt: CommerceRuntime = Depends(runtime),
):
    products = await rt.storefront.search_products(
        buyer_context(record), query, SearchFilters(category=category) if category else None, limit
    )
    record.state.remember_products(products)
    return {"products": [product.model_dump(mode="json") for product in products]}


@router.get("/buyer/products/{product_id}")
async def buyer_product(
    product_id: str,
    record: SessionRecord = Depends(buyer_record),
    rt: CommerceRuntime = Depends(runtime),
):
    details = await rt.storefront.get_product_details(buyer_context(record), product_id)
    if details is None:
        raise HTTPException(status_code=404, detail="Product not found")
    record.state.remember_products([details, *details.variants])
    return details.model_dump(mode="json")


@router.get("/buyer/cart")
async def buyer_cart(
    record: SessionRecord = Depends(buyer_record),
    rt: CommerceRuntime = Depends(runtime),
):
    return cart_payload(await rt.storefront.get_cart(buyer_context(record)))


class CartAddRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product_id: str = Field(min_length=1, max_length=80)
    quantity: int = Field(default=1, ge=1, le=1_000_000)


@router.post("/buyer/cart/add")
async def buyer_cart_add(
    request: CartAddRequest,
    record: SessionRecord = Depends(buyer_record),
    rt: CommerceRuntime = Depends(runtime),
):
    agent = rt.shopping_agent
    executor = agent.executor_class(
        backend=rt.storefront,
        config=agent.config,
        skills=agent.skills,
        session=buyer_context(record),
        state=record.state,
        memory=agent.memory,
    )
    execution = await executor.execute("add_to_cart", {"product_id": request.product_id, "quantity": request.quantity})
    if execution.blocked or execution.is_error:
        raise HTTPException(status_code=400, detail=execution.result_text.split(". ")[0] + ".")
    product = record.state.seen_products.get(request.product_id)
    title = STOREFRONT_FENCE.sanitize_text(product.title, max_chars=120) if product else request.product_id
    record.pending_app_events.append(
        f"Buyer added {title} ({request.product_id}) to the RFQ basket, quantity {request.quantity}."
    )
    return cart_payload(await rt.storefront.get_cart(buyer_context(record)))


class RfqSubmit(BaseModel):
    model_config = ConfigDict(extra="forbid")

    note: Optional[str] = Field(default=None, max_length=1000)
    destination: Optional[str] = Field(default=None, max_length=100)


@router.post("/buyer/rfq", status_code=201)
async def buyer_submit_rfq(
    command: RfqSubmit,
    record: SessionRecord = Depends(buyer_record),
    principal: BuyerPrincipal = Depends(buyer_principal),
    db: Session = Depends(get_db),
):
    owner = db.get(User, principal.owner_user_id)
    try:
        result = submit_rfq(
            db,
            customer_id=record.customer_id,
            owner=owner,
            note=command.note,
            destination=command.destination,
        )
    except (FulfillmentConflict, FulfillmentNotFound) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    record.pending_app_events.append(
        f"Buyer submitted the RFQ basket; quotation request {result.quote_number} is with the sales team."
    )
    return {
        "opportunity_id": result.opportunity_id,
        "quotation_id": result.quotation_id,
        "quote_number": result.quote_number,
        "below_moq": result.below_moq,
    }


@router.get("/buyer/orders")
async def buyer_orders(
    record: SessionRecord = Depends(buyer_record),
    rt: CommerceRuntime = Depends(runtime),
):
    orders = await rt.storefront.get_orders(buyer_context(record), limit=20)
    return {"orders": [order.model_dump(mode="json") for order in orders]}


@router.get("/buyer/memory")
async def buyer_memory(
    record: SessionRecord = Depends(buyer_record),
    rt: CommerceRuntime = Depends(runtime),
):
    return await _memory(rt, record.subject_id)


@router.delete("/buyer/memory/{key}")
async def buyer_forget(
    key: str,
    record: SessionRecord = Depends(buyer_record),
    rt: CommerceRuntime = Depends(runtime),
):
    if not await rt.memory_store.delete_fact(record.subject_id, key):
        raise HTTPException(status_code=404, detail="No such fact")
    return {"ok": True}


@router.delete("/buyer/memory")
async def buyer_purge_memory(
    record: SessionRecord = Depends(buyer_record),
    rt: CommerceRuntime = Depends(runtime),
):
    await rt.memory_store.clear(record.subject_id)
    return {"ok": True}


@router.post("/buyer/feedback")
async def buyer_feedback(
    request: FeedbackRequest,
    record: SessionRecord = Depends(buyer_record),
    rt: CommerceRuntime = Depends(runtime),
):
    return _feedback(rt, "buyer", request, record)


@router.post("/buyer/handoff")
async def buyer_handoff(
    request: HandoffRequest,
    record: SessionRecord = Depends(buyer_record),
    rt: CommerceRuntime = Depends(runtime),
):
    return _handoff(rt, "buyer", request, record)


@router.post("/buyer/reset")
async def buyer_reset(
    record: SessionRecord = Depends(buyer_record),
    rt: CommerceRuntime = Depends(runtime),
):
    rt.buyer_sessions.end(record)
    fresh = rt.buyer_sessions.start(
        subject_id=record.subject_id,
        user_id=record.user_id,
        customer_id=record.customer_id,
        invite_id=record.invite_id,
    )
    return {"ok": True, "session_id": fresh.session_id}


# ---------------------------------------------------------------------------
# Operations assistant
# ---------------------------------------------------------------------------


def _dump(model: Any) -> Dict[str, Any]:
    return model.model_dump(mode="json", exclude_none=True)


@router.post("/operations/session", status_code=201)
async def start_operations_session(
    user: User = Depends(get_current_active_user),
    rt: CommerceRuntime = Depends(runtime),
):
    record = rt.merchant_sessions.start(subject_id=f"operator:{user.id}", user_id=user.id)
    return {
        "session_id": record.session_id,
        "operator": user.username,
        "can_approve": can_approve(user),
        "model_configured": rt.choice.configured,
    }


@router.post("/operations/chat")
async def operations_chat(
    request: ChatRequest,
    record: SessionRecord = Depends(operations_record),
    user: User = Depends(get_current_active_user),
    rt: CommerceRuntime = Depends(runtime),
):
    append_user_turn(record, request.message, "Console events")
    return stream_turn(rt, "merchant", record, operations_context(record, user.username, request.locale), request.locale)


@router.get("/operations/overview")
async def operations_overview(
    record: SessionRecord = Depends(operations_record),
    user: User = Depends(get_current_active_user),
    rt: CommerceRuntime = Depends(runtime),
):
    context = operations_context(record, user.username)
    backend = rt.merchant
    snapshot = await backend.get_business_snapshot(context)
    alerts = await backend.get_inventory_alerts(context)
    issues = await backend.get_order_issues(context)
    return {
        "snapshot": _dump(snapshot),
        "needs_attention": {
            "inventory": [_dump(alert) for alert in alerts[:8]],
            "order_issues": [_dump(issue) for issue in issues[:8]],
            "pending_changes": [_dump(change) for change in backend.ledger.pending()[:8]],
        },
        "recent_changes": [_dump(change) for change in backend.ledger.resolved(10)],
    }


@router.get("/operations/changes")
async def operations_changes(
    record: SessionRecord = Depends(operations_record),
    rt: CommerceRuntime = Depends(runtime),
):
    pending = rt.merchant.ledger.pending()
    for change in pending:
        record.state.remember_change(change)
    return {
        "pending": [_dump(change) for change in pending],
        "resolved": [_dump(change) for change in rt.merchant.ledger.resolved(30)],
    }


async def change_action(
    rt: CommerceRuntime, change_id: str, action: str, record: SessionRecord, user: User
) -> Dict[str, Any]:
    """The console's own approval or dismissal. The id is marked approved before the
    executor runs and unmarked after, whatever happens, so no later chat turn can spend
    the mark; the executor still runs every staging gate and guardrail."""
    if action == "apply_change":
        record.state.approved_change_ids.add(change_id)
    else:
        record.state.host_action_change_ids.add(change_id)
    agent = rt.merchant_agent
    executor = MerchantToolExecutor(
        backend=rt.merchant,
        config=agent.config,
        skills=agent.skills,
        session=operations_context(record, user.username),
        state=record.state,
        memory=agent.memory,
    )
    standing = False
    try:
        execution = await executor.dispatch(action, {"change_id": change_id})
    except ChangeNotApplicable as refused:
        standing = True
        execution = executor.domain_error(refused)
    except Exception:
        logger.warning("console %s of %s failed", action, change_id, exc_info=True)
        raise HTTPException(status_code=400, detail=executor.unavailable_text.format(name=action)) from None
    finally:
        record.state.host_action_change_ids.discard(change_id)
        record.state.approved_change_ids.discard(change_id)
    if execution.is_error and not standing:
        raise HTTPException(status_code=400, detail=execution.result_text)
    if standing or execution.blocked is not None:
        current = rt.merchant.ledger.get(change_id)
        expired = current is not None and current.status is ChangeStatus.EXPIRED
        if expired:
            record.state.remember_change(current)
        return {"ok": False, "change": _dump(current) if expired else None, "reason": execution.result_text}
    verb = "approved and applied" if action == "apply_change" else "dismissed"
    rt.merchant_log.action(record.session_id, action, [change_id])
    record.pending_app_events.append(f"Operator {verb} change {change_id} from the console.")
    change = next((event.data.get("change") for event in execution.events if event.type == "change_update"), None)
    return {"ok": True, "change": change}


@router.post("/operations/changes/{change_id}/apply")
async def operations_apply(
    change_id: str,
    record: SessionRecord = Depends(operations_record),
    user: User = Depends(get_current_active_user),
    rt: CommerceRuntime = Depends(runtime),
):
    if not can_approve(user):
        raise HTTPException(status_code=403, detail="Only operators or admins approve staged changes")
    return await change_action(rt, change_id, "apply_change", record, user)


@router.post("/operations/changes/{change_id}/discard")
async def operations_discard(
    change_id: str,
    record: SessionRecord = Depends(operations_record),
    user: User = Depends(get_current_active_user),
    rt: CommerceRuntime = Depends(runtime),
):
    return await change_action(rt, change_id, "discard_change", record, user)


@router.get("/operations/memory")
async def operations_memory(
    record: SessionRecord = Depends(operations_record),
    rt: CommerceRuntime = Depends(runtime),
):
    return await _memory(rt, record.subject_id)


@router.delete("/operations/memory")
async def operations_purge_memory(
    record: SessionRecord = Depends(operations_record),
    rt: CommerceRuntime = Depends(runtime),
):
    await rt.memory_store.clear(record.subject_id)
    return {"ok": True}


@router.post("/operations/feedback")
async def operations_feedback(
    request: FeedbackRequest,
    record: SessionRecord = Depends(operations_record),
    rt: CommerceRuntime = Depends(runtime),
):
    return _feedback(rt, "merchant", request, record)


@router.post("/operations/handoff")
async def operations_handoff(
    request: HandoffRequest,
    record: SessionRecord = Depends(operations_record),
    rt: CommerceRuntime = Depends(runtime),
):
    return _handoff(rt, "merchant", request, record)


@router.post("/operations/reset")
async def operations_reset(
    record: SessionRecord = Depends(operations_record),
    rt: CommerceRuntime = Depends(runtime),
):
    rt.merchant_sessions.end(record)
    fresh = rt.merchant_sessions.start(subject_id=record.subject_id, user_id=record.user_id)
    return {"ok": True, "session_id": fresh.session_id}


# ---------------------------------------------------------------------------
# Catalog administration
# ---------------------------------------------------------------------------


class ProductUpsert(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(pattern=r"^[A-Z0-9][A-Z0-9-]{2,79}$")
    parent_id: Optional[str] = Field(default=None, max_length=80)
    title: str = Field(min_length=2, max_length=255)
    brand: Optional[str] = Field(default=None, max_length=100)
    category: Optional[str] = Field(default=None, max_length=100)
    status: Literal["active", "paused", "draft"] = "active"
    short_description: Optional[str] = Field(default=None, max_length=500)
    long_description: Optional[str] = Field(default=None, max_length=10000)
    attributes: Dict[str, str] = Field(default_factory=dict)
    specs: Dict[str, str] = Field(default_factory=dict)
    options: Dict[str, List[str]] = Field(default_factory=dict)
    option_values: Dict[str, str] = Field(default_factory=dict)
    labels: List[str] = Field(default_factory=list, max_length=10)
    price: Decimal = Field(ge=0, max_digits=14, decimal_places=4)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    unit_cost: Optional[Decimal] = Field(default=None, ge=0, max_digits=14, decimal_places=4)
    min_price: Optional[Decimal] = Field(default=None, ge=0, max_digits=14, decimal_places=4)
    moq: int = Field(default=1, ge=1)
    lead_time_days: Optional[int] = Field(default=None, ge=1, le=365)
    stock: int = Field(default=0, ge=0)
    reorder_point: int = Field(default=0, ge=0)
    image_url: Optional[str] = Field(default=None, max_length=1000)


def _product_payload(row: CatalogProduct) -> Dict[str, Any]:
    listing = to_listing(row)
    return {
        **listing.model_dump(mode="json"),
        "parent_id": row.parent_id,
        "brand": row.brand,
        "unit_cost": float(row.unit_cost) if row.unit_cost is not None else None,
        "min_price": float(row.min_price) if row.min_price is not None else None,
        "moq": row.moq,
        "lead_time_days": row.lead_time_days,
        "reorder_point": row.reorder_point,
        "sales_last_30d": row.sales_last_30d,
        "variants": [to_listing(variant).model_dump(mode="json") for variant in row.variants],
    }


@router.get("/catalog/products")
async def catalog_products(
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    return [_product_payload(row) for row in families(db, ("active", "paused", "draft"))]


@router.put("/catalog/products/{product_id}")
async def upsert_catalog_product(
    product_id: str,
    command: ProductUpsert,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    if command.id != product_id:
        raise HTTPException(status_code=422, detail="Product id in path and body differ")
    if command.parent_id and db.get(CatalogProduct, command.parent_id) is None:
        raise HTTPException(status_code=404, detail="Parent product not found")
    row = db.get(CatalogProduct, product_id)
    if row is None:
        row = CatalogProduct(id=product_id)
        db.add(row)
    else:
        row.version += 1
    row.parent_id = command.parent_id
    row.title = command.title.strip()
    row.brand = command.brand
    row.category = command.category
    row.status = command.status
    row.short_description = command.short_description
    row.long_description = command.long_description
    row.attributes_json = command.attributes
    row.specs_json = command.specs
    row.options_json = command.options
    row.option_values_json = command.option_values
    row.labels_json = command.labels
    row.price = command.price
    row.currency = command.currency
    row.unit_cost = command.unit_cost
    row.min_price = command.min_price
    row.moq = command.moq
    row.lead_time_days = command.lead_time_days
    row.stock = command.stock
    row.reorder_point = command.reorder_point
    row.image_url = command.image_url
    db.commit()
    db.refresh(row)
    return _product_payload(row)


class TermCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(pattern=r"^[a-z0-9][a-z0-9/_-]{2,79}$")
    version: str = Field(min_length=1, max_length=20)
    title: str = Field(min_length=2, max_length=255)
    category: Optional[str] = Field(default=None, max_length=50)
    content: str = Field(min_length=10, max_length=10000)
    effective_at: datetime
    expires_at: Optional[datetime] = None


@router.get("/catalog/terms")
async def catalog_terms(
    _: User = Depends(get_current_active_user),
    db: Session = Depends(get_db),
):
    rows = db.query(TradeTerm).order_by(TradeTerm.source_id, TradeTerm.effective_at.desc()).all()
    now = utcnow()
    return [
        {
            "id": row.id,
            "source_id": row.source_id,
            "version": row.version,
            "title": row.title,
            "category": row.category,
            "content": row.content,
            "effective_at": row.effective_at,
            "expires_at": row.expires_at,
            "in_force": row.effective_at <= now and (row.expires_at is None or now < row.expires_at),
        }
        for row in rows
    ]


@router.post("/catalog/terms", status_code=201)
async def create_term(
    command: TermCreate,
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    def naive(value: Optional[datetime]) -> Optional[datetime]:
        if value is None or value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)

    if command.expires_at and command.expires_at <= command.effective_at:
        raise HTTPException(status_code=422, detail="expires_at must be after effective_at")
    if db.query(TradeTerm).filter(TradeTerm.source_id == command.source_id, TradeTerm.version == command.version).first():
        raise HTTPException(status_code=409, detail="This version of the source already exists")
    row = TradeTerm(
        id=f"{command.source_id}@{command.version}",
        source_id=command.source_id,
        version=command.version,
        title=command.title,
        category=command.category,
        content=command.content,
        effective_at=naive(command.effective_at),
        expires_at=naive(command.expires_at),
    )
    db.add(row)
    db.commit()
    return {"id": row.id}


@router.get("/catalog/campaigns")
async def catalog_campaigns(
    _: User = Depends(get_current_active_user),
    rt: CommerceRuntime = Depends(runtime),
):
    campaigns = await rt.merchant.get_campaign_performance(
        MerchantSessionContext(session_id="console", merchant_id=MERCHANT_ID, operator="console")
    )
    return [campaign.model_dump(mode="json") for campaign in campaigns]


@router.post("/catalog/seed-demo")
async def seed_demo_catalog(
    _: User = Depends(require_admin),
    db: Session = Depends(get_db),
):
    from app.commerce.seed import seed_demo_catalog as seed

    return seed(db)
