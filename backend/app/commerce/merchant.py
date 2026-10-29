"""``MerchantBackend`` over B-agent: the operations assistant's metrics, catalog,
campaigns, alerts and the durable staged-change ledger.

Reads come from the live tables: booked orders, collected payments, new inquiries and
sent quotations make the business metrics, the catalog makes the listings, fulfillment
risk makes the order issues. Every write is staged in ``commerce_staged_changes`` and
reaches the catalog or campaign tables only through :meth:`BAgentMerchant.apply_change`,
which the runtime calls after the operator approved the change in the console.
"""

import asyncio
import sqlite3
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Any, Callable, Dict, List, Optional, Tuple
from uuid import uuid4

from sqlalchemy.orm import Session

from commerce_common.fencing import truncate_display
from merchant_agent import (
    ActorKind,
    AlertCounts,
    AnalysisTable,
    BusinessSnapshot,
    Campaign,
    CampaignDraft,
    ChangeItem,
    ChangeKind,
    ChangeNotApplicable,
    ChangeStatus,
    DataLimitation,
    GuardrailViolation,
    InventoryActionItem,
    InventoryAlert,
    Listing,
    ListingDetails,
    ListingFilters,
    MerchantAgentConfig,
    MerchantBackend,
    MerchantSessionContext,
    MetricPoint,
    MetricSeries,
    OrderIssue,
    PriceUpdateItem,
    PricingContext,
    PromotionDraft,
    StagedChange,
    check_analysis_sql,
)
from merchant_agent.changes import check_drift, check_guardrails, expires_at

from app.commerce.catalog import families, money, ranked, to_listing, to_listing_details
from app.commerce.stores import SessionScope, utcnow
from app.models.database import (
    AgentOutreachDelivery,
    CatalogProduct,
    CatalogPromotion,
    CommerceStagedChange,
    MarketingCampaign,
    OrderPayment,
    QualityInspection,
    SalesOpportunity,
    SalesOrder,
    SalesQuotation,
)


MERCHANT_ID = "b-agent"
CONTENT_FIELDS = ("title", "short_description", "long_description", "category")
METRICS = {
    "sales": ("Booked order value", "currency"),
    "orders": ("Confirmed orders", "count"),
    "inquiries": ("New buyer inquiries", "count"),
    "quotations_sent": ("Quotations sent", "count"),
    "collected": ("Payments received", "currency"),
    "outreach_sent": ("Outreach emails sent", "count"),
}
METRIC_ALIASES = {
    "revenue": "sales",
    "gmv": "sales",
    "booked": "sales",
    "order_count": "orders",
    "traffic": "inquiries",
    "leads": "inquiries",
    "quotes": "quotations_sent",
    "payments": "collected",
    "cash": "collected",
    "outreach": "outreach_sent",
}
HISTORY_DAYS = 180


def _as_utc(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value


def _pct(current: float, prior: float) -> Optional[float]:
    if prior <= 0:
        return None
    return round((current - prior) / prior * 100, 1)


def _margin(price: float, unit_cost: float) -> float:
    return round((price - unit_cost) / price * 100, 1)


def window(period: Optional[str], today: date) -> Tuple[date, date, date, date]:
    """The period's first and last day, then the prior window of the same length. Seven
    days unless the period names 30 or 90 days, a quarter, or an ISO ``start/end`` range."""
    days = 7
    cleaned = (period or "").strip().lower()
    if cleaned in {"last_30_days", "last 30 days", "30d", "month", "this_month"}:
        days = 30
    elif cleaned in {"last_90_days", "last 90 days", "90d", "quarter"}:
        days = 90
    elif "/" in cleaned:
        try:
            start_text, end_text = cleaned.split("/", 1)
            start = date.fromisoformat(start_text.strip())
            end = date.fromisoformat(end_text.strip())
            if start <= end:
                length = (end - start).days + 1
                return start, end, start - timedelta(days=length), start - timedelta(days=1)
        except ValueError:
            pass
    end = today
    start = end - timedelta(days=days - 1)
    return start, end, start - timedelta(days=days), start - timedelta(days=1)


class SqlChangeLedger:
    """``merchant_agent.ChangeLedger`` semantics over ``commerce_staged_changes``: the
    guardrails at stage and at apply, expiry after ``staged_change_ttl_minutes``, drift
    refusal at apply, and resolved changes kept as the audit trail."""

    def __init__(
        self,
        scope: SessionScope,
        config: MerchantAgentConfig,
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._scope = scope
        self.config = config
        self._clock = clock

    @staticmethod
    def _load(row: CommerceStagedChange) -> StagedChange:
        return StagedChange.model_validate(row.document_json)

    @staticmethod
    def _store(row: CommerceStagedChange, change: StagedChange) -> None:
        row.document_json = change.model_dump(mode="json")
        row.status = change.status.value
        row.kind = change.kind.value

    def _expire_overdue(self, db: Session) -> None:
        now = self._clock()
        for row in db.query(CommerceStagedChange).filter(CommerceStagedChange.status == "staged"):
            change = self._load(row)
            deadline = expires_at(change, self.config)
            if now >= _as_utc(deadline):
                self._store(
                    row,
                    change.model_copy(update={"status": ChangeStatus.EXPIRED, "expired_at": deadline}),
                )
        db.commit()

    def stage(
        self,
        *,
        kind: ChangeKind,
        summary: str,
        items: List[ChangeItem],
        actor: str,
        actor_kind: ActorKind = ActorKind.AGENT,
        currency: Optional[str] = None,
        margin_impact: Optional[float] = None,
        margin_before_pct: Optional[float] = None,
        margin_after_pct: Optional[float] = None,
        guardrail_notes: Optional[List[str]] = None,
    ) -> StagedChange:
        violations = check_guardrails(kind, items, self.config)
        if violations:
            raise GuardrailViolation(violations)
        change = StagedChange(
            change_id=f"chg-{uuid4().hex[:8]}",
            kind=kind,
            status=ChangeStatus.STAGED,
            summary=truncate_display(summary, 200),
            items=items,
            created_at=self._clock(),
            created_by=actor,
            created_by_kind=actor_kind,
            guardrail_notes=guardrail_notes or [],
            currency=currency,
            margin_impact=margin_impact,
            margin_before_pct=margin_before_pct,
            margin_after_pct=margin_after_pct,
        )
        with self._scope() as db:
            row = CommerceStagedChange(id=change.change_id, kind=kind.value, status="staged", document_json={})
            self._store(row, change)
            db.add(row)
            db.commit()
        return change

    def get(self, change_id: str) -> Optional[StagedChange]:
        with self._scope() as db:
            self._expire_overdue(db)
            row = db.get(CommerceStagedChange, change_id)
            return self._load(row) if row is not None else None

    def pending(self) -> List[StagedChange]:
        with self._scope() as db:
            self._expire_overdue(db)
            rows = (
                db.query(CommerceStagedChange)
                .filter(CommerceStagedChange.status == "staged")
                .order_by(CommerceStagedChange.created_at)
                .all()
            )
            return [self._load(row) for row in rows]

    def resolved(self, limit: int = 50) -> List[StagedChange]:
        with self._scope() as db:
            self._expire_overdue(db)
            rows = (
                db.query(CommerceStagedChange)
                .filter(CommerceStagedChange.status != "staged")
                .order_by(CommerceStagedChange.updated_at.desc())
                .limit(limit)
                .all()
            )
            return [self._load(row) for row in rows]

    def require_staged(self, db: Session, change_id: str, action: str) -> Tuple[CommerceStagedChange, StagedChange]:
        self._expire_overdue(db)
        row = db.get(CommerceStagedChange, change_id)
        if row is None:
            raise ChangeNotApplicable(f"no change with id {change_id!r} to {action}")
        change = self._load(row)
        if change.status is ChangeStatus.EXPIRED:
            raise ChangeNotApplicable(
                f"change {change_id} expired unapproved after "
                f"{self.config.staged_change_ttl_minutes} minutes and was not applied — "
                f"nothing to {action}; stage it again from the current values"
            )
        if change.status is not ChangeStatus.STAGED:
            raise ChangeNotApplicable(
                f"change {change_id} is {change.status.value}, not staged — nothing to {action}"
            )
        return row, change

    def mark_applied(self, db: Session, row: CommerceStagedChange, change: StagedChange, actor: str) -> StagedChange:
        updated = change.model_copy(
            update={"status": ChangeStatus.APPLIED, "applied_at": self._clock(), "applied_by": actor}
        )
        self._store(row, updated)
        return updated

    def discard(self, change_id: str, actor: str, actor_kind: ActorKind = ActorKind.OPERATOR) -> StagedChange:
        with self._scope() as db:
            row, change = self.require_staged(db, change_id, "discard")
            updated = change.model_copy(
                update={
                    "status": ChangeStatus.DISCARDED,
                    "discarded_at": self._clock(),
                    "discarded_by": actor,
                    "discarded_by_kind": actor_kind,
                }
            )
            self._store(row, updated)
            db.commit()
            return updated


class BAgentMerchant(MerchantBackend):
    def __init__(
        self,
        scope: SessionScope,
        config: MerchantAgentConfig,
        *,
        reporting_currency: str = "USD",
        clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
    ) -> None:
        self._scope = scope
        self.config = config
        self.currency = reporting_currency
        self._clock = clock
        self.ledger = SqlChangeLedger(scope, config, clock)

    # -- Daily rows ---------------------------------------------------------------

    def _today(self) -> date:
        return self._clock().date()

    def _daily(self, db: Session, metric: str, start: date, end: date, segment: Optional[str] = None) -> Dict[date, float]:
        begin = datetime.combine(start, datetime.min.time())
        finish = datetime.combine(end + timedelta(days=1), datetime.min.time())
        values: Dict[date, float] = defaultdict(float)
        if metric in ("sales", "orders"):
            rows = (
                db.query(SalesOrder)
                .filter(
                    SalesOrder.created_at >= begin,
                    SalesOrder.created_at < finish,
                    SalesOrder.status != "cancelled",
                    SalesOrder.currency == self.currency,
                )
                .all()
            )
            categories = self._sku_categories(db) if segment else {}
            for row in rows:
                day = row.created_at.date()
                if segment:
                    amount = sum(
                        float(line.get("amount") or 0)
                        for line in row.line_items_json or []
                        if categories.get(str(line.get("sku")), "").casefold() == segment.casefold()
                    )
                    if not amount:
                        continue
                    values[day] += amount if metric == "sales" else 1
                else:
                    values[day] += float(row.total) if metric == "sales" else 1
        elif metric == "inquiries":
            for row in db.query(SalesOpportunity.created_at).filter(
                SalesOpportunity.created_at >= begin, SalesOpportunity.created_at < finish
            ):
                values[row.created_at.date()] += 1
        elif metric == "quotations_sent":
            for row in db.query(SalesQuotation.sent_at).filter(
                SalesQuotation.sent_at >= begin, SalesQuotation.sent_at < finish
            ):
                values[row.sent_at.date()] += 1
        elif metric == "collected":
            for row in db.query(OrderPayment).filter(
                OrderPayment.received_at >= begin,
                OrderPayment.received_at < finish,
                OrderPayment.currency == self.currency,
            ):
                values[row.received_at.date()] += float(row.amount)
        elif metric == "outreach_sent":
            for row in db.query(AgentOutreachDelivery.updated_at).filter(
                AgentOutreachDelivery.status == "sent",
                AgentOutreachDelivery.updated_at >= begin,
                AgentOutreachDelivery.updated_at < finish,
            ):
                values[row.updated_at.date()] += 1
        return values

    @staticmethod
    def _sku_categories(db: Session) -> Dict[str, str]:
        rows = db.query(CatalogProduct.id, CatalogProduct.parent_id, CatalogProduct.category).all()
        by_id = {row.id: row for row in rows}
        return {
            row.id: (row.category or (by_id[row.parent_id].category if row.parent_id in by_id else "") or "")
            for row in rows
        }

    # -- Performance --------------------------------------------------------------

    async def get_business_snapshot(
        self, session: MerchantSessionContext, period: Optional[str] = None
    ) -> BusinessSnapshot:
        start, end, prior_start, prior_end = window(period, self._today())
        with self._scope() as db:
            current = {m: sum(self._daily(db, m, start, end).values()) for m in ("sales", "orders", "inquiries")}
            prior = {
                m: sum(self._daily(db, m, prior_start, prior_end).values())
                for m in ("sales", "orders", "inquiries")
            }
        alerts = await self._alert_counts(session)
        conversion = round(current["orders"] / current["inquiries"] * 100, 2) if current["inquiries"] else None
        prior_conversion = round(prior["orders"] / prior["inquiries"] * 100, 2) if prior["inquiries"] else None
        orders = int(current["orders"])
        return BusinessSnapshot(
            period=f"{start.isoformat()}/{end.isoformat()}",
            compare_to=f"{prior_start.isoformat()}/{prior_end.isoformat()}",
            sales=round(current["sales"], 2),
            orders=orders,
            traffic=int(current["inquiries"]),
            conversion_rate=conversion,
            average_order_value=round(current["sales"] / orders, 2) if orders else None,
            sales_change_pct=_pct(current["sales"], prior["sales"]),
            orders_change_pct=_pct(current["orders"], prior["orders"]),
            traffic_change_pct=_pct(current["inquiries"], prior["inquiries"]),
            conversion_change_pct=_pct(conversion or 0, prior_conversion or 0) if prior_conversion else None,
            currency=self.currency,
            alerts=alerts,
            note="traffic counts new buyer inquiries; sales are booked orders",
        )

    async def query_metrics(
        self,
        session: MerchantSessionContext,
        metric: str,
        period: Optional[str] = None,
        granularity: str = "day",
        segment: Optional[str] = None,
    ) -> MetricSeries:
        name = METRIC_ALIASES.get(metric.strip().lower(), metric.strip().lower())
        granularity = granularity if granularity in ("day", "week", "month") else "day"
        if name not in METRICS:
            return MetricSeries(
                metric=metric,
                granularity=granularity,
                note=truncate_display("available: " + ", ".join(METRICS), 140),
            )
        if segment and name not in ("sales", "orders"):
            return MetricSeries(
                metric=name,
                granularity=granularity,
                segment=segment,
                note="segments apply to sales and orders only",
            )
        start, end, _, _ = window(period, self._today())
        with self._scope() as db:
            daily = self._daily(db, name, start, end, segment)
        buckets: Dict[str, float] = {}
        day = start
        while day <= end:
            if granularity == "week":
                key = (day - timedelta(days=day.weekday())).isoformat()
            elif granularity == "month":
                key = day.replace(day=1).isoformat()
            else:
                key = day.isoformat()
            buckets[key] = buckets.get(key, 0.0) + daily.get(day, 0.0)
            day += timedelta(days=1)
        unit = self.currency if METRICS[name][1] == "currency" else "count"
        return MetricSeries(
            metric=name,
            unit=unit,
            granularity=granularity,
            period=f"{start.isoformat()}/{end.isoformat()}",
            segment=segment,
            points=[MetricPoint(date=key, value=round(value, 2)) for key, value in buckets.items()],
        )

    async def get_campaign_performance(
        self, session: MerchantSessionContext, campaign_id: Optional[str] = None
    ) -> List[Campaign]:
        with self._scope() as db:
            query = db.query(MarketingCampaign)
            if campaign_id:
                query = query.filter(MarketingCampaign.id == campaign_id)
            return [self._campaign(row) for row in query.order_by(MarketingCampaign.id).all()]

    @staticmethod
    def _campaign(row: MarketingCampaign) -> Campaign:
        return Campaign(
            campaign_id=row.id,
            name=row.name,
            status=row.status if row.status in ("draft", "active", "paused", "ended") else "draft",
            objective=row.objective,
            channel=row.channel,
            budget=float(row.budget or 0),
            spend=money(row.spend),
            revenue=money(row.revenue),
            currency=row.currency,
            starts=row.starts.isoformat() if row.starts else None,
            ends=row.ends.isoformat() if row.ends else None,
        )

    # -- Catalog --------------------------------------------------------------------

    def all_listings(self) -> List[Listing]:
        with self._scope() as db:
            return [to_listing(row) for row in families(db, ("active", "paused", "draft"))]

    async def search_listings(
        self,
        session: MerchantSessionContext,
        query: str,
        filters: Optional[ListingFilters] = None,
        limit: int = 8,
    ) -> List[Listing]:
        with self._scope() as db:
            rows = families(db, ("active", "paused", "draft"))
            named = {token.strip(",;").casefold() for token in (query or "").split()}
            direct = [row for row in rows if row.id.casefold() in named]
            browse = (query or "").strip().lower() in ("", "*", "all", "everything", "catalog")
            matched = direct or (rows if browse else ranked(rows, query))
            sales = {row.id: row.sales_last_30d for row in rows}
            listings = [to_listing(row) for row in matched]
        if filters is not None:
            if filters.status:
                listings = [item for item in listings if item.status == filters.status]
            if filters.category:
                wanted = filters.category.casefold()
                listings = [item for item in listings if wanted in (item.category or "").casefold()]
            if filters.max_stock is not None:
                listings = [item for item in listings if item.stock <= filters.max_stock]
            if filters.content_quality:
                listings = [item for item in listings if item.content_quality == filters.content_quality]
            if filters.sort == "sales_desc":
                listings.sort(key=lambda item: -sales.get(item.listing_id, 0))
            elif filters.sort == "stock_asc":
                listings.sort(key=lambda item: item.stock)
            elif filters.sort == "price_desc":
                listings.sort(key=lambda item: -item.price)
            elif filters.sort == "price_asc":
                listings.sort(key=lambda item: item.price)
        return listings[:limit]

    async def get_listing(
        self, session: MerchantSessionContext, listing_id: str
    ) -> Optional[ListingDetails]:
        with self._scope() as db:
            row = db.get(CatalogProduct, listing_id)
            return to_listing_details(row) if row is not None else None

    # -- Inventory and order health -----------------------------------------------------

    async def get_inventory_alerts(self, session: MerchantSessionContext) -> List[InventoryAlert]:
        alerts: List[InventoryAlert] = []
        with self._scope() as db:
            rows = (
                db.query(CatalogProduct)
                .filter(CatalogProduct.status == "active")
                .order_by(CatalogProduct.id)
                .all()
            )
            for row in rows:
                if row.variants:
                    continue
                pace = (row.sales_last_30d or 0) / 30
                cover = round(row.stock / pace, 1) if pace else None
                if row.stock <= row.reorder_point:
                    kind = "low_stock"
                elif row.stock > 0 and not row.sales_last_30d and row.stock > max(row.reorder_point, 1) * 3:
                    kind = "slow_mover"
                else:
                    continue
                alerts.append(
                    InventoryAlert(
                        listing_id=row.id,
                        title=row.title,
                        kind=kind,
                        option_values=dict(row.option_values_json or {}),
                        variant_of=row.parent_id,
                        stock=row.stock,
                        threshold=row.reorder_point,
                        days_of_cover=cover,
                        sales_last_30d=row.sales_last_30d,
                        storefront_visible=True,
                    )
                )
        return alerts

    async def get_order_issues(self, session: MerchantSessionContext) -> List[OrderIssue]:
        today = self._today()
        issues: List[OrderIssue] = []
        with self._scope() as db:
            orders = (
                db.query(SalesOrder)
                .filter(SalesOrder.status.notin_(("completed", "cancelled", "delivered")))
                .order_by(SalesOrder.required_ship_date)
                .all()
            )
            for order in orders:
                unshipped = order.status in ("confirmed", "in_production", "quality_check", "ready_to_ship")
                if unshipped and order.required_ship_date and order.required_ship_date < today:
                    issues.append(
                        OrderIssue(
                            issue_id=f"late-{order.order_number}",
                            order_id=order.order_number,
                            kind="delayed",
                            summary=f"Past the required ship date {order.required_ship_date.isoformat()} while {order.status}",
                            opened_at=_as_utc(datetime.combine(order.required_ship_date, datetime.min.time())),
                        )
                    )
                finals = [
                    item
                    for item in order.inspections
                    if item.stage == "pre_shipment"
                ]
                latest: Optional[QualityInspection] = (
                    max(finals, key=lambda item: item.inspected_at) if finals else None
                )
                if latest is not None and latest.result == "failed":
                    issues.append(
                        OrderIssue(
                            issue_id=f"qc-{order.order_number}",
                            order_id=order.order_number,
                            kind="damaged",
                            summary=f"Pre-shipment inspection failed ({len(latest.defects_json or [])} defect types)",
                            opened_at=_as_utc(latest.inspected_at),
                        )
                    )
                for shipment in order.shipments:
                    if shipment.status in ("departed", "arrived") and shipment.eta and shipment.eta < today:
                        issues.append(
                            OrderIssue(
                                issue_id=f"eta-{shipment.shipment_number}",
                                order_id=order.order_number,
                                kind="delayed",
                                summary=f"{shipment.shipment_number} passed its ETA {shipment.eta.isoformat()}",
                            )
                        )
        return issues

    async def _alert_counts(self, session: MerchantSessionContext) -> AlertCounts:
        alerts = await self.get_inventory_alerts(session)
        issues = await self.get_order_issues(session)
        return AlertCounts(
            low_stock=sum(1 for alert in alerts if alert.kind == "low_stock"),
            slow_movers=sum(1 for alert in alerts if alert.kind == "slow_mover"),
            order_issues=len(issues),
            pending_changes=len(self.ledger.pending()),
        )

    # -- Pricing ----------------------------------------------------------------------

    def _pricing(self, row: CatalogProduct) -> PricingContext:
        price = money(row.price) or 0.0
        cost = money(row.unit_cost)
        floor = money(row.min_price)
        basis = "policy" if floor is not None else None
        if floor is None and cost:
            floor, basis = round(cost * 1.1, 2), "cost"
        sales = row.sales_last_30d or 0
        return PricingContext(
            listing_id=row.id,
            current_price=price,
            currency=row.currency,
            unit_cost=cost,
            margin_pct=_margin(price, cost) if cost and price else None,
            min_price=floor,
            min_price_basis=basis,
            max_price=round(price * 1.35, 2) if price else None,
            max_price_delta_pct=self.config.max_price_delta_pct,
            max_promotion_discount_pct=self.config.max_promotion_discount_pct,
            demand_signal="rising" if sales >= 2000 else "falling" if sales == 0 else "steady",
            option_values=dict(row.option_values_json or {}),
        )

    async def get_pricing_context(
        self, session: MerchantSessionContext, listing_id: str
    ) -> Optional[PricingContext]:
        with self._scope() as db:
            row = db.get(CatalogProduct, listing_id)
            if row is None:
                return None
            if row.variants:
                variants = [self._pricing(variant) for variant in row.variants]
                return PricingContext(
                    listing_id=row.id,
                    current_price=min((v.current_price for v in variants), default=money(row.price) or 0.0),
                    currency=row.currency,
                    max_price_delta_pct=self.config.max_price_delta_pct,
                    max_promotion_discount_pct=self.config.max_promotion_discount_pct,
                    variants=variants,
                )
            return self._pricing(row)

    # -- Staged writes ----------------------------------------------------------------

    @staticmethod
    def _require(db: Session, listing_id: str) -> CatalogProduct:
        row = db.get(CatalogProduct, listing_id)
        if row is None:
            raise ChangeNotApplicable(f"no listing {listing_id}")
        return row

    async def stage_listing_update(
        self,
        session: MerchantSessionContext,
        listing_id: str,
        fields: Dict[str, Any],
        note: Optional[str] = None,
    ) -> StagedChange:
        with self._scope() as db:
            row = self._require(db, listing_id)
            if row.parent_id and (shared := set(fields) & set(CONTENT_FIELDS)):
                raise ChangeNotApplicable(
                    f"{', '.join(sorted(shared))} is shared by every variant of {row.parent_id}; "
                    f"stage the edit against {row.parent_id}."
                )
            items = [
                ChangeItem(
                    target=row.id,
                    field=name,
                    before=getattr(row, name) if name in CONTENT_FIELDS else (row.attributes_json or {}).get(name),
                    after=value,
                )
                for name, value in fields.items()
            ]
        return self.ledger.stage(
            kind=ChangeKind.LISTING_UPDATE,
            summary=note or f"Update listing content on {listing_id}",
            items=items,
            actor=session.operator,
        )

    async def stage_price_update(
        self,
        session: MerchantSessionContext,
        items: List[PriceUpdateItem],
        note: Optional[str] = None,
    ) -> StagedChange:
        change_items: List[ChangeItem] = []
        margins: List[Tuple[float, float]] = []
        notes: List[str] = []
        impact = 0.0
        costed = True
        currency: Optional[str] = None
        with self._scope() as db:
            for item in items:
                row = self._require(db, item.listing_id)
                if row.variants:
                    raise ChangeNotApplicable(f"{row.id} is priced per variant")
                context = self._pricing(row)
                if context.min_price is not None and item.new_price < context.min_price:
                    raise ChangeNotApplicable(
                        f"{row.id}: {item.new_price:.2f} is below the floor of {context.min_price:.2f} "
                        f"({context.min_price_basis or 'store rule'})."
                    )
                if context.max_price is not None and item.new_price > context.max_price:
                    raise ChangeNotApplicable(
                        f"{row.id}: {item.new_price:.2f} is above the ceiling of {context.max_price:.2f}."
                    )
                before = context.current_price
                currency = currency or row.currency
                if context.unit_cost is None:
                    costed = False
                else:
                    impact += (item.new_price - before) * (row.sales_last_30d or 0) / 30 * 7
                    pair = (_margin(before, context.unit_cost), _margin(item.new_price, context.unit_cost))
                    margins.append(pair)
                    notes.append(f"{row.id} margin: {pair[0]}% → {pair[1]}% ({pair[1] - pair[0]:+.1f} pts)")
                change_items.append(ChangeItem(target=row.id, field="price", before=before, after=item.new_price))
        return self.ledger.stage(
            kind=ChangeKind.PRICE_UPDATE,
            summary=note or f"Price update for {len(items)} listing(s)",
            items=change_items,
            actor=session.operator,
            currency=currency,
            margin_impact=round(impact, 2) if costed else None,
            margin_before_pct=margins[0][0] if len(margins) == 1 else None,
            margin_after_pct=margins[0][1] if len(margins) == 1 else None,
            guardrail_notes=notes if len(margins) > 1 else None,
        )

    async def stage_inventory_action(
        self,
        session: MerchantSessionContext,
        items: List[InventoryActionItem],
        note: Optional[str] = None,
    ) -> StagedChange:
        change_items: List[ChangeItem] = []
        with self._scope() as db:
            for item in items:
                row = self._require(db, item.listing_id)
                if item.action == "restock":
                    if row.variants:
                        raise ChangeNotApplicable(f"{row.id} is restocked per variant")
                    change_items.append(
                        ChangeItem(target=row.id, field="stock", before=row.stock, after=row.stock + (item.quantity or 0))
                    )
                else:
                    change_items.append(
                        ChangeItem(
                            target=row.id,
                            field="status",
                            before=to_listing(row).status,
                            after="paused" if item.action == "pause" else "active",
                        )
                    )
        return self.ledger.stage(
            kind=ChangeKind.INVENTORY_ACTION,
            summary=note or f"Inventory action for {len(items)} listing(s)",
            items=change_items,
            actor=session.operator,
        )

    async def stage_promotion(
        self, session: MerchantSessionContext, promotion: PromotionDraft
    ) -> StagedChange:
        change_items: List[ChangeItem] = []
        margins: List[Tuple[float, float]] = []
        notes: List[str] = []
        impact = 0.0
        currency: Optional[str] = None
        with self._scope() as db:
            targets: List[CatalogProduct] = []
            for listing_id in promotion.listing_ids:
                row = self._require(db, listing_id)
                for target in row.variants or [row]:
                    if target not in targets:
                        targets.append(target)
            for row in targets:
                price = money(row.price) or 0.0
                currency = currency or row.currency
                promo = round(price * (1 - promotion.discount_pct / 100), 2)
                impact -= price * promotion.discount_pct / 100 * (row.sales_last_30d or 0) / 30 * 7
                cost = money(row.unit_cost)
                if cost and promo > 0:
                    pair = (_margin(price, cost), _margin(promo, cost))
                    margins.append(pair)
                    notes.append(
                        f"{row.id} margin: {pair[0]}% → {pair[1]}% ({pair[1] - pair[0]:+.1f} pts) for the window"
                    )
                change_items.append(ChangeItem(target=row.id, field="promotion_price", before=price, after=promo))
        return self.ledger.stage(
            kind=ChangeKind.PROMOTION,
            summary=f"{promotion.name} ({promotion.discount_pct:.0f}% off, {promotion.starts} to {promotion.ends})",
            items=change_items,
            actor=session.operator,
            currency=currency,
            margin_impact=round(impact, 2),
            margin_before_pct=margins[0][0] if len(margins) == 1 else None,
            margin_after_pct=margins[0][1] if len(margins) == 1 else None,
            guardrail_notes=notes if len(margins) > 1 else None,
        )

    async def stage_campaign(
        self, session: MerchantSessionContext, campaign: CampaignDraft
    ) -> StagedChange:
        with self._scope() as db:
            existing = db.get(MarketingCampaign, campaign.campaign_id) if campaign.campaign_id else None
            if campaign.campaign_id and existing is None:
                raise ChangeNotApplicable(f"no campaign {campaign.campaign_id}")
            target = campaign.campaign_id or campaign.name
            items: List[ChangeItem] = []
            if campaign.budget is not None or existing is None:
                items.append(
                    ChangeItem(
                        target=target,
                        field="budget",
                        before=float(existing.budget) if existing else None,
                        after=campaign.budget,
                    )
                )
            for name in ("audience", "copy_text", "objective", "starts", "ends"):
                value = getattr(campaign, name)
                if value:
                    items.append(ChangeItem(target=target, field=name, before=None, after=value))
        if not items:
            raise ChangeNotApplicable(f"{target}: the draft changes no budget, audience, or copy.")
        return self.ledger.stage(
            kind=ChangeKind.CAMPAIGN,
            summary=f"Campaign draft: {campaign.name}",
            items=items,
            actor=session.operator,
            currency=self.currency,
        )

    async def get_pending_changes(self, session: MerchantSessionContext) -> List[StagedChange]:
        return self.ledger.pending()

    def _live_values(self, db: Session, change: StagedChange) -> Dict[Tuple[str, str], object]:
        live: Dict[Tuple[str, str], object] = {}
        for item in change.items:
            key = (item.target, item.field)
            if change.kind is ChangeKind.CAMPAIGN:
                if item.field == "budget":
                    existing = db.get(MarketingCampaign, item.target)
                    live[key] = float(existing.budget) if existing else None
                continue
            if change.kind is ChangeKind.INVENTORY_ACTION and item.field != "status":
                continue
            row = db.get(CatalogProduct, item.target)
            if row is None:
                live[key] = None
            elif change.kind in (ChangeKind.PRICE_UPDATE, ChangeKind.PROMOTION):
                live[key] = money(row.price)
            elif change.kind is ChangeKind.INVENTORY_ACTION:
                live[key] = to_listing(row).status
            elif item.field in CONTENT_FIELDS:
                live[key] = getattr(row, item.field)
            else:
                live[key] = (row.attributes_json or {}).get(item.field)
        return live

    def _write(self, db: Session, change: StagedChange) -> None:
        if change.kind is ChangeKind.CAMPAIGN:
            target = change.items[0].target
            row = db.get(MarketingCampaign, target)
            if row is None:
                row = MarketingCampaign(
                    id=f"cmp-{uuid4().hex[:8]}",
                    name=target[:80],
                    status="draft",
                    budget=0,
                    currency=self.currency,
                )
                db.add(row)
            for item in change.items:
                if item.field == "budget" and item.after is not None:
                    row.budget = Decimal(str(item.after))
                elif item.field in ("starts", "ends"):
                    setattr(row, item.field, date.fromisoformat(str(item.after)[:10]))
                elif item.field in ("audience", "copy_text", "objective"):
                    setattr(row, item.field, str(item.after))
            return
        if change.kind is ChangeKind.PROMOTION:
            discount = None
            listing_ids: List[str] = []
            for item in change.items:
                listing_ids.append(item.target)
                if discount is None and item.before:
                    discount = round((1 - float(item.after) / float(item.before)) * 100, 2)
            starts, ends = self._promotion_window(change.summary)
            db.add(
                CatalogPromotion(
                    id=f"promo-{uuid4().hex[:8]}",
                    name=change.summary[:80],
                    listing_ids_json=listing_ids,
                    discount_pct=Decimal(str(discount or 0)),
                    starts=starts,
                    ends=ends,
                    status="scheduled",
                    change_id=change.change_id,
                )
            )
            return
        for item in change.items:
            row = self._require(db, item.target)
            if item.field == "price":
                row.price = Decimal(str(item.after))
            elif item.field == "stock":
                delta = int(item.after) - int(item.before or 0)
                row.stock = max(row.stock + delta, 0)
            elif item.field == "status":
                row.status = "paused" if item.after == "paused" else "active"
            elif item.field in CONTENT_FIELDS:
                setattr(row, item.field, item.after)
            else:
                attributes = dict(row.attributes_json or {})
                attributes[item.field] = item.after
                row.attributes_json = attributes
            row.version += 1

    def _promotion_window(self, summary: str) -> Tuple[date, date]:
        today = self._today()
        try:
            inside = summary.rsplit("(", 1)[1].rstrip(")")
            starts_text, ends_text = inside.split(",", 1)[1].strip().split(" to ")
            return date.fromisoformat(starts_text.strip()[:10]), date.fromisoformat(ends_text.strip()[:10])
        except (IndexError, ValueError):
            return today, today + timedelta(days=7)

    async def apply_change(self, session: MerchantSessionContext, change_id: str) -> StagedChange:
        with self._scope() as db:
            row, change = self.ledger.require_staged(db, change_id, "apply")
            violations = check_guardrails(change.kind, change.items, self.config)
            if violations:
                raise GuardrailViolation(violations)
            if drifted := check_drift(change, self._live_values(db, change)):
                raise ChangeNotApplicable(
                    f"change {change_id} was not applied: {'; '.join(drifted)}. Discard it and "
                    "stage it again from the current values"
                )
            try:
                self._write(db, change)
                applied = self.ledger.mark_applied(db, row, change, session.operator)
                db.commit()
            except Exception:
                db.rollback()
                raise
            return applied

    async def discard_change(
        self,
        session: MerchantSessionContext,
        change_id: str,
        actor_kind: ActorKind = ActorKind.OPERATOR,
    ) -> StagedChange:
        return self.ledger.discard(change_id, session.operator, actor_kind)

    # -- Analysis -----------------------------------------------------------------------

    async def get_analysis_schema(self, session: MerchantSessionContext) -> Optional[str]:
        return (
            "daily_metrics(date TEXT, sales REAL, orders INTEGER, inquiries INTEGER, "
            "quotations_sent INTEGER, collected REAL) — last 180 days, reporting currency; "
            "listings(listing_id TEXT, parent_id TEXT, title TEXT, category TEXT, status TEXT, "
            "price REAL, unit_cost REAL, moq INTEGER, stock INTEGER, sales_last_30d INTEGER); "
            "orders(order_number TEXT, status TEXT, currency TEXT, total REAL, created_at TEXT, "
            "required_ship_date TEXT, fulfillment_mode TEXT); "
            "order_lines(order_number TEXT, sku TEXT, product TEXT, quantity REAL, unit_price REAL, amount REAL); "
            "opportunities(opportunity_id TEXT, stage TEXT, source TEXT, estimated_value REAL, "
            "currency TEXT, created_at TEXT); "
            "campaigns(campaign_id TEXT, name TEXT, status TEXT, channel TEXT, budget REAL, "
            "spend REAL, revenue REAL, starts TEXT, ends TEXT)"
        )

    def _snapshot_rows(self) -> Dict[str, List[tuple]]:
        today = self._today()
        start = today - timedelta(days=HISTORY_DAYS - 1)
        with self._scope() as db:
            daily = {m: self._daily(db, m, start, today) for m in ("sales", "orders", "inquiries", "quotations_sent", "collected")}
            days = [start + timedelta(days=offset) for offset in range(HISTORY_DAYS)]
            tables: Dict[str, List[tuple]] = {
                "daily_metrics": [
                    (
                        day.isoformat(),
                        daily["sales"].get(day, 0.0),
                        int(daily["orders"].get(day, 0)),
                        int(daily["inquiries"].get(day, 0)),
                        int(daily["quotations_sent"].get(day, 0)),
                        daily["collected"].get(day, 0.0),
                    )
                    for day in days
                ],
                "listings": [
                    (
                        row.id,
                        row.parent_id,
                        row.title,
                        row.category,
                        row.status,
                        money(row.price),
                        money(row.unit_cost),
                        row.moq,
                        row.stock,
                        row.sales_last_30d,
                    )
                    for row in db.query(CatalogProduct).order_by(CatalogProduct.id).all()
                ],
                "campaigns": [
                    (
                        row.id,
                        row.name,
                        row.status,
                        row.channel,
                        money(row.budget),
                        money(row.spend),
                        money(row.revenue),
                        row.starts.isoformat() if row.starts else None,
                        row.ends.isoformat() if row.ends else None,
                    )
                    for row in db.query(MarketingCampaign).all()
                ],
                "opportunities": [
                    (
                        str(row.id),
                        row.stage,
                        row.source,
                        money(row.estimated_value),
                        row.currency,
                        row.created_at.isoformat(),
                    )
                    for row in db.query(SalesOpportunity).all()
                ],
            }
            orders = db.query(SalesOrder).all()
            tables["orders"] = [
                (
                    row.order_number,
                    row.status,
                    row.currency,
                    float(row.total),
                    row.created_at.isoformat(),
                    row.required_ship_date.isoformat() if row.required_ship_date else None,
                    row.fulfillment_mode,
                )
                for row in orders
            ]
            tables["order_lines"] = [
                (
                    row.order_number,
                    line.get("sku"),
                    line.get("product"),
                    float(line.get("quantity") or 0),
                    float(line.get("unit_price") or 0),
                    float(line.get("amount") or 0),
                )
                for row in orders
                for line in row.line_items_json or []
            ]
        return tables

    def _analysis_connection(self, tables: Dict[str, List[tuple]]) -> sqlite3.Connection:
        conn = sqlite3.connect(":memory:")
        schemas = {
            "daily_metrics": "date TEXT, sales REAL, orders INTEGER, inquiries INTEGER, quotations_sent INTEGER, collected REAL",
            "listings": "listing_id TEXT, parent_id TEXT, title TEXT, category TEXT, status TEXT, price REAL, unit_cost REAL, moq INTEGER, stock INTEGER, sales_last_30d INTEGER",
            "campaigns": "campaign_id TEXT, name TEXT, status TEXT, channel TEXT, budget REAL, spend REAL, revenue REAL, starts TEXT, ends TEXT",
            "opportunities": "opportunity_id TEXT, stage TEXT, source TEXT, estimated_value REAL, currency TEXT, created_at TEXT",
            "orders": "order_number TEXT, status TEXT, currency TEXT, total REAL, created_at TEXT, required_ship_date TEXT, fulfillment_mode TEXT",
            "order_lines": "order_number TEXT, sku TEXT, product TEXT, quantity REAL, unit_price REAL, amount REAL",
        }
        for name, columns in schemas.items():
            conn.execute(f"CREATE TABLE {name} ({columns})")
            rows = tables.get(name) or []
            if rows:
                conn.executemany(
                    f"INSERT INTO {name} VALUES ({', '.join('?' for _ in rows[0])})", rows
                )
        conn.commit()
        read_actions = {sqlite3.SQLITE_SELECT, sqlite3.SQLITE_READ, sqlite3.SQLITE_FUNCTION}
        recursive = getattr(sqlite3, "SQLITE_RECURSIVE", None)
        if recursive is not None:
            read_actions.add(recursive)

        def read_only(action: int, *args: object) -> int:
            return sqlite3.SQLITE_OK if action in read_actions else sqlite3.SQLITE_DENY

        conn.set_authorizer(read_only)
        conn.set_progress_handler(lambda: 1, 5_000_000)
        return conn

    async def execute_analysis_query(
        self, session: MerchantSessionContext, sql: str
    ) -> Optional[AnalysisTable]:
        if session.merchant_id != MERCHANT_ID:
            raise PermissionError("analysis queries are scoped to this organization")
        if reason := check_analysis_sql(sql):
            raise ValueError(f"query refused: {reason}")
        tables = self._snapshot_rows()
        cap = self.config.max_analysis_rows

        def run() -> Tuple[List[str], List[Any]]:
            conn = self._analysis_connection(tables)
            try:
                cursor = conn.execute(sql)
                columns = [description[0] for description in cursor.description or []]
                return columns, cursor.fetchmany(cap + 1)
            finally:
                conn.close()

        try:
            columns, fetched = await asyncio.to_thread(run)
        except sqlite3.Error as error:
            raise ValueError(str(error)) from error
        truncated = len(fetched) > cap
        rows = [list(row) for row in fetched[:cap]]
        return AnalysisTable(
            columns=columns,
            rows=rows,
            row_count=len(rows),
            truncated=truncated,
            note="row-capped" if truncated else None,
        )

    # -- Context ------------------------------------------------------------------------

    async def get_merchant_context(self, session: MerchantSessionContext) -> Optional[Dict[str, Any]]:
        counts = await self._alert_counts(session)
        return {
            "business": "B2B export manufacturer and trading desk",
            "reporting_currency": self.currency,
            "alerts": counts.model_dump(),
            "limitations": [
                DataLimitation(source="returns", note="Return reasons are not recorded in B-agent.").model_dump(),
                DataLimitation(
                    source="traffic", note="Traffic is new buyer inquiries, not website visits."
                ).model_dump(),
            ],
        }

