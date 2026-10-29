"""Opportunity-to-delivery pipeline: quotations, orders, production, QC and shipment.

Every lifecycle change is gated by the business evidence it depends on (paid
deposit, completed production, passed final inspection, departed shipment,
settled balance) and recorded in an append-only ``fulfillment_events``
timeline. Callers never set an order status directly without passing those
gates; blocked transitions return the list of unmet requirements.
"""

from datetime import date, datetime, timedelta, timezone
from decimal import ROUND_HALF_UP, Decimal
from typing import Dict, List, Literal, Optional, Sequence, Tuple
from uuid import UUID, uuid4

from pydantic import BaseModel, ConfigDict, Field, HttpUrl, field_validator, model_validator
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.models.database import (
    AgentOutreachDelivery,
    Conversation,
    ConversationStatus,
    Customer,
    FulfillmentEvent,
    Message,
    OrderPayment,
    OrderShipment,
    ProductionTask,
    QualityInspection,
    SalesOpportunity,
    SalesOrder,
    SalesQuotation,
    User,
)


CENT = Decimal("0.01")

OPPORTUNITY_STAGES = ("inquiry", "qualified", "quoting", "negotiation", "won", "lost")
OPEN_OPPORTUNITY_STAGES = ("inquiry", "qualified", "quoting", "negotiation")
OPPORTUNITY_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "inquiry": ("qualified", "lost"),
    "qualified": ("quoting", "lost"),
    "quoting": ("negotiation", "lost"),
    "negotiation": ("quoting", "lost"),
    "lost": ("qualified",),
    "won": (),
}

LIVE_QUOTATION_STATUSES = ("draft", "approval_pending", "approved", "sent")

ORDER_STATUSES = (
    "confirmed",
    "in_production",
    "quality_check",
    "ready_to_ship",
    "shipped",
    "delivered",
    "completed",
    "cancelled",
)
ORDER_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "confirmed": ("in_production", "cancelled"),
    "in_production": ("quality_check", "cancelled"),
    "quality_check": ("ready_to_ship", "in_production", "cancelled"),
    "ready_to_ship": ("shipped", "cancelled"),
    "shipped": ("delivered",),
    "delivered": ("completed",),
    "completed": (),
    "cancelled": (),
}
TASK_EDITABLE_ORDER_STATUSES = ("confirmed", "in_production", "quality_check")
SHIPMENT_ORDER_STATUSES = ("quality_check", "ready_to_ship", "shipped")
CLOSED_ORDER_STATUSES = ("completed", "cancelled")

TASK_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "planned": ("in_progress", "cancelled"),
    "in_progress": ("completed", "cancelled"),
    "completed": (),
    "cancelled": (),
}
SHIPMENT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "booked": ("departed",),
    "departed": ("arrived", "delivered"),
    "arrived": ("delivered",),
    "delivered": (),
}

BUYING_INTENTS = (
    "price_inquiry",
    "product_inquiry",
    "sample_request",
    "moq_inquiry",
    "collaboration_inquiry",
    "payment_inquiry",
    "lead_time_inquiry",
    "shipping_inquiry",
)

FulfillmentMode = Literal["in_house", "outsourced", "mixed"]
Incoterm = Literal["EXW", "FCA", "FOB", "CFR", "CIF", "CPT", "CIP", "DAP", "DPU", "DDP"]


# ---------------------------------------------------------------------------
# Contracts
# ---------------------------------------------------------------------------


class OpportunityRequirements(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: Optional[str] = Field(default=None, max_length=255)
    quantity: Optional[Decimal] = Field(default=None, gt=0)
    unit: Optional[str] = Field(default=None, max_length=20)
    target_price: Optional[Decimal] = Field(default=None, ge=0)
    destination_country: Optional[str] = Field(default=None, max_length=100)
    incoterm: Optional[Incoterm] = None
    required_by: Optional[date] = None
    certifications: List[str] = Field(default_factory=list, max_length=20)
    notes: Optional[str] = Field(default=None, max_length=2000)


class OpportunityCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    customer_id: int = Field(gt=0)
    title: str = Field(min_length=3, max_length=255)
    inquiry_summary: Optional[str] = Field(default=None, max_length=5000)
    requirements: OpportunityRequirements = Field(default_factory=OpportunityRequirements)
    estimated_value: Optional[Decimal] = Field(default=None, ge=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    expected_close_date: Optional[date] = None


class OpportunityFromConversation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(default=None, min_length=3, max_length=255)
    requirements: OpportunityRequirements = Field(default_factory=OpportunityRequirements)
    estimated_value: Optional[Decimal] = Field(default=None, ge=0)
    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")


class OpportunityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: Optional[str] = Field(default=None, min_length=3, max_length=255)
    inquiry_summary: Optional[str] = Field(default=None, max_length=5000)
    requirements: Optional[OpportunityRequirements] = None
    estimated_value: Optional[Decimal] = Field(default=None, ge=0)
    currency: Optional[str] = Field(default=None, pattern=r"^[A-Z]{3}$")
    expected_close_date: Optional[date] = None


class OpportunityTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Literal["qualified", "quoting", "negotiation", "lost"]
    reason: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def lost_requires_reason(self) -> "OpportunityTransition":
        if self.stage == "lost" and not (self.reason or "").strip():
            raise ValueError("A reason is required when marking an opportunity lost")
        return self


class QuotationLineItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    product: str = Field(min_length=1, max_length=255)
    description: Optional[str] = Field(default=None, max_length=1000)
    hs_code: Optional[str] = Field(default=None, pattern=r"^[0-9.]{4,14}$")
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unit: str = Field(default="pcs", min_length=1, max_length=20)
    unit_price: Decimal = Field(ge=0, max_digits=14, decimal_places=4)
    unit_cost: Optional[Decimal] = Field(default=None, ge=0, max_digits=14, decimal_places=4)


class QuotationCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    currency: str = Field(default="USD", pattern=r"^[A-Z]{3}$")
    incoterm: Incoterm = "FOB"
    payment_terms: str = Field(default="30% T/T deposit, 70% before shipment", min_length=3, max_length=255)
    deposit_percent: int = Field(default=30, ge=0, le=100)
    lead_time_days: int = Field(default=30, ge=1, le=365)
    valid_days: int = Field(default=15, ge=1, le=180)
    line_items: List[QuotationLineItem] = Field(min_length=1, max_length=100)
    freight_amount: Decimal = Field(default=Decimal("0"), ge=0)
    discount_amount: Decimal = Field(default=Decimal("0"), ge=0)
    notes: Optional[str] = Field(default=None, max_length=5000)


class QuotationReview(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: Literal["approve", "reject"]
    reason: str = Field(min_length=3, max_length=1000)


class QuotationSend(BaseModel):
    model_config = ConfigDict(extra="forbid")

    channel: Literal["email", "whatsapp", "other"] = "email"


class QuotationDecline(BaseModel):
    model_config = ConfigDict(extra="forbid")

    reason: str = Field(min_length=3, max_length=1000)


class QuotationAccept(BaseModel):
    model_config = ConfigDict(extra="forbid")

    fulfillment_mode: FulfillmentMode = "in_house"
    customer_po_number: Optional[str] = Field(default=None, max_length=100)
    required_ship_date: Optional[date] = None
    shipping_address: Optional[str] = Field(default=None, max_length=2000)
    balance_before_shipment: bool = True


class OrderTransition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal[
        "in_production",
        "quality_check",
        "ready_to_ship",
        "shipped",
        "delivered",
        "completed",
        "cancelled",
    ]
    reason: Optional[str] = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def cancel_requires_reason(self) -> "OrderTransition":
        if self.status == "cancelled" and not (self.reason or "").strip():
            raise ValueError("A reason is required when cancelling an order")
        return self


class ProductionTaskCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    kind: Literal["work_order", "purchase_order"]
    description: str = Field(min_length=3, max_length=500)
    quantity: Decimal = Field(gt=0, max_digits=14, decimal_places=3)
    unit: str = Field(default="pcs", min_length=1, max_length=20)
    supplier_name: Optional[str] = Field(default=None, max_length=255)
    production_line: Optional[str] = Field(default=None, max_length=100)
    planned_start: Optional[date] = None
    planned_finish: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=2000)

    @model_validator(mode="after")
    def validate_shape(self) -> "ProductionTaskCreate":
        if self.kind == "purchase_order" and not (self.supplier_name or "").strip():
            raise ValueError("A supplier is required for an outsourced purchase order")
        if (
            self.planned_start
            and self.planned_finish
            and self.planned_finish < self.planned_start
        ):
            raise ValueError("planned_finish must not be earlier than planned_start")
        return self


class ProductionTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Optional[Literal["in_progress", "completed", "cancelled"]] = None
    progress_percent: Optional[int] = Field(default=None, ge=0, le=100)
    planned_finish: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


class InspectionDefect(BaseModel):
    model_config = ConfigDict(extra="forbid")

    description: str = Field(min_length=1, max_length=500)
    severity: Literal["critical", "major", "minor"]
    count: int = Field(default=1, ge=1)


class InspectionCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    stage: Literal["pre_production", "inline", "pre_shipment"]
    result: Literal["passed", "failed", "conditional"]
    inspector: str = Field(min_length=2, max_length=255)
    production_task_id: Optional[UUID] = None
    sample_size: Optional[int] = Field(default=None, ge=1)
    defects: List[InspectionDefect] = Field(default_factory=list, max_length=100)
    report_url: Optional[HttpUrl] = None
    notes: Optional[str] = Field(default=None, max_length=2000)
    inspected_at: Optional[datetime] = None

    @field_validator("report_url")
    @classmethod
    def reject_url_credentials(cls, value: Optional[HttpUrl]) -> Optional[HttpUrl]:
        if value is not None and (value.username or value.password):
            raise ValueError("report URL must not contain credentials")
        return value

    @model_validator(mode="after")
    def passed_has_no_critical_defects(self) -> "InspectionCreate":
        if self.result == "passed" and any(d.severity == "critical" for d in self.defects):
            raise ValueError("An inspection with critical defects cannot pass")
        return self


class ShipmentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    transport_mode: Literal["sea", "air", "rail", "road", "express"]
    carrier: str = Field(min_length=2, max_length=255)
    tracking_number: Optional[str] = Field(default=None, max_length=255)
    bill_of_lading: Optional[str] = Field(default=None, max_length=255)
    container_number: Optional[str] = Field(default=None, max_length=100)
    port_of_loading: Optional[str] = Field(default=None, max_length=255)
    port_of_discharge: Optional[str] = Field(default=None, max_length=255)
    etd: Optional[date] = None
    eta: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


class ShipmentUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Optional[Literal["departed", "arrived", "delivered"]] = None
    tracking_number: Optional[str] = Field(default=None, max_length=255)
    bill_of_lading: Optional[str] = Field(default=None, max_length=255)
    container_number: Optional[str] = Field(default=None, max_length=100)
    eta: Optional[date] = None
    notes: Optional[str] = Field(default=None, max_length=2000)


class PaymentCreate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    idempotency_key: str = Field(min_length=8, max_length=255)
    kind: Literal["deposit", "balance", "other"]
    amount: Decimal = Field(gt=0, max_digits=14, decimal_places=2)
    currency: str = Field(pattern=r"^[A-Z]{3}$")
    method: Literal["tt", "lc", "paypal", "card", "cash", "other"] = "tt"
    reference: Optional[str] = Field(default=None, max_length=255)
    received_at: Optional[datetime] = None


class OpportunityResponse(BaseModel):
    id: UUID
    customer_id: int
    customer_name: str
    conversation_id: Optional[UUID]
    title: str
    source: str
    stage: str
    allowed_stages: List[str]
    inquiry_summary: Optional[str]
    requirements: Dict[str, object]
    estimated_value: Optional[Decimal]
    currency: str
    expected_close_date: Optional[date]
    lost_reason: Optional[str]
    won_at: Optional[datetime]
    order_id: Optional[UUID]
    quotation_count: int
    created_at: datetime
    updated_at: datetime


class QuotationResponse(BaseModel):
    id: UUID
    opportunity_id: UUID
    quote_number: str
    revision: int
    status: str
    currency: str
    incoterm: str
    payment_terms: str
    deposit_percent: int
    lead_time_days: int
    valid_until: date
    expired: bool
    line_items: List[Dict[str, object]]
    subtotal: Decimal
    freight_amount: Decimal
    discount_amount: Decimal
    total: Decimal
    margin_percent: Optional[Decimal]
    requires_escalated_approval: bool
    notes: Optional[str]
    review_reason: Optional[str]
    reviewed_by_user_id: Optional[int]
    reviewed_at: Optional[datetime]
    sent_at: Optional[datetime]
    sent_channel: Optional[str]
    accepted_at: Optional[datetime]
    created_at: datetime


class ProductionTaskResponse(BaseModel):
    id: UUID
    kind: str
    reference_number: str
    description: str
    supplier_name: Optional[str]
    production_line: Optional[str]
    quantity: Decimal
    unit: str
    status: str
    progress_percent: int
    planned_start: Optional[date]
    planned_finish: Optional[date]
    actual_start: Optional[datetime]
    actual_finish: Optional[datetime]
    overdue: bool
    notes: Optional[str]


class InspectionResponse(BaseModel):
    id: UUID
    production_task_id: Optional[UUID]
    stage: str
    result: str
    inspector: str
    sample_size: Optional[int]
    defects: List[Dict[str, object]]
    report_url: Optional[str]
    notes: Optional[str]
    inspected_at: datetime


class ShipmentResponse(BaseModel):
    id: UUID
    shipment_number: str
    status: str
    transport_mode: str
    carrier: str
    tracking_number: Optional[str]
    bill_of_lading: Optional[str]
    container_number: Optional[str]
    port_of_loading: Optional[str]
    port_of_discharge: Optional[str]
    etd: Optional[date]
    eta: Optional[date]
    departed_at: Optional[datetime]
    delivered_at: Optional[datetime]
    notes: Optional[str]


class PaymentResponse(BaseModel):
    id: UUID
    kind: str
    amount: Decimal
    currency: str
    method: str
    reference: Optional[str]
    received_at: datetime


class TransitionReadiness(BaseModel):
    status: str
    ready: bool
    blockers: List[str]


class OrderSummaryResponse(BaseModel):
    id: UUID
    order_number: str
    customer_id: int
    customer_name: str
    opportunity_id: UUID
    quotation_id: UUID
    status: str
    fulfillment_mode: str
    currency: str
    total: Decimal
    amount_paid: Decimal
    balance_due: Decimal
    required_ship_date: Optional[date]
    ship_date_at_risk: bool
    production_progress_percent: int
    created_at: datetime
    updated_at: datetime


class OrderDetailResponse(OrderSummaryResponse):
    customer_po_number: Optional[str]
    incoterm: str
    payment_terms: str
    line_items: List[Dict[str, object]]
    deposit_required: Decimal
    balance_before_shipment: bool
    shipping_address: Optional[str]
    cancel_reason: Optional[str]
    production_started_at: Optional[datetime]
    shipped_at: Optional[datetime]
    delivered_at: Optional[datetime]
    completed_at: Optional[datetime]
    version: int
    next_transitions: List[TransitionReadiness]
    production_tasks: List[ProductionTaskResponse]
    inspections: List[InspectionResponse]
    shipments: List[ShipmentResponse]
    payments: List[PaymentResponse]


class FulfillmentEventResponse(BaseModel):
    id: UUID
    opportunity_id: UUID
    order_id: Optional[UUID]
    actor_user_id: Optional[int]
    event_type: str
    from_status: Optional[str]
    to_status: Optional[str]
    payload: Dict[str, object]
    created_at: datetime


class PipelineStage(BaseModel):
    key: str
    count: int
    value: Decimal


class PipelineAlert(BaseModel):
    kind: str
    severity: Literal["info", "warning", "critical"]
    message: str
    opportunity_id: Optional[UUID] = None
    order_id: Optional[UUID] = None
    conversation_id: Optional[UUID] = None


class UnconvertedInquiry(BaseModel):
    conversation_id: UUID
    customer_id: int
    customer_name: str
    intent: str
    last_message_at: Optional[datetime]


class PipelineOverview(BaseModel):
    leads: Dict[str, int]
    outreach: Dict[str, int]
    opportunities: List[PipelineStage]
    quotations: Dict[str, int]
    orders: List[PipelineStage]
    win_rate_percent: Optional[Decimal]
    booked_value: Decimal
    collected_value: Decimal
    unconverted_inquiries: List[UnconvertedInquiry]
    alerts: List[PipelineAlert]


# ---------------------------------------------------------------------------
# Errors
# ---------------------------------------------------------------------------


class FulfillmentNotFound(LookupError):
    pass


class FulfillmentConflict(RuntimeError):
    pass


class FulfillmentForbidden(PermissionError):
    pass


class FulfillmentGateBlocked(RuntimeError):
    def __init__(self, status: str, blockers: Sequence[str]) -> None:
        super().__init__(f"Order cannot move to {status}: " + "; ".join(blockers))
        self.status = status
        self.blockers = list(blockers)


# ---------------------------------------------------------------------------
# Service
# ---------------------------------------------------------------------------


class FulfillmentService:
    def __init__(self, db: Session) -> None:
        self._db = db

    # -- opportunities -----------------------------------------------------

    def list_opportunities(
        self,
        *,
        actor: User,
        stage: Optional[str] = None,
        customer_id: Optional[int] = None,
    ) -> List[OpportunityResponse]:
        query = self._scoped(self._db.query(SalesOpportunity), SalesOpportunity, actor)
        if stage:
            query = query.filter(SalesOpportunity.stage == stage)
        if customer_id:
            query = query.filter(SalesOpportunity.customer_id == customer_id)
        rows = query.order_by(SalesOpportunity.updated_at.desc()).limit(500).all()
        return [self._opportunity_response(row) for row in rows]

    def get_opportunity(self, opportunity_id: UUID, *, actor: User) -> OpportunityResponse:
        return self._opportunity_response(self._owned_opportunity(opportunity_id, actor))

    def create_opportunity(
        self,
        command: OpportunityCreate,
        *,
        actor: User,
    ) -> OpportunityResponse:
        customer = self._db.get(Customer, command.customer_id)
        if customer is None:
            raise FulfillmentNotFound("Customer not found")
        row = SalesOpportunity(
            user_id=actor.id,
            customer_id=customer.id,
            title=command.title.strip(),
            source="manual",
            stage="inquiry",
            inquiry_summary=(command.inquiry_summary or "").strip() or None,
            requirements_json=self._requirements_json(command.requirements),
            estimated_value=self._money_or_none(command.estimated_value),
            currency=command.currency,
            expected_close_date=command.expected_close_date,
        )
        self._db.add(row)
        self._db.flush()
        self._mark_customer_engaged(customer)
        self._record(row, None, actor, "opportunity.created", None, "inquiry", {"source": "manual"})
        self._db.commit()
        self._db.refresh(row)
        return self._opportunity_response(row)

    def create_opportunity_from_conversation(
        self,
        conversation_id: UUID,
        command: OpportunityFromConversation,
        *,
        actor: User,
    ) -> Tuple[OpportunityResponse, bool]:
        conversation = self._db.get(Conversation, conversation_id)
        if conversation is None or conversation.customer is None:
            raise FulfillmentNotFound("Conversation not found")
        existing = (
            self._scoped(self._db.query(SalesOpportunity), SalesOpportunity, actor)
            .filter(
                SalesOpportunity.conversation_id == conversation.id,
                SalesOpportunity.stage.in_(OPEN_OPPORTUNITY_STAGES + ("won",)),
            )
            .order_by(SalesOpportunity.created_at.desc())
            .first()
        )
        if existing is not None:
            return self._opportunity_response(existing), False

        customer = conversation.customer
        inbound = (
            self._db.query(Message)
            .filter(Message.conversation_id == conversation.id, Message.role == "user")
            .order_by(Message.sent_at.desc())
            .limit(3)
            .all()
        )
        excerpt = "\n---\n".join(
            (message.content or "").strip() for message in reversed(inbound) if message.content
        )
        summary = (conversation.summary or "").strip() or excerpt
        intent = conversation.current_intent or "inquiry"
        title = (command.title or "").strip() or (
            f"{self._customer_name(customer)} · {intent.replace('_', ' ')}"
        )[:255]
        row = SalesOpportunity(
            user_id=actor.id,
            customer_id=customer.id,
            conversation_id=conversation.id,
            title=title,
            source="conversation",
            stage="inquiry",
            inquiry_summary=summary[:5000] or None,
            requirements_json=self._requirements_json(command.requirements),
            estimated_value=self._money_or_none(command.estimated_value),
            currency=command.currency,
        )
        self._db.add(row)
        self._db.flush()
        self._mark_customer_engaged(customer)
        self._record(
            row,
            None,
            actor,
            "opportunity.created",
            None,
            "inquiry",
            {
                "source": "conversation",
                "conversation_id": str(conversation.id),
                "intent": intent,
                "intent_confidence": float(conversation.intent_confidence or 0.0),
            },
        )
        self._db.commit()
        self._db.refresh(row)
        return self._opportunity_response(row), True

    def update_opportunity(
        self,
        opportunity_id: UUID,
        command: OpportunityUpdate,
        *,
        actor: User,
    ) -> OpportunityResponse:
        row = self._owned_opportunity(opportunity_id, actor)
        if row.stage not in OPEN_OPPORTUNITY_STAGES:
            raise FulfillmentConflict("Closed opportunities cannot be edited")
        fields = command.model_dump(exclude_unset=True)
        if "title" in fields and command.title:
            row.title = command.title.strip()
        if "inquiry_summary" in fields:
            row.inquiry_summary = (command.inquiry_summary or "").strip() or None
        if command.requirements is not None:
            row.requirements_json = self._requirements_json(command.requirements)
        if "estimated_value" in fields:
            row.estimated_value = self._money_or_none(command.estimated_value)
        if command.currency:
            row.currency = command.currency
        if "expected_close_date" in fields:
            row.expected_close_date = command.expected_close_date
        self._record(row, None, actor, "opportunity.updated", row.stage, row.stage, {"fields": sorted(fields)})
        self._db.commit()
        self._db.refresh(row)
        return self._opportunity_response(row)

    def transition_opportunity(
        self,
        opportunity_id: UUID,
        command: OpportunityTransition,
        *,
        actor: User,
    ) -> OpportunityResponse:
        row = self._owned_opportunity(opportunity_id, actor)
        if command.stage not in OPPORTUNITY_TRANSITIONS.get(row.stage, ()):
            raise FulfillmentConflict(
                f"Opportunity cannot move from {row.stage} to {command.stage}"
            )
        if command.stage == "qualified":
            requirements = row.requirements_json or {}
            missing = [key for key in ("product", "quantity") if not requirements.get(key)]
            if missing:
                raise FulfillmentConflict(
                    "Qualification requires captured requirements: " + ", ".join(missing)
                )
        previous = row.stage
        row.stage = command.stage
        if command.stage == "lost":
            row.lost_reason = (command.reason or "").strip()
            row.closed_at = self._now()
            self._supersede_live_quotations(row, actor, reason="opportunity_lost")
        elif previous == "lost":
            row.lost_reason = None
            row.closed_at = None
        self._record(
            row,
            None,
            actor,
            "opportunity.stage_changed",
            previous,
            command.stage,
            {"reason": (command.reason or "").strip() or None},
        )
        self._db.commit()
        self._db.refresh(row)
        return self._opportunity_response(row)

    # -- quotations --------------------------------------------------------

    def list_quotations(self, opportunity_id: UUID, *, actor: User) -> List[QuotationResponse]:
        row = self._owned_opportunity(opportunity_id, actor)
        return [self._quotation_response(quote) for quote in row.quotations]

    def create_quotation(
        self,
        opportunity_id: UUID,
        command: QuotationCreate,
        *,
        actor: User,
    ) -> QuotationResponse:
        opportunity = self._owned_opportunity(opportunity_id, actor)
        if opportunity.stage not in ("qualified", "quoting", "negotiation"):
            raise FulfillmentConflict(
                "Only qualified opportunities can be quoted; qualify the inquiry first"
            )
        line_items, subtotal, total_cost = self._price_lines(command.line_items)
        freight = self._money(command.freight_amount)
        discount = self._money(command.discount_amount)
        if discount > subtotal:
            raise FulfillmentConflict("Discount cannot exceed the quotation subtotal")
        total = subtotal + freight - discount
        if total <= 0:
            raise FulfillmentConflict("Quotation total must be greater than zero")
        margin = None
        if total_cost is not None and subtotal - discount > 0:
            net = subtotal - discount
            margin = ((net - total_cost) / net * 100).quantize(CENT, rounding=ROUND_HALF_UP)

        revision = (
            self._db.query(func.coalesce(func.max(SalesQuotation.revision), 0))
            .filter(SalesQuotation.opportunity_id == opportunity.id)
            .scalar()
            or 0
        ) + 1
        self._supersede_live_quotations(opportunity, actor, reason="new_revision")
        quote = SalesQuotation(
            opportunity_id=opportunity.id,
            user_id=actor.id,
            quote_number=f"QT-{opportunity.id.hex[:8].upper()}-R{revision}",
            revision=revision,
            status="draft",
            currency=command.currency,
            incoterm=command.incoterm,
            payment_terms=command.payment_terms.strip(),
            deposit_percent=command.deposit_percent,
            lead_time_days=command.lead_time_days,
            valid_until=self._today() + timedelta(days=command.valid_days),
            line_items_json=line_items,
            subtotal=subtotal,
            freight_amount=freight,
            discount_amount=discount,
            total=total,
            total_cost=total_cost,
            margin_percent=margin,
            notes=(command.notes or "").strip() or None,
        )
        self._db.add(quote)
        if opportunity.stage == "qualified":
            self._record(opportunity, None, actor, "opportunity.stage_changed", "qualified", "quoting", {})
            opportunity.stage = "quoting"
        opportunity.estimated_value = total
        opportunity.currency = command.currency
        self._db.flush()
        self._record(
            opportunity,
            None,
            actor,
            "quotation.created",
            None,
            "draft",
            {"quotation_id": str(quote.id), "quote_number": quote.quote_number, "total": str(total)},
        )
        self._db.commit()
        self._db.refresh(quote)
        return self._quotation_response(quote)

    def submit_quotation(self, quotation_id: UUID, *, actor: User) -> QuotationResponse:
        quote = self._owned_quotation(quotation_id, actor)
        self._require_quote_status(quote, ("draft",), "submitted for approval")
        self._move_quote(quote, actor, "approval_pending", "quotation.submitted", {})
        self._db.commit()
        self._db.refresh(quote)
        return self._quotation_response(quote)

    def review_quotation(
        self,
        quotation_id: UUID,
        command: QuotationReview,
        *,
        actor: User,
    ) -> QuotationResponse:
        quote = self._owned_quotation(quotation_id, actor)
        self._require_quote_status(quote, ("approval_pending",), "reviewed")
        if command.decision == "approve" and self._requires_escalation(quote):
            if not actor.is_superuser or actor.id == quote.user_id:
                raise FulfillmentForbidden(
                    "This quotation exceeds the approval threshold or is below the minimum "
                    "margin and needs approval from a different administrator"
                )
        if command.decision == "approve" and quote.valid_until < self._today():
            raise FulfillmentConflict("Quotation has expired; create a new revision")
        quote.review_reason = command.reason.strip()
        quote.reviewed_by_user_id = actor.id
        quote.reviewed_at = self._now()
        target = "approved" if command.decision == "approve" else "rejected"
        self._move_quote(
            quote,
            actor,
            target,
            f"quotation.{target}",
            {"reason": quote.review_reason, "escalated": self._requires_escalation(quote)},
        )
        self._db.commit()
        self._db.refresh(quote)
        return self._quotation_response(quote)

    def send_quotation(
        self,
        quotation_id: UUID,
        command: QuotationSend,
        *,
        actor: User,
    ) -> QuotationResponse:
        quote = self._owned_quotation(quotation_id, actor)
        self._require_quote_status(quote, ("approved",), "sent")
        if quote.valid_until < self._today():
            raise FulfillmentConflict("Quotation has expired; create a new revision")
        customer = quote.opportunity.customer
        if (customer.custom_fields or {}).get("contact_suppressed"):
            raise FulfillmentConflict("Contact is suppressed and cannot receive quotations")
        quote.sent_at = self._now()
        quote.sent_channel = command.channel
        self._move_quote(quote, actor, "sent", "quotation.sent", {"channel": command.channel})
        opportunity = quote.opportunity
        if opportunity.stage == "quoting":
            self._record(opportunity, None, actor, "opportunity.stage_changed", "quoting", "negotiation", {})
            opportunity.stage = "negotiation"
        self._db.commit()
        self._db.refresh(quote)
        return self._quotation_response(quote)

    def decline_quotation(
        self,
        quotation_id: UUID,
        command: QuotationDecline,
        *,
        actor: User,
    ) -> QuotationResponse:
        quote = self._owned_quotation(quotation_id, actor)
        self._require_quote_status(quote, ("sent",), "declined")
        self._move_quote(quote, actor, "declined", "quotation.declined", {"reason": command.reason.strip()})
        self._db.commit()
        self._db.refresh(quote)
        return self._quotation_response(quote)

    def accept_quotation(
        self,
        quotation_id: UUID,
        command: QuotationAccept,
        *,
        actor: User,
    ) -> OrderDetailResponse:
        quote = self._owned_quotation(quotation_id, actor)
        self._require_quote_status(quote, ("sent",), "accepted")
        if quote.valid_until < self._today():
            raise FulfillmentConflict("Quotation has expired; create a new revision")
        opportunity = quote.opportunity
        if opportunity.stage not in OPEN_OPPORTUNITY_STAGES:
            raise FulfillmentConflict("Opportunity is already closed")

        now = self._now()
        quote.accepted_at = now
        self._move_quote(quote, actor, "accepted", "quotation.accepted", {})
        deposit = (quote.total * Decimal(quote.deposit_percent) / 100).quantize(
            CENT, rounding=ROUND_HALF_UP
        )
        order = SalesOrder(
            user_id=opportunity.user_id,
            customer_id=opportunity.customer_id,
            opportunity_id=opportunity.id,
            quotation_id=quote.id,
            order_number=f"SO-{self._today():%Y%m%d}-{uuid4().hex[:6].upper()}",
            customer_po_number=(command.customer_po_number or "").strip() or None,
            status="confirmed",
            fulfillment_mode=command.fulfillment_mode,
            currency=quote.currency,
            incoterm=quote.incoterm,
            payment_terms=quote.payment_terms,
            line_items_json=list(quote.line_items_json or []),
            total=quote.total,
            deposit_required=deposit,
            balance_before_shipment=command.balance_before_shipment,
            required_ship_date=command.required_ship_date
            or self._today() + timedelta(days=quote.lead_time_days),
            shipping_address=(command.shipping_address or "").strip() or None,
            version=1,
        )
        self._db.add(order)
        self._db.flush()

        previous_stage = opportunity.stage
        opportunity.stage = "won"
        opportunity.won_at = now
        opportunity.closed_at = now
        opportunity.estimated_value = quote.total
        self._record(opportunity, order, actor, "opportunity.stage_changed", previous_stage, "won", {})
        self._record(
            opportunity,
            order,
            actor,
            "order.created",
            None,
            "confirmed",
            {
                "order_number": order.order_number,
                "quotation_id": str(quote.id),
                "total": str(order.total),
                "deposit_required": str(deposit),
                "fulfillment_mode": order.fulfillment_mode,
            },
        )
        customer = opportunity.customer
        if customer.status != "converted":
            customer.status = "converted"
        self._db.commit()
        self._db.refresh(order)
        return self._order_detail(order)

    # -- orders ------------------------------------------------------------

    def list_orders(
        self,
        *,
        actor: User,
        status: Optional[str] = None,
        customer_id: Optional[int] = None,
    ) -> List[OrderSummaryResponse]:
        query = self._scoped(self._db.query(SalesOrder), SalesOrder, actor)
        if status:
            query = query.filter(SalesOrder.status == status)
        if customer_id:
            query = query.filter(SalesOrder.customer_id == customer_id)
        rows = query.order_by(SalesOrder.updated_at.desc()).limit(500).all()
        return [self._order_summary(row) for row in rows]

    def get_order(self, order_id: UUID, *, actor: User) -> OrderDetailResponse:
        return self._order_detail(self._owned_order(order_id, actor))

    def transition_order(
        self,
        order_id: UUID,
        command: OrderTransition,
        *,
        actor: User,
    ) -> OrderDetailResponse:
        order = self._owned_order(order_id, actor)
        blockers = self._order_blockers(order, command.status)
        if blockers:
            raise FulfillmentGateBlocked(command.status, blockers)
        previous = order.status
        now = self._now()
        order.status = command.status
        order.version += 1
        if command.status == "in_production" and order.production_started_at is None:
            order.production_started_at = now
        elif command.status == "shipped":
            order.shipped_at = now
        elif command.status == "delivered":
            order.delivered_at = now
        elif command.status == "completed":
            order.completed_at = now
        elif command.status == "cancelled":
            order.cancel_reason = (command.reason or "").strip()
            for task in order.production_tasks:
                if task.status in ("planned", "in_progress"):
                    task.status = "cancelled"
        self._record_order(
            order,
            actor,
            "order.status_changed",
            previous,
            command.status,
            {"reason": (command.reason or "").strip() or None},
        )
        self._db.commit()
        self._db.refresh(order)
        return self._order_detail(order)

    def add_production_task(
        self,
        order_id: UUID,
        command: ProductionTaskCreate,
        *,
        actor: User,
    ) -> OrderDetailResponse:
        order = self._owned_order(order_id, actor)
        if order.status not in TASK_EDITABLE_ORDER_STATUSES:
            raise FulfillmentConflict(f"Production cannot be planned while the order is {order.status}")
        if order.fulfillment_mode == "in_house" and command.kind != "work_order":
            raise FulfillmentConflict("In-house orders are produced through work orders")
        if order.fulfillment_mode == "outsourced" and command.kind != "purchase_order":
            raise FulfillmentConflict("Outsourced orders are produced through supplier purchase orders")
        prefix = "WO" if command.kind == "work_order" else "PO"
        task = ProductionTask(
            order_id=order.id,
            kind=command.kind,
            reference_number=f"{prefix}-{order.order_number[3:]}-{uuid4().hex[:4].upper()}",
            description=command.description.strip(),
            supplier_name=(command.supplier_name or "").strip() or None,
            production_line=(command.production_line or "").strip() or None,
            quantity=command.quantity,
            unit=command.unit,
            status="planned",
            progress_percent=0,
            planned_start=command.planned_start,
            planned_finish=command.planned_finish,
            notes=(command.notes or "").strip() or None,
        )
        self._db.add(task)
        self._db.flush()
        self._record_order(
            order,
            actor,
            "production.planned",
            None,
            "planned",
            {
                "task_id": str(task.id),
                "kind": task.kind,
                "reference_number": task.reference_number,
                "supplier_name": task.supplier_name,
            },
        )
        self._db.commit()
        self._db.refresh(order)
        return self._order_detail(order)

    def update_production_task(
        self,
        order_id: UUID,
        task_id: UUID,
        command: ProductionTaskUpdate,
        *,
        actor: User,
    ) -> OrderDetailResponse:
        order = self._owned_order(order_id, actor)
        task = next((item for item in order.production_tasks if item.id == task_id), None)
        if task is None:
            raise FulfillmentNotFound("Production task not found")
        if order.status in CLOSED_ORDER_STATUSES:
            raise FulfillmentConflict(f"Order is {order.status}")
        previous = task.status
        if command.status and command.status != task.status:
            if command.status not in TASK_TRANSITIONS.get(task.status, ()):
                raise FulfillmentConflict(f"Production task cannot move from {task.status} to {command.status}")
            if command.status == "in_progress" and order.status not in ("in_production", "quality_check"):
                raise FulfillmentConflict("Release the order to production before starting work")
            task.status = command.status
            if command.status == "in_progress":
                task.actual_start = self._now()
            elif command.status == "completed":
                task.progress_percent = 100
                task.actual_finish = self._now()
        if command.progress_percent is not None and task.status == "in_progress":
            task.progress_percent = command.progress_percent
        if command.planned_finish is not None:
            task.planned_finish = command.planned_finish
        if command.notes is not None:
            task.notes = command.notes.strip() or None
        self._record_order(
            order,
            actor,
            "production.updated",
            previous,
            task.status,
            {
                "task_id": str(task.id),
                "reference_number": task.reference_number,
                "progress_percent": task.progress_percent,
            },
        )
        self._db.commit()
        self._db.refresh(order)
        return self._order_detail(order)

    def record_inspection(
        self,
        order_id: UUID,
        command: InspectionCreate,
        *,
        actor: User,
    ) -> OrderDetailResponse:
        order = self._owned_order(order_id, actor)
        if order.status in CLOSED_ORDER_STATUSES or order.status in ("shipped", "delivered"):
            raise FulfillmentConflict(f"Inspections cannot be recorded while the order is {order.status}")
        if command.production_task_id and not any(
            task.id == command.production_task_id for task in order.production_tasks
        ):
            raise FulfillmentNotFound("Production task not found")
        inspection = QualityInspection(
            order_id=order.id,
            production_task_id=command.production_task_id,
            stage=command.stage,
            result=command.result,
            inspector=command.inspector.strip(),
            sample_size=command.sample_size,
            defects_json=[defect.model_dump() for defect in command.defects],
            report_url=str(command.report_url) if command.report_url else None,
            notes=(command.notes or "").strip() or None,
            inspected_at=self._naive(command.inspected_at) or self._now(),
            recorded_by_user_id=actor.id,
        )
        self._db.add(inspection)
        self._db.flush()
        self._record_order(
            order,
            actor,
            "quality.inspected",
            None,
            command.result,
            {
                "inspection_id": str(inspection.id),
                "stage": command.stage,
                "defects": len(command.defects),
            },
        )
        self._db.commit()
        self._db.refresh(order)
        return self._order_detail(order)

    def create_shipment(
        self,
        order_id: UUID,
        command: ShipmentCreate,
        *,
        actor: User,
    ) -> OrderDetailResponse:
        order = self._owned_order(order_id, actor)
        if order.status not in SHIPMENT_ORDER_STATUSES:
            raise FulfillmentConflict("Book shipments once production has reached quality check")
        if command.etd and command.eta and command.eta < command.etd:
            raise FulfillmentConflict("ETA must not be earlier than ETD")
        shipment = OrderShipment(
            order_id=order.id,
            shipment_number=f"SH-{order.order_number[3:]}-{uuid4().hex[:4].upper()}",
            status="booked",
            transport_mode=command.transport_mode,
            carrier=command.carrier.strip(),
            tracking_number=(command.tracking_number or "").strip() or None,
            bill_of_lading=(command.bill_of_lading or "").strip() or None,
            container_number=(command.container_number or "").strip() or None,
            port_of_loading=(command.port_of_loading or "").strip() or None,
            port_of_discharge=(command.port_of_discharge or "").strip() or None,
            etd=command.etd,
            eta=command.eta,
            notes=(command.notes or "").strip() or None,
        )
        self._db.add(shipment)
        self._db.flush()
        self._record_order(
            order,
            actor,
            "shipment.booked",
            None,
            "booked",
            {"shipment_id": str(shipment.id), "shipment_number": shipment.shipment_number, "carrier": shipment.carrier},
        )
        self._db.commit()
        self._db.refresh(order)
        return self._order_detail(order)

    def update_shipment(
        self,
        order_id: UUID,
        shipment_id: UUID,
        command: ShipmentUpdate,
        *,
        actor: User,
    ) -> OrderDetailResponse:
        order = self._owned_order(order_id, actor)
        shipment = next((item for item in order.shipments if item.id == shipment_id), None)
        if shipment is None:
            raise FulfillmentNotFound("Shipment not found")
        if order.status == "cancelled":
            raise FulfillmentConflict("Order is cancelled")
        for field in ("tracking_number", "bill_of_lading", "container_number", "notes"):
            value = getattr(command, field)
            if value is not None:
                setattr(shipment, field, value.strip() or None)
        if command.eta is not None:
            shipment.eta = command.eta
        previous = shipment.status
        if command.status and command.status != shipment.status:
            if command.status not in SHIPMENT_TRANSITIONS.get(shipment.status, ()):
                raise FulfillmentConflict(f"Shipment cannot move from {shipment.status} to {command.status}")
            if command.status == "departed":
                if order.status not in ("ready_to_ship", "shipped"):
                    raise FulfillmentConflict("Goods cannot depart before the order is ready to ship")
                if not (shipment.tracking_number or shipment.bill_of_lading):
                    raise FulfillmentConflict("A tracking number or bill of lading is required before departure")
                shipment.departed_at = self._now()
            elif command.status == "delivered":
                shipment.delivered_at = self._now()
            shipment.status = command.status
        self._record_order(
            order,
            actor,
            "shipment.updated",
            previous,
            shipment.status,
            {"shipment_id": str(shipment.id), "shipment_number": shipment.shipment_number},
        )
        self._db.commit()
        self._db.refresh(order)
        return self._order_detail(order)

    def record_payment(
        self,
        order_id: UUID,
        command: PaymentCreate,
        *,
        actor: User,
    ) -> Tuple[OrderDetailResponse, bool]:
        order = self._owned_order(order_id, actor)
        replay = (
            self._db.query(OrderPayment)
            .filter(
                OrderPayment.order_id == order.id,
                OrderPayment.idempotency_key == command.idempotency_key,
            )
            .one_or_none()
        )
        if replay is not None:
            if replay.amount != self._money(command.amount) or replay.kind != command.kind:
                raise FulfillmentConflict("Idempotency key was already used for a different payment")
            return self._order_detail(order), False
        if order.status == "cancelled":
            raise FulfillmentConflict("Order is cancelled")
        if command.currency != order.currency:
            raise FulfillmentConflict(f"Payment currency must be {order.currency}")
        amount = self._money(command.amount)
        if self._paid(order) + amount > order.total:
            raise FulfillmentConflict("Payment would exceed the order total")
        payment = OrderPayment(
            order_id=order.id,
            user_id=actor.id,
            idempotency_key=command.idempotency_key,
            kind=command.kind,
            amount=amount,
            currency=command.currency,
            method=command.method,
            reference=(command.reference or "").strip() or None,
            received_at=self._naive(command.received_at) or self._now(),
        )
        self._db.add(payment)
        self._db.flush()
        self._db.refresh(order)
        self._record_order(
            order,
            actor,
            "payment.received",
            None,
            None,
            {
                "payment_id": str(payment.id),
                "kind": payment.kind,
                "amount": str(amount),
                "amount_paid": str(self._paid(order)),
            },
        )
        self._db.commit()
        self._db.refresh(order)
        return self._order_detail(order), True

    # -- timeline and pipeline ---------------------------------------------

    def list_events(
        self,
        *,
        actor: User,
        opportunity_id: Optional[UUID] = None,
        order_id: Optional[UUID] = None,
    ) -> List[FulfillmentEventResponse]:
        query = self._db.query(FulfillmentEvent)
        if order_id is not None:
            order = self._owned_order(order_id, actor)
            query = query.filter(FulfillmentEvent.opportunity_id == order.opportunity_id)
        elif opportunity_id is not None:
            opportunity = self._owned_opportunity(opportunity_id, actor)
            query = query.filter(FulfillmentEvent.opportunity_id == opportunity.id)
        else:
            raise FulfillmentConflict("An opportunity or order is required")
        rows = query.order_by(FulfillmentEvent.created_at.asc()).limit(1000).all()
        return [
            FulfillmentEventResponse(
                id=row.id,
                opportunity_id=row.opportunity_id,
                order_id=row.order_id,
                actor_user_id=row.actor_user_id,
                event_type=row.event_type,
                from_status=row.from_status,
                to_status=row.to_status,
                payload=dict(row.payload_json or {}),
                created_at=row.created_at,
            )
            for row in rows
        ]

    def pipeline_overview(self, *, actor: User) -> PipelineOverview:
        today = self._today()
        leads = {
            str(status or "new"): count
            for status, count in self._db.query(Customer.status, func.count(Customer.id))
            .group_by(Customer.status)
            .all()
        }
        outreach_query = self._scoped(
            self._db.query(AgentOutreachDelivery.status, func.count(AgentOutreachDelivery.id)),
            AgentOutreachDelivery,
            actor,
        )
        outreach = {
            str(status): count
            for status, count in outreach_query.group_by(AgentOutreachDelivery.status).all()
        }

        opportunities = self._scoped(self._db.query(SalesOpportunity), SalesOpportunity, actor).all()
        opportunity_stages = []
        for stage in OPPORTUNITY_STAGES:
            rows = [row for row in opportunities if row.stage == stage]
            opportunity_stages.append(
                PipelineStage(
                    key=stage,
                    count=len(rows),
                    value=sum((Decimal(row.estimated_value or 0) for row in rows), Decimal("0")),
                )
            )
        won = sum(1 for row in opportunities if row.stage == "won")
        lost = sum(1 for row in opportunities if row.stage == "lost")
        win_rate = (
            (Decimal(won) / Decimal(won + lost) * 100).quantize(CENT, rounding=ROUND_HALF_UP)
            if won + lost
            else None
        )

        quote_query = self._scoped(
            self._db.query(SalesQuotation.status, func.count(SalesQuotation.id)),
            SalesQuotation,
            actor,
        )
        quotations = {
            str(status): count for status, count in quote_query.group_by(SalesQuotation.status).all()
        }

        orders = self._scoped(self._db.query(SalesOrder), SalesOrder, actor).all()
        order_stages = []
        for status in ORDER_STATUSES:
            rows = [row for row in orders if row.status == status]
            order_stages.append(
                PipelineStage(
                    key=status,
                    count=len(rows),
                    value=sum((Decimal(row.total) for row in rows), Decimal("0")),
                )
            )
        live_orders = [row for row in orders if row.status != "cancelled"]
        booked = sum((Decimal(row.total) for row in live_orders), Decimal("0"))
        collected = sum((self._paid(row) for row in live_orders), Decimal("0"))

        alerts: List[PipelineAlert] = []
        warning_horizon = today + timedelta(days=settings.FULFILLMENT_QUOTE_EXPIRY_WARNING_DAYS)
        live_quotes = (
            self._scoped(self._db.query(SalesQuotation), SalesQuotation, actor)
            .filter(SalesQuotation.status.in_(("approved", "sent")))
            .all()
        )
        for quote in live_quotes:
            if quote.valid_until < today:
                alerts.append(
                    PipelineAlert(
                        kind="quotation_expired",
                        severity="warning",
                        message=f"{quote.quote_number} expired on {quote.valid_until.isoformat()}",
                        opportunity_id=quote.opportunity_id,
                    )
                )
            elif quote.valid_until <= warning_horizon:
                alerts.append(
                    PipelineAlert(
                        kind="quotation_expiring",
                        severity="info",
                        message=f"{quote.quote_number} expires on {quote.valid_until.isoformat()}",
                        opportunity_id=quote.opportunity_id,
                    )
                )
        pending_review = sum(1 for row in opportunities for q in row.quotations if q.status == "approval_pending")
        if pending_review:
            alerts.append(
                PipelineAlert(
                    kind="quotation_approval_pending",
                    severity="info",
                    message=f"{pending_review} quotation(s) awaiting approval",
                )
            )
        for order in orders:
            if order.status in CLOSED_ORDER_STATUSES:
                continue
            if self._ship_date_at_risk(order, today):
                alerts.append(
                    PipelineAlert(
                        kind="ship_date_at_risk",
                        severity="critical"
                        if order.required_ship_date and order.required_ship_date < today
                        else "warning",
                        message=f"{order.order_number} must ship by {order.required_ship_date.isoformat()}",
                        opportunity_id=order.opportunity_id,
                        order_id=order.id,
                    )
                )
            if order.status == "confirmed" and self._paid(order) < order.deposit_required:
                alerts.append(
                    PipelineAlert(
                        kind="deposit_outstanding",
                        severity="info",
                        message=f"{order.order_number} awaits a {order.currency} {order.deposit_required} deposit",
                        opportunity_id=order.opportunity_id,
                        order_id=order.id,
                    )
                )
            for task in order.production_tasks:
                if self._task_overdue(task, today):
                    alerts.append(
                        PipelineAlert(
                            kind="production_overdue",
                            severity="warning",
                            message=f"{task.reference_number} was due {task.planned_finish.isoformat()}",
                            opportunity_id=order.opportunity_id,
                            order_id=order.id,
                        )
                    )
            final = self._latest_final_inspection(order)
            if final is not None and final.result == "failed":
                alerts.append(
                    PipelineAlert(
                        kind="final_inspection_failed",
                        severity="critical",
                        message=f"{order.order_number} failed pre-shipment inspection",
                        opportunity_id=order.opportunity_id,
                        order_id=order.id,
                    )
                )
            for shipment in order.shipments:
                if shipment.status in ("departed", "arrived") and shipment.eta and shipment.eta < today:
                    alerts.append(
                        PipelineAlert(
                            kind="shipment_overdue",
                            severity="warning",
                            message=f"{shipment.shipment_number} passed its ETA {shipment.eta.isoformat()}",
                            opportunity_id=order.opportunity_id,
                            order_id=order.id,
                        )
                    )

        return PipelineOverview(
            leads=leads,
            outreach=outreach,
            opportunities=opportunity_stages,
            quotations=quotations,
            orders=order_stages,
            win_rate_percent=win_rate,
            booked_value=booked,
            collected_value=collected,
            unconverted_inquiries=self._unconverted_inquiries(),
            alerts=alerts,
        )

    # -- gates -------------------------------------------------------------

    def _order_blockers(self, order: SalesOrder, target: str) -> List[str]:
        if target not in ORDER_TRANSITIONS.get(order.status, ()):
            return [f"Order cannot move from {order.status} to {target}"]
        blockers: List[str] = []
        paid = self._paid(order)
        active_tasks = [task for task in order.production_tasks if task.status != "cancelled"]
        if target == "in_production":
            if paid < order.deposit_required:
                blockers.append(
                    f"Deposit of {order.currency} {order.deposit_required} not received "
                    f"(received {paid})"
                )
            if not active_tasks:
                blockers.append("Plan at least one work order or supplier purchase order")
        elif target == "quality_check":
            if not active_tasks:
                blockers.append("No active production tasks")
            open_tasks = [task.reference_number for task in active_tasks if task.status != "completed"]
            if open_tasks:
                blockers.append("Production still open: " + ", ".join(open_tasks))
        elif target == "ready_to_ship":
            final = self._latest_final_inspection(order)
            if final is None:
                blockers.append("Record a pre-shipment inspection")
            elif final.result != "passed":
                blockers.append(f"Latest pre-shipment inspection is {final.result}")
        elif target == "shipped":
            if not any(item.status in ("departed", "arrived", "delivered") for item in order.shipments):
                blockers.append("No shipment has departed")
            if order.balance_before_shipment and paid < order.total:
                blockers.append(
                    f"Balance of {order.currency} {order.total - paid} is due before shipment"
                )
        elif target == "delivered":
            departed = [item for item in order.shipments if item.status != "booked"]
            if not departed:
                blockers.append("No shipment has departed")
            pending = [item.shipment_number for item in departed if item.status != "delivered"]
            if pending:
                blockers.append("Shipments not yet delivered: " + ", ".join(pending))
        elif target == "completed":
            if paid < order.total:
                blockers.append(f"Outstanding balance of {order.currency} {order.total - paid}")
        return blockers

    def _requires_escalation(self, quote: SalesQuotation) -> bool:
        if Decimal(quote.total) > Decimal(str(settings.FULFILLMENT_QUOTE_APPROVAL_THRESHOLD)):
            return True
        if quote.margin_percent is not None and Decimal(quote.margin_percent) < Decimal(
            str(settings.FULFILLMENT_QUOTE_MIN_MARGIN_PERCENT)
        ):
            return True
        return False

    # -- helpers -----------------------------------------------------------

    @staticmethod
    def _scoped(query, model, actor: User):
        if actor.is_superuser:
            return query
        if model is SalesQuotation:
            return query.join(
                SalesOpportunity, SalesQuotation.opportunity_id == SalesOpportunity.id
            ).filter(SalesOpportunity.user_id == actor.id)
        return query.filter(model.user_id == actor.id)

    def _owned_opportunity(self, opportunity_id: UUID, actor: User) -> SalesOpportunity:
        row = (
            self._scoped(self._db.query(SalesOpportunity), SalesOpportunity, actor)
            .filter(SalesOpportunity.id == opportunity_id)
            .one_or_none()
        )
        if row is None:
            raise FulfillmentNotFound("Opportunity not found")
        return row

    def _owned_quotation(self, quotation_id: UUID, actor: User) -> SalesQuotation:
        row = (
            self._scoped(self._db.query(SalesQuotation), SalesQuotation, actor)
            .filter(SalesQuotation.id == quotation_id)
            .one_or_none()
        )
        if row is None:
            raise FulfillmentNotFound("Quotation not found")
        return row

    def _owned_order(self, order_id: UUID, actor: User) -> SalesOrder:
        row = (
            self._scoped(self._db.query(SalesOrder), SalesOrder, actor)
            .filter(SalesOrder.id == order_id)
            .one_or_none()
        )
        if row is None:
            raise FulfillmentNotFound("Order not found")
        return row

    @staticmethod
    def _require_quote_status(quote: SalesQuotation, allowed: Sequence[str], action: str) -> None:
        if quote.status not in allowed:
            raise FulfillmentConflict(f"A {quote.status} quotation cannot be {action}")

    def _move_quote(
        self,
        quote: SalesQuotation,
        actor: User,
        target: str,
        event_type: str,
        payload: Dict[str, object],
    ) -> None:
        previous = quote.status
        quote.status = target
        self._record(
            quote.opportunity,
            None,
            actor,
            event_type,
            previous,
            target,
            {"quotation_id": str(quote.id), "quote_number": quote.quote_number, **payload},
        )

    def _supersede_live_quotations(self, opportunity: SalesOpportunity, actor: User, *, reason: str) -> None:
        for quote in opportunity.quotations:
            if quote.status in LIVE_QUOTATION_STATUSES:
                self._move_quote(quote, actor, "superseded", "quotation.superseded", {"reason": reason})

    def _record(
        self,
        opportunity: SalesOpportunity,
        order: Optional[SalesOrder],
        actor: Optional[User],
        event_type: str,
        from_status: Optional[str],
        to_status: Optional[str],
        payload: Dict[str, object],
    ) -> None:
        self._db.add(
            FulfillmentEvent(
                opportunity_id=opportunity.id,
                order_id=order.id if order is not None else None,
                actor_user_id=actor.id if actor is not None else None,
                event_type=event_type,
                from_status=from_status,
                to_status=to_status,
                payload_json=payload,
                created_at=self._now(),
            )
        )

    def _record_order(
        self,
        order: SalesOrder,
        actor: User,
        event_type: str,
        from_status: Optional[str],
        to_status: Optional[str],
        payload: Dict[str, object],
    ) -> None:
        self._db.add(
            FulfillmentEvent(
                opportunity_id=order.opportunity_id,
                order_id=order.id,
                actor_user_id=actor.id,
                event_type=event_type,
                from_status=from_status,
                to_status=to_status,
                payload_json=payload,
                created_at=self._now(),
            )
        )

    @staticmethod
    def _mark_customer_engaged(customer: Customer) -> None:
        if customer.status in (None, "new", "contacted"):
            customer.status = "engaged"

    def _unconverted_inquiries(self) -> List[UnconvertedInquiry]:
        converted = self._db.query(SalesOpportunity.conversation_id).filter(
            SalesOpportunity.conversation_id.isnot(None)
        )
        rows = (
            self._db.query(Conversation)
            .filter(
                Conversation.current_intent.in_(BUYING_INTENTS),
                Conversation.status == ConversationStatus.ACTIVE,
                Conversation.id.notin_(converted),
            )
            .order_by(Conversation.last_message_at.desc())
            .limit(20)
            .all()
        )
        return [
            UnconvertedInquiry(
                conversation_id=row.id,
                customer_id=row.customer_id,
                customer_name=self._customer_name(row.customer),
                intent=row.current_intent,
                last_message_at=row.last_message_at,
            )
            for row in rows
            if row.customer is not None
        ]

    def _price_lines(
        self,
        items: Sequence[QuotationLineItem],
    ) -> Tuple[List[Dict[str, object]], Decimal, Optional[Decimal]]:
        lines: List[Dict[str, object]] = []
        subtotal = Decimal("0")
        total_cost: Optional[Decimal] = Decimal("0")
        for item in items:
            amount = self._money(item.quantity * item.unit_price)
            subtotal += amount
            if item.unit_cost is None or total_cost is None:
                total_cost = None
            else:
                total_cost += self._money(item.quantity * item.unit_cost)
            lines.append(
                {
                    "product": item.product.strip(),
                    "description": (item.description or "").strip() or None,
                    "hs_code": item.hs_code,
                    "quantity": str(item.quantity),
                    "unit": item.unit,
                    "unit_price": str(item.unit_price),
                    "amount": str(amount),
                }
            )
        return lines, subtotal, total_cost

    @staticmethod
    def _requirements_json(requirements: OpportunityRequirements) -> Dict[str, object]:
        return requirements.model_dump(mode="json", exclude_none=True, exclude_defaults=True)

    @staticmethod
    def _paid(order: SalesOrder) -> Decimal:
        return sum((Decimal(payment.amount) for payment in order.payments), Decimal("0")).quantize(CENT)

    @staticmethod
    def _latest_final_inspection(order: SalesOrder) -> Optional[QualityInspection]:
        finals = [item for item in order.inspections if item.stage == "pre_shipment"]
        if not finals:
            return None
        return max(finals, key=lambda item: (item.inspected_at, item.created_at))

    @staticmethod
    def _task_overdue(task: ProductionTask, today: date) -> bool:
        return (
            task.status in ("planned", "in_progress")
            and task.planned_finish is not None
            and task.planned_finish < today
        )

    @classmethod
    def _ship_date_at_risk(cls, order: SalesOrder, today: date) -> bool:
        if order.required_ship_date is None or order.status not in (
            "confirmed",
            "in_production",
            "quality_check",
            "ready_to_ship",
        ):
            return False
        if order.required_ship_date < today:
            return True
        return any(
            task.status in ("planned", "in_progress")
            and task.planned_finish is not None
            and task.planned_finish > order.required_ship_date
            for task in order.production_tasks
        ) or any(cls._task_overdue(task, today) for task in order.production_tasks)

    @staticmethod
    def _production_progress(order: SalesOrder) -> int:
        active = [task for task in order.production_tasks if task.status != "cancelled"]
        if not active:
            return 0
        return round(sum(task.progress_percent for task in active) / len(active))

    @staticmethod
    def _customer_name(customer: Optional[Customer]) -> str:
        if customer is None:
            return ""
        return customer.company_name or customer.username or customer.email or f"#{customer.id}"

    @staticmethod
    def _money(value: Decimal) -> Decimal:
        return Decimal(value).quantize(CENT, rounding=ROUND_HALF_UP)

    @classmethod
    def _money_or_none(cls, value: Optional[Decimal]) -> Optional[Decimal]:
        return None if value is None else cls._money(value)

    # -- responses ---------------------------------------------------------

    def _opportunity_response(self, row: SalesOpportunity) -> OpportunityResponse:
        order_id = (
            self._db.query(SalesOrder.id)
            .filter(SalesOrder.opportunity_id == row.id)
            .scalar()
            if row.stage == "won"
            else None
        )
        return OpportunityResponse(
            id=row.id,
            customer_id=row.customer_id,
            customer_name=self._customer_name(row.customer),
            conversation_id=row.conversation_id,
            title=row.title,
            source=row.source,
            stage=row.stage,
            allowed_stages=list(OPPORTUNITY_TRANSITIONS.get(row.stage, ())),
            inquiry_summary=row.inquiry_summary,
            requirements=dict(row.requirements_json or {}),
            estimated_value=row.estimated_value,
            currency=row.currency,
            expected_close_date=row.expected_close_date,
            lost_reason=row.lost_reason,
            won_at=row.won_at,
            order_id=order_id,
            quotation_count=len(row.quotations),
            created_at=row.created_at,
            updated_at=row.updated_at,
        )

    def _quotation_response(self, row: SalesQuotation) -> QuotationResponse:
        return QuotationResponse(
            id=row.id,
            opportunity_id=row.opportunity_id,
            quote_number=row.quote_number,
            revision=row.revision,
            status=row.status,
            currency=row.currency,
            incoterm=row.incoterm,
            payment_terms=row.payment_terms,
            deposit_percent=row.deposit_percent,
            lead_time_days=row.lead_time_days,
            valid_until=row.valid_until,
            expired=row.status in LIVE_QUOTATION_STATUSES and row.valid_until < self._today(),
            line_items=list(row.line_items_json or []),
            subtotal=row.subtotal,
            freight_amount=row.freight_amount,
            discount_amount=row.discount_amount,
            total=row.total,
            margin_percent=row.margin_percent,
            requires_escalated_approval=self._requires_escalation(row),
            notes=row.notes,
            review_reason=row.review_reason,
            reviewed_by_user_id=row.reviewed_by_user_id,
            reviewed_at=row.reviewed_at,
            sent_at=row.sent_at,
            sent_channel=row.sent_channel,
            accepted_at=row.accepted_at,
            created_at=row.created_at,
        )

    def _order_summary_fields(self, row: SalesOrder) -> Dict[str, object]:
        paid = self._paid(row)
        return {
            "id": row.id,
            "order_number": row.order_number,
            "customer_id": row.customer_id,
            "customer_name": self._customer_name(row.customer),
            "opportunity_id": row.opportunity_id,
            "quotation_id": row.quotation_id,
            "status": row.status,
            "fulfillment_mode": row.fulfillment_mode,
            "currency": row.currency,
            "total": row.total,
            "amount_paid": paid,
            "balance_due": Decimal(row.total) - paid,
            "required_ship_date": row.required_ship_date,
            "ship_date_at_risk": self._ship_date_at_risk(row, self._today()),
            "production_progress_percent": self._production_progress(row),
            "created_at": row.created_at,
            "updated_at": row.updated_at,
        }

    def _order_summary(self, row: SalesOrder) -> OrderSummaryResponse:
        return OrderSummaryResponse(**self._order_summary_fields(row))

    def _order_detail(self, row: SalesOrder) -> OrderDetailResponse:
        today = self._today()
        return OrderDetailResponse(
            **self._order_summary_fields(row),
            customer_po_number=row.customer_po_number,
            incoterm=row.incoterm,
            payment_terms=row.payment_terms,
            line_items=list(row.line_items_json or []),
            deposit_required=row.deposit_required,
            balance_before_shipment=row.balance_before_shipment,
            shipping_address=row.shipping_address,
            cancel_reason=row.cancel_reason,
            production_started_at=row.production_started_at,
            shipped_at=row.shipped_at,
            delivered_at=row.delivered_at,
            completed_at=row.completed_at,
            version=row.version,
            next_transitions=[
                TransitionReadiness(
                    status=target,
                    ready=not blockers,
                    blockers=blockers,
                )
                for target in ORDER_TRANSITIONS.get(row.status, ())
                if target != "cancelled"
                for blockers in [self._order_blockers(row, target)]
            ],
            production_tasks=[
                ProductionTaskResponse(
                    id=task.id,
                    kind=task.kind,
                    reference_number=task.reference_number,
                    description=task.description,
                    supplier_name=task.supplier_name,
                    production_line=task.production_line,
                    quantity=task.quantity,
                    unit=task.unit,
                    status=task.status,
                    progress_percent=task.progress_percent,
                    planned_start=task.planned_start,
                    planned_finish=task.planned_finish,
                    actual_start=task.actual_start,
                    actual_finish=task.actual_finish,
                    overdue=self._task_overdue(task, today),
                    notes=task.notes,
                )
                for task in row.production_tasks
            ],
            inspections=[
                InspectionResponse(
                    id=item.id,
                    production_task_id=item.production_task_id,
                    stage=item.stage,
                    result=item.result,
                    inspector=item.inspector,
                    sample_size=item.sample_size,
                    defects=list(item.defects_json or []),
                    report_url=item.report_url,
                    notes=item.notes,
                    inspected_at=item.inspected_at,
                )
                for item in row.inspections
            ],
            shipments=[
                ShipmentResponse(
                    id=item.id,
                    shipment_number=item.shipment_number,
                    status=item.status,
                    transport_mode=item.transport_mode,
                    carrier=item.carrier,
                    tracking_number=item.tracking_number,
                    bill_of_lading=item.bill_of_lading,
                    container_number=item.container_number,
                    port_of_loading=item.port_of_loading,
                    port_of_discharge=item.port_of_discharge,
                    etd=item.etd,
                    eta=item.eta,
                    departed_at=item.departed_at,
                    delivered_at=item.delivered_at,
                    notes=item.notes,
                )
                for item in row.shipments
            ],
            payments=[
                PaymentResponse(
                    id=item.id,
                    kind=item.kind,
                    amount=item.amount,
                    currency=item.currency,
                    method=item.method,
                    reference=item.reference,
                    received_at=item.received_at,
                )
                for item in row.payments
            ],
        )

    # -- clock -------------------------------------------------------------

    @staticmethod
    def _now() -> datetime:
        return datetime.now(timezone.utc).replace(tzinfo=None)

    @classmethod
    def _today(cls) -> date:
        return cls._now().date()

    @staticmethod
    def _naive(value: Optional[datetime]) -> Optional[datetime]:
        if value is None or value.tzinfo is None:
            return value
        return value.astimezone(timezone.utc).replace(tzinfo=None)
