"""``StorefrontBackend`` over B-agent: the buyer assistant's catalog, RFQ basket, trade
terms and the customer's own fulfillment orders.

There is no checkout. The basket is a request for quotation: ``checkout_handoff`` points
the card at the RFQ action, and :mod:`app.commerce.rfq` turns the basket into an
opportunity with a draft quotation for the sales team to price and approve.
"""

import re
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional

from shopping_agent import (
    Cart,
    CartItem,
    CheckoutHandoff,
    Disclosure,
    DisclosureRow,
    FulfillmentOption,
    Order,
    OrderItem,
    OrderStatus,
    Policy,
    Product,
    ProductDetails,
    SearchFilters,
    ShoppingSessionContext,
    StorefrontBackend,
    Unavailable,
    UserPreferences,
)

from app.commerce.catalog import families, money, ranked, to_details, to_product, SELLABLE_STATUSES
from app.commerce.stores import SessionScope, utcnow
from app.models.database import (
    CatalogProduct,
    CommerceCartLine,
    Customer,
    SalesOpportunity,
    SalesOrder,
    TradeTerm,
)


RFQ_HANDOFF_URL = "#submit-rfq"

_ORDER_STATUS = {
    "confirmed": OrderStatus.PROCESSING,
    "in_production": OrderStatus.PROCESSING,
    "quality_check": OrderStatus.PROCESSING,
    "ready_to_ship": OrderStatus.PROCESSING,
    "shipped": OrderStatus.SHIPPED,
    "delivered": OrderStatus.DELIVERED,
    "completed": OrderStatus.DELIVERED,
    "cancelled": OrderStatus.CANCELLED,
}


_STOPWORDS = frozenset(
    "a an and are be can do does for from how i if in is it me my of on or our please the "
    "there to u we what when where which with you your".split()
)
_WORD = re.compile(r"[\w\u4e00-\u9fff/.%]+", re.UNICODE)


def _words(text: str) -> set:
    return {word for word in _WORD.findall((text or "").casefold()) if word not in _STOPWORDS}


def rank_policies(policies: List[Policy], query: str) -> List[Policy]:
    """Every version of each source whose passages share at least half of the query's
    words, best-matching source first; the terms gate then passes the version in force."""
    wanted = _words(query)
    if not wanted:
        return list(policies)
    best: Dict[str, float] = {}
    for policy in policies:
        overlap = len(wanted & _words(f"{policy.title} {policy.category or ''} {policy.content}"))
        key = policy.source_id or policy.policy_id
        best[key] = max(best.get(key, 0.0), overlap / len(wanted))
    matched = {key: value for key, value in best.items() if value >= 0.5}
    ranked = sorted(matched, key=lambda key: -matched[key])
    order = {key: index for index, key in enumerate(ranked)}
    return sorted(
        (policy for policy in policies if (policy.source_id or policy.policy_id) in order),
        key=lambda policy: order[policy.source_id or policy.policy_id],
    )


def customer_subject(customer_id: int) -> str:
    return f"customer:{customer_id}"


def customer_id_of(session: ShoppingSessionContext) -> int:
    prefix, _, value = session.user_id.partition(":")
    if prefix != "customer" or not value.isdigit():
        raise PermissionError("Buyer sessions are bound to one customer")
    return int(value)


def _as_utc(value: Optional[datetime]) -> Optional[datetime]:
    return value.replace(tzinfo=timezone.utc) if value is not None else None


class BAgentStorefront(StorefrontBackend):
    def __init__(self, scope: SessionScope) -> None:
        self._scope = scope

    def _customer_id(self, session: ShoppingSessionContext) -> int:
        return customer_id_of(session)

    # -- Catalog ------------------------------------------------------------------

    async def search_products(
        self,
        session: ShoppingSessionContext,
        query: str,
        filters: Optional[SearchFilters] = None,
        limit: int = 8,
    ) -> List[Product]:
        with self._scope() as db:
            rows = families(db, SELLABLE_STATUSES)
            if filters and filters.category:
                wanted = filters.category.casefold()
                rows = [row for row in rows if (row.category or "").casefold() == wanted]
            products = [(row, to_product(row)) for row in ranked(rows, query)]
            if filters:
                if filters.min_price is not None:
                    products = [p for p in products if p[1].price >= filters.min_price]
                if filters.max_price is not None:
                    products = [p for p in products if p[1].price <= filters.max_price]
                for name, value in (filters.attributes or {}).items():
                    wanted = str(value).casefold()
                    products = [
                        p for p in products if wanted in str(p[1].attributes.get(name, "")).casefold()
                    ]
                if filters.sort == "price_asc":
                    products.sort(key=lambda p: p[1].price)
                elif filters.sort == "price_desc":
                    products.sort(key=lambda p: -p[1].price)
            return [product for _, product in products[:limit]]

    async def get_product_details(
        self, session: ShoppingSessionContext, product_id: str
    ) -> Optional[ProductDetails]:
        with self._scope() as db:
            row = db.get(CatalogProduct, product_id)
            if row is None or row.status not in SELLABLE_STATUSES:
                return None
            return to_details(row)

    # -- RFQ basket ---------------------------------------------------------------

    def _cart(self, db, customer_id: int) -> Cart:
        lines = (
            db.query(CommerceCartLine)
            .filter(CommerceCartLine.customer_id == customer_id)
            .order_by(CommerceCartLine.id)
            .all()
        )
        items = []
        currency = "USD"
        for line in lines:
            product = db.get(CatalogProduct, line.product_id)
            if product is None:
                continue
            currency = product.currency
            items.append(
                CartItem(
                    product_id=product.id,
                    title=product.title,
                    price=money(product.price) or 0.0,
                    quantity=line.quantity,
                    image_url=product.image_url,
                    option_values=dict(product.option_values_json or {}),
                    variant_of=product.parent_id,
                )
            )
        return Cart(items=items, currency=currency)

    async def get_cart(self, session: ShoppingSessionContext) -> Cart:
        with self._scope() as db:
            return self._cart(db, self._customer_id(session))

    async def add_to_cart(
        self, session: ShoppingSessionContext, product_id: str, quantity: int
    ) -> Cart:
        customer_id = self._customer_id(session)
        with self._scope() as db:
            product = db.get(CatalogProduct, product_id)
            if product is None or product.status not in SELLABLE_STATUSES:
                raise Unavailable(f"{product_id} is not offered for quotation")
            if product.variants:
                raise Unavailable(f"{product_id} is quoted per variant")
            basket = self._cart(db, customer_id)
            if basket.items and basket.currency != product.currency:
                raise Unavailable(
                    f"{product_id} is priced in {product.currency}; the RFQ is in {basket.currency}"
                )
            line = (
                db.query(CommerceCartLine)
                .filter(
                    CommerceCartLine.customer_id == customer_id,
                    CommerceCartLine.product_id == product_id,
                )
                .one_or_none()
            )
            if line is None:
                db.add(CommerceCartLine(customer_id=customer_id, product_id=product_id, quantity=quantity))
            else:
                line.quantity += quantity
            db.commit()
            return self._cart(db, customer_id)

    async def update_cart_item(
        self, session: ShoppingSessionContext, product_id: str, quantity: int
    ) -> Cart:
        customer_id = self._customer_id(session)
        with self._scope() as db:
            line = (
                db.query(CommerceCartLine)
                .filter(
                    CommerceCartLine.customer_id == customer_id,
                    CommerceCartLine.product_id == product_id,
                )
                .one_or_none()
            )
            if line is not None:
                line.quantity = quantity
                db.commit()
            return self._cart(db, customer_id)

    async def remove_from_cart(self, session: ShoppingSessionContext, product_id: str) -> Cart:
        customer_id = self._customer_id(session)
        with self._scope() as db:
            db.query(CommerceCartLine).filter(
                CommerceCartLine.customer_id == customer_id,
                CommerceCartLine.product_id == product_id,
            ).delete()
            db.commit()
            return self._cart(db, customer_id)

    async def checkout_handoff(
        self, session: ShoppingSessionContext, cart: Cart
    ) -> List[CheckoutHandoff]:
        return [CheckoutHandoff(url=RFQ_HANDOFF_URL, label="Submit RFQ")] if cart.items else []

    # -- Customer context ---------------------------------------------------------

    async def get_preferences(self, session: ShoppingSessionContext) -> UserPreferences:
        with self._scope() as db:
            customer = db.get(Customer, self._customer_id(session))
            if customer is None:
                return UserPreferences(user_id=session.user_id)
            fields = customer.custom_fields or {}
            preferences = {
                key: str(fields[key])
                for key in ("preferred_incoterm", "preferred_currency", "destination_port")
                if fields.get(key)
            }
            return UserPreferences(
                user_id=session.user_id,
                display_name=customer.company_name or customer.username,
                default_location=customer.country,
                preferences=preferences,
            )

    async def get_account_context(self, session: ShoppingSessionContext) -> Optional[Dict[str, Any]]:
        customer_id = self._customer_id(session)
        with self._scope() as db:
            open_rfqs = (
                db.query(SalesOpportunity)
                .filter(
                    SalesOpportunity.customer_id == customer_id,
                    SalesOpportunity.stage.in_(("inquiry", "qualified", "quoting", "negotiation")),
                )
                .count()
            )
            open_orders = (
                db.query(SalesOrder)
                .filter(
                    SalesOrder.customer_id == customer_id,
                    SalesOrder.status.notin_(("completed", "cancelled")),
                )
                .count()
            )
            return {
                "account_type": "B2B buyer",
                "open_quotation_requests": open_rfqs,
                "open_orders": open_orders,
                "basket_is_rfq": True,
            }

    # -- Orders and terms ---------------------------------------------------------

    @staticmethod
    def _order(row: SalesOrder) -> Order:
        status = _ORDER_STATUS.get(row.status, OrderStatus.PROCESSING)
        today = utcnow().date()
        if (
            status is OrderStatus.PROCESSING
            and row.required_ship_date is not None
            and row.required_ship_date < today
        ):
            status = OrderStatus.DELAYED
        eta = next((s.eta for s in reversed(row.shipments) if s.eta), None)
        items = []
        for line in row.line_items_json or []:
            try:
                quantity = max(int(float(line.get("quantity") or 0)), 1)
            except (TypeError, ValueError):
                quantity = 1
            items.append(
                OrderItem(
                    product_id=str(line.get("sku") or line.get("product")),
                    title=str(line.get("product")),
                    quantity=quantity,
                    price=float(line.get("unit_price") or 0),
                )
            )
        return Order(
            order_id=row.order_number,
            status=status,
            placed_at=_as_utc(row.created_at),
            items=items,
            total=float(row.total),
            currency=row.currency,
            estimated_delivery=(
                f"ETA {eta.isoformat()}"
                if eta
                else (f"ships by {row.required_ship_date.isoformat()}" if row.required_ship_date else None)
            ),
        )

    async def get_orders(self, session: ShoppingSessionContext, limit: int = 5) -> List[Order]:
        with self._scope() as db:
            rows = (
                db.query(SalesOrder)
                .filter(SalesOrder.customer_id == self._customer_id(session))
                .order_by(SalesOrder.created_at.desc())
                .limit(limit)
                .all()
            )
            return [self._order(row) for row in rows]

    async def get_order(self, session: ShoppingSessionContext, order_id: str) -> Optional[Order]:
        with self._scope() as db:
            row = (
                db.query(SalesOrder)
                .filter(
                    SalesOrder.customer_id == self._customer_id(session),
                    SalesOrder.order_number == order_id,
                )
                .one_or_none()
            )
            return self._order(row) if row is not None else None

    async def search_policies(self, session: ShoppingSessionContext, query: str) -> List[Policy]:
        with self._scope() as db:
            rows = db.query(TradeTerm).order_by(TradeTerm.source_id, TradeTerm.effective_at).all()
            policies = [
                Policy(
                    policy_id=row.id,
                    title=row.title,
                    category=row.category,
                    content=row.content,
                    source_id=row.source_id,
                    version=row.version,
                    effective_at=_as_utc(row.effective_at),
                    expires_at=_as_utc(row.expires_at),
                )
                for row in rows
            ]
        return rank_policies(policies, query)

    # -- Compliance facts ---------------------------------------------------------

    async def get_disclosure(
        self, session: ShoppingSessionContext, product_id: str
    ) -> Optional[Disclosure]:
        with self._scope() as db:
            row = db.get(CatalogProduct, product_id)
            if row is None:
                return None
            source = row
            if row.parent_id:
                source = db.get(CatalogProduct, row.parent_id) or row
            attributes = {**(source.attributes_json or {}), **(row.attributes_json or {})}
            labels = (
                ("hs_code", "HS code"),
                ("origin", "Country of origin"),
                ("certifications", "Certifications"),
                ("material", "Material"),
                ("packaging", "Export packaging"),
            )
            rows = [
                DisclosureRow(label=label, value=str(attributes[key]))
                for key, label in labels
                if attributes.get(key)
            ]
            rows.append(DisclosureRow(label="Minimum order", value=f"{source.moq} {attributes.get('unit', 'pcs')}"))
            if source.lead_time_days:
                rows.append(
                    DisclosureRow(
                        label="Production lead time",
                        value=f"{source.lead_time_days} days",
                        note="after deposit and artwork approval",
                    )
                )
            return Disclosure(
                title=f"Trade facts · {row.title}",
                product_id=row.id,
                rows=rows,
                sources=["B-agent product master data"],
                footnotes=["Final prices, duties and freight are confirmed on the quotation."],
            )

    async def get_fulfillment_options(
        self, session: ShoppingSessionContext, product_ids: List[str]
    ) -> List[FulfillmentOption]:
        options: List[FulfillmentOption] = []
        with self._scope() as db:
            for product_id in product_ids[:20]:
                row = db.get(CatalogProduct, product_id)
                if row is None:
                    continue
                source = db.get(CatalogProduct, row.parent_id) if row.parent_id else row
                attributes = source.attributes_json or {}
                lead = source.lead_time_days or 30
                port = attributes.get("port_of_loading")
                options.append(
                    FulfillmentOption(
                        method="shipping",
                        eta=f"sea freight, ready to ship {lead} days after deposit",
                        location=port,
                    )
                )
                options.append(
                    FulfillmentOption(
                        method="shipping",
                        eta="sample by air express in 5-7 days",
                        location=port,
                    )
                )
        return options
