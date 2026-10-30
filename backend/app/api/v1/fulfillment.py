"""Authenticated opportunity, quotation, order, production and delivery API."""
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.orm import Session

from app.api.v1.auth import get_current_active_user
from app.db import get_db
from app.models.database import User
from app.services.fulfillment import (
    FulfillmentConflict,
    FulfillmentEventResponse,
    FulfillmentForbidden,
    FulfillmentGateBlocked,
    FulfillmentNotFound,
    FulfillmentService,
    InspectionCreate,
    OpportunityCreate,
    OpportunityFromConversation,
    OpportunityResponse,
    OpportunityTransition,
    OpportunityUpdate,
    OrderDetailResponse,
    OrderSummaryResponse,
    OrderTransition,
    PaymentCreate,
    PipelineOverview,
    ProductionTaskCreate,
    ProductionTaskUpdate,
    QuotationAccept,
    QuotationCreate,
    QuotationDecline,
    QuotationResponse,
    QuotationReview,
    QuotationSend,
    ShipmentCreate,
    ShipmentUpdate,
)


router = APIRouter()


def _http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, FulfillmentNotFound):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, FulfillmentForbidden):
        return HTTPException(status_code=403, detail=str(exc))
    if isinstance(exc, FulfillmentGateBlocked):
        return HTTPException(
            status_code=409,
            detail={"message": str(exc), "status": exc.status, "blockers": exc.blockers},
        )
    return HTTPException(status_code=409, detail=str(exc))


FULFILLMENT_ERRORS = (
    FulfillmentNotFound,
    FulfillmentConflict,
    FulfillmentForbidden,
    FulfillmentGateBlocked,
)


def service(db: Session = Depends(get_db)) -> FulfillmentService:
    return FulfillmentService(db)


@router.get("/pipeline", response_model=PipelineOverview)
async def pipeline_overview(
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    return fulfillment.pipeline_overview(actor=current_user)


@router.get("/events", response_model=List[FulfillmentEventResponse])
async def list_events(
    opportunity_id: Optional[UUID] = None,
    order_id: Optional[UUID] = None,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.list_events(
            actor=current_user,
            opportunity_id=opportunity_id,
            order_id=order_id,
        )
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.get("/opportunities", response_model=List[OpportunityResponse])
async def list_opportunities(
    stage: Optional[str] = Query(default=None, max_length=30),
    customer_id: Optional[int] = Query(default=None, gt=0),
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    return fulfillment.list_opportunities(
        actor=current_user,
        stage=stage,
        customer_id=customer_id,
    )


@router.post(
    "/opportunities",
    response_model=OpportunityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_opportunity(
    command: OpportunityCreate,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.create_opportunity(command, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.post(
    "/opportunities/from-conversation/{conversation_id}",
    response_model=OpportunityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_opportunity_from_conversation(
    conversation_id: UUID,
    command: OpportunityFromConversation,
    response: Response,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        result, created = fulfillment.create_opportunity_from_conversation(
            conversation_id,
            command,
            actor=current_user,
        )
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return result


@router.get("/opportunities/{opportunity_id}", response_model=OpportunityResponse)
async def get_opportunity(
    opportunity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.get_opportunity(opportunity_id, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.patch("/opportunities/{opportunity_id}", response_model=OpportunityResponse)
async def update_opportunity(
    opportunity_id: UUID,
    command: OpportunityUpdate,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.update_opportunity(opportunity_id, command, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.post("/opportunities/{opportunity_id}/transition", response_model=OpportunityResponse)
async def transition_opportunity(
    opportunity_id: UUID,
    command: OpportunityTransition,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.transition_opportunity(opportunity_id, command, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.get(
    "/opportunities/{opportunity_id}/quotations",
    response_model=List[QuotationResponse],
)
async def list_quotations(
    opportunity_id: UUID,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.list_quotations(opportunity_id, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.post(
    "/opportunities/{opportunity_id}/quotations",
    response_model=QuotationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_quotation(
    opportunity_id: UUID,
    command: QuotationCreate,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.create_quotation(opportunity_id, command, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.post("/quotations/{quotation_id}/submit", response_model=QuotationResponse)
async def submit_quotation(
    quotation_id: UUID,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.submit_quotation(quotation_id, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.post("/quotations/{quotation_id}/review", response_model=QuotationResponse)
async def review_quotation(
    quotation_id: UUID,
    command: QuotationReview,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.review_quotation(quotation_id, command, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.post("/quotations/{quotation_id}/send", response_model=QuotationResponse)
async def send_quotation(
    quotation_id: UUID,
    command: QuotationSend,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.send_quotation(quotation_id, command, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.post("/quotations/{quotation_id}/decline", response_model=QuotationResponse)
async def decline_quotation(
    quotation_id: UUID,
    command: QuotationDecline,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.decline_quotation(quotation_id, command, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.post(
    "/quotations/{quotation_id}/accept",
    response_model=OrderDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def accept_quotation(
    quotation_id: UUID,
    command: QuotationAccept,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.accept_quotation(quotation_id, command, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.get("/orders", response_model=List[OrderSummaryResponse])
async def list_orders(
    order_status: Optional[str] = Query(default=None, alias="status", max_length=30),
    customer_id: Optional[int] = Query(default=None, gt=0),
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    return fulfillment.list_orders(
        actor=current_user,
        status=order_status,
        customer_id=customer_id,
    )


@router.get("/orders/{order_id}", response_model=OrderDetailResponse)
async def get_order(
    order_id: UUID,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.get_order(order_id, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.post("/orders/{order_id}/transition", response_model=OrderDetailResponse)
async def transition_order(
    order_id: UUID,
    command: OrderTransition,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.transition_order(order_id, command, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.post(
    "/orders/{order_id}/production-tasks",
    response_model=OrderDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def add_production_task(
    order_id: UUID,
    command: ProductionTaskCreate,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.add_production_task(order_id, command, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.patch(
    "/orders/{order_id}/production-tasks/{task_id}",
    response_model=OrderDetailResponse,
)
async def update_production_task(
    order_id: UUID,
    task_id: UUID,
    command: ProductionTaskUpdate,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.update_production_task(order_id, task_id, command, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.post(
    "/orders/{order_id}/inspections",
    response_model=OrderDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_inspection(
    order_id: UUID,
    command: InspectionCreate,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.record_inspection(order_id, command, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.post(
    "/orders/{order_id}/shipments",
    response_model=OrderDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_shipment(
    order_id: UUID,
    command: ShipmentCreate,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.create_shipment(order_id, command, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.patch(
    "/orders/{order_id}/shipments/{shipment_id}",
    response_model=OrderDetailResponse,
)
async def update_shipment(
    order_id: UUID,
    shipment_id: UUID,
    command: ShipmentUpdate,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        return fulfillment.update_shipment(order_id, shipment_id, command, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc


@router.post(
    "/orders/{order_id}/payments",
    response_model=OrderDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def record_payment(
    order_id: UUID,
    command: PaymentCreate,
    response: Response,
    current_user: User = Depends(get_current_active_user),
    fulfillment: FulfillmentService = Depends(service),
):
    try:
        result, created = fulfillment.record_payment(order_id, command, actor=current_user)
    except FULFILLMENT_ERRORS as exc:
        raise _http_error(exc) from exc
    if not created:
        response.status_code = status.HTTP_200_OK
    return result
