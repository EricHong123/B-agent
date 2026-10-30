# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The telecom example's ``StorefrontBackend`` over the fixtures in ``data/``. Plans,
devices, home internet, and add-ons are ordinary products; a ``min_data_gb`` attribute
filter is enforced as a hard constraint. On top of the interface it computes the account
context (contract clock, upgrade eligibility, trade-in estimate, bill) and the plan
disclosures from seeded billing state, and it holds the one-plan, one-internet-service
cart rule.
"""

from __future__ import annotations

from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from demo_common.storefront_fixtures import (
    SessionCarts,
    cited_evidence,
    example_data_dir,
    find_order,
    find_product,
    keyword_score,
    load_catalog,
    load_help_synonyms,
    load_orders,
    load_policies,
    load_users,
    matches_attribute_filters,
    newest_orders,
    orders_for,
    preferences_of,
    rank_products,
    search_help,
    summary_of,
    unavailable_detail,
    within_price_and_rating,
)
from shopping_agent import (
    Cart,
    Disclosure,
    DisclosureRow,
    FulfillmentOption,
    Order,
    Policy,
    Product,
    ProductDetails,
    SearchFilters,
    ShoppingSessionContext,
    StorefrontBackend,
    Unavailable,
    UserPreferences,
)

DATA_DIR = example_data_dir(__file__)

# A customer has one line in each of these categories: adding another replaces it.
_SINGLE_LINE_CATEGORIES = {"plans", "home-internet"}
_MIN_DATA_GB = "min_data_gb"

# Figures the policies in data/policies.json state, held once so the account context
# and the policy text agree: trade-in credit by device tier, the contract clock, the
# trade-in quote window, and the per-line network surcharge on every plan disclosure.
_TRADE_IN_CREDITS = {"A": 350, "B": 200, "C": 80}
_EARLY_UPGRADE_MONTH = 22
_CONTRACT_MONTHS = 24
_TRADE_IN_QUOTE_DAYS = 30
_NETWORK_SURCHARGE_USD = 1.45
# Recent top-up spend is priced from this catalog record.
_TOP_UP_PRODUCT_ID = "AM-ADD-401"

_SEARCH_WEIGHTS = {
    "title": 3.0,
    "brand": 2.0,
    "category": 2.5,
    "attributes": 1.5,
    "description": 1.0,
}
# A small synonym map so natural demo queries land without a real search engine.
_SYNONYMS: dict[str, list[str]] = {
    "phone": ["device", "flip", "smartphone"],
    "cell": ["phone", "device"],
    "cellphone": ["phone", "device"],
    "mobile": ["plan", "phone"],
    "smartphone": ["phone", "device"],
    "internet": ["fiber", "home"],
    "wifi": ["fiber", "internet", "mesh"],
    "broadband": ["fiber", "internet"],
    "upgrade": ["device", "phone", "flip"],
    "tradein": ["trade"],
    "esim": ["plan", "line"],
    "sim": ["plan", "line"],
    "roaming": ["roaming", "day", "pass"],
    "abroad": ["roaming", "pass", "day"],
    "travel": ["roaming", "pass", "day"],
    "family": ["line", "extra"],
    "kid": ["line", "phone"],
    "tablet": ["tablet"],
    "watch": ["smartwatch"],
    "overage": ["top", "up", "data"],
    "tether": ["hotspot"],
    "tethering": ["hotspot"],
    "stream": ["streaming", "video"],
    "gig": ["fiber", "gbps"],
}


def _min_data_gb(filters: SearchFilters) -> float | None:
    raw = str(filters.attributes.get(_MIN_DATA_GB, "")).strip()
    try:
        return float(raw) if raw else None
    except ValueError:
        return None


def _meets_data_need(product: ProductDetails, need_gb: float) -> bool:
    """Products without an allowance are not data-bound; "unlimited" always qualifies."""
    allowance = product.attributes.get("data_allowance_gb")
    if allowance is None:
        return True
    if allowance.strip().lower() == "unlimited":
        return True
    try:
        return float(allowance) >= need_gb
    except ValueError:
        return True


def _months_between(start: date, on: date) -> int:
    months = (on.year - start.year) * 12 + (on.month - start.month)
    if on.day < start.day:
        months -= 1
    return max(months, 0)


def _add_months(start: date, months: int) -> date:
    year = start.year + (start.month - 1 + months) // 12
    month = (start.month - 1 + months) % 12 + 1
    return date(year, month, min(start.day, 28))


class MockTelecom(StorefrontBackend):
    def __init__(self, data_dir: Path = DATA_DIR) -> None:
        catalog, self.products, self.variants = load_catalog(data_dir)
        self.store_name: str = catalog.get("store_name", "the store")
        self._users = load_users(data_dir)
        self._orders = load_orders(data_dir)
        self._policies = load_policies(data_dir)
        self._help_synonyms = load_help_synonyms(data_dir)
        self._carts = SessionCarts()

        # Seeded billing state. The contract start is anchored to boot so the account is
        # always in month 23 of 24; everything else is derived from it in
        # get_account_context.
        self._accounts: dict[str, dict[str, Any] | None] = {
            "demo-user": {
                "plan_id": "AM-PLAN-101",
                "contract_start": _add_months(date.today(), -(_CONTRACT_MONTHS - 1)),
                "device_id": "AM-DEV-201",
                "recent_usage": {
                    "avg_gb_per_month_last_3": 14.2,
                    "cycles_gb_last_3": [13.4, 14.9, 14.3],
                    "top_ups_last_3_months": 4,
                    "note": "hit the 5GB allowance in each of the last 3 cycles",
                },
            },
            "demo-user-2": None,  # new prospect: no account yet
        }

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    def _searchable_text(self, product: ProductDetails) -> dict[str, str]:
        return {
            "title": product.title,
            "brand": product.brand or "",
            "category": product.category or "",
            "attributes": " ".join(f"{k} {v}" for k, v in product.attributes.items()),
            "description": f"{product.short_description or ''} {product.long_description or ''}",
        }

    def _score(self, product: ProductDetails, query_tokens: list[str]) -> float:
        return keyword_score(
            self._searchable_text(product), _SEARCH_WEIGHTS, query_tokens, _SYNONYMS
        )

    @staticmethod
    def _hard_filter(product: ProductDetails, filters: SearchFilters) -> bool:
        if not within_price_and_rating(product, filters):
            return False
        need = _min_data_gb(filters)
        return need is None or _meets_data_need(product, need)

    @staticmethod
    def _soft_filter(product: ProductDetails, filters: SearchFilters) -> bool:
        return matches_attribute_filters(product, filters, ignore=frozenset({_MIN_DATA_GB}))

    async def search_products(
        self,
        session: ShoppingSessionContext,
        query: str,
        filters: SearchFilters | None = None,
        limit: int = 8,
    ) -> list[Product]:
        del session
        ranked = rank_products(
            self.products.values(),
            query,
            filters,
            limit,
            score=self._score,
            hard_filter=self._hard_filter,
            soft_filter=self._soft_filter,
        )
        return [summary_of(product) for product in ranked]

    def product(self, product_id: str) -> ProductDetails | None:
        return find_product(self.products, self.variants, product_id)

    async def get_product_details(
        self, session: ShoppingSessionContext, product_id: str
    ) -> ProductDetails | None:
        del session
        return self.product(product_id)

    # ------------------------------------------------------------------
    # Cart
    # ------------------------------------------------------------------

    async def get_cart(self, session: ShoppingSessionContext) -> Cart:
        return self._carts.cart(session.session_id)

    def _category_of(self, product_id: str) -> str:
        product = self.product(product_id)
        return (product.category or "") if product else ""

    async def add_to_cart(
        self, session: ShoppingSessionContext, product_id: str, quantity: int
    ) -> Cart:
        product = self.product(product_id)
        if product is None or product.has_options:
            raise KeyError(product_id)
        if not product.in_stock:
            family = self.product(product.variant_of) if product.variant_of else None
            raise Unavailable(unavailable_detail(product, family))
        lines = self._carts.lines(session.session_id)
        if product.category in _SINGLE_LINE_CATEGORIES:
            # A second plan or internet service is a change of service, not a second line.
            for other in [pid for pid in lines if self._category_of(pid) == product.category]:
                lines.pop(other)
            quantity = 1
        elif existing := lines.get(product_id):
            quantity += existing.quantity
        return self._carts.put(session.session_id, product, quantity)

    async def update_cart_item(
        self, session: ShoppingSessionContext, product_id: str, quantity: int
    ) -> Cart:
        if self._category_of(product_id) in _SINGLE_LINE_CATEGORIES:
            quantity = min(quantity, 1)
        return self._carts.set_quantity(session.session_id, product_id, quantity)

    async def remove_from_cart(self, session: ShoppingSessionContext, product_id: str) -> Cart:
        return self._carts.remove(session.session_id, product_id)

    def reset_session(self, session_id: str) -> None:
        self._carts.reset(session_id)

    # ------------------------------------------------------------------
    # Customer, account, orders, help content, fulfillment
    # ------------------------------------------------------------------

    async def get_preferences(self, session: ShoppingSessionContext) -> UserPreferences:
        return preferences_of(self._users, session.user_id)

    async def get_account_context(
        self, session: ShoppingSessionContext, on: date | None = None
    ) -> dict[str, Any] | None:
        """The subscriber's account as of ``on`` (today unless a test says otherwise):
        eligibility, trade-in, and the bill are computed from the contract clock and the
        catalog."""
        account = self._accounts.get(session.user_id)
        if not account:
            return None
        on = on or date.today()

        plan = self.products.get(account["plan_id"])
        device = self.products.get(account["device_id"])
        start: date = account["contract_start"]
        month = _months_between(start, on)
        early_date = _add_months(start, _EARLY_UPGRADE_MONTH)
        outright_date = _add_months(start, _CONTRACT_MONTHS)

        if month >= _CONTRACT_MONTHS:
            eligibility = {
                "eligible": True,
                "kind": "outright",
                "reason": f"device agreement completed (month {month} of {_CONTRACT_MONTHS})",
            }
        elif month >= _EARLY_UPGRADE_MONTH:
            eligibility = {
                "eligible": True,
                "kind": "early-with-trade-in",
                "reason": (
                    f"month {month} of {_CONTRACT_MONTHS}; early upgrade available with a "
                    f"qualifying trade-in; outright upgrade on {outright_date.isoformat()}"
                ),
            }
        else:
            eligibility = {
                "eligible": False,
                "kind": "not-yet",
                "reason": (
                    f"month {month} of {_CONTRACT_MONTHS}; early upgrade with trade-in opens "
                    f"on {early_date.isoformat()}"
                ),
            }

        trade_in = None
        if device is not None:
            tier = device.attributes.get("trade_in_tier", "C")
            # The estimate carries the policy's condition and validity terms.
            trade_in = {
                "device": device.title,
                "tier": tier,
                "estimated_credit_usd": _TRADE_IN_CREDITS.get(tier, 0),
                "condition_assumption": (
                    "assumes qualifying condition: powers on, screen intact, "
                    "activation lock removed"
                ),
                "quote_valid_through": (on + timedelta(days=_TRADE_IN_QUOTE_DAYS)).isoformat(),
                "note": (
                    "applied as 24 monthly bill credits; estimate re-runs on arrival "
                    "if the device condition differs"
                ),
            }

        installments_remaining = max(_CONTRACT_MONTHS - month, 0)
        # Plan price plus the device installment (24 payments, cents rounded half up as
        # in the catalog's own installment strings) while any remain.
        installment = 0.0
        if device is not None and installments_remaining > 0:
            cents = Decimal(str(device.price)) / _CONTRACT_MONTHS
            installment = float(cents.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))
        monthly_bill = round((plan.price if plan else 0.0) + installment, 2)

        usage = dict(account["recent_usage"])
        top_up = self.products.get(_TOP_UP_PRODUCT_ID)
        if top_up is not None:
            usage["top_up_spend_usd_last_3_months"] = round(
                usage.get("top_ups_last_3_months", 0) * top_up.price, 2
            )

        return {
            "current_plan": {
                "product_id": plan.product_id if plan else account["plan_id"],
                "name": plan.title if plan else account["plan_id"],
                "price_per_month": plan.price if plan else None,
                "data_allowance_gb": plan.attributes.get("data_allowance_gb") if plan else None,
            },
            "contract": {
                "started": start.isoformat(),
                "month": month,
                "of_months": _CONTRACT_MONTHS,
                "ends": outright_date.isoformat(),
                "early_upgrade_on": early_date.isoformat(),
            },
            "device": {
                "product_id": device.product_id if device else account["device_id"],
                "name": device.title if device else account["device_id"],
                # One installment per contract month, on the same clock as eligibility.
                "installments_remaining": installments_remaining,
                # The per-payment amount behind monthly_bill_usd (0 once paid off).
                "installment_usd": installment,
            },
            "upgrade_eligibility": eligibility,
            "trade_in_estimate": trade_in,
            "monthly_bill_usd": monthly_bill,
            "recent_usage": usage,
        }

    async def get_disclosure(
        self, session: ShoppingSessionContext, product_id: str
    ) -> Disclosure | None:
        """The service-facts box for a plan or home-internet tier, from the catalog record
        and the fee schedule; devices and add-ons have none."""
        product = self.products.get(product_id)
        if product is None or product.category not in {"plans", "home-internet"}:
            return None
        attrs = product.attributes

        rows: list[DisclosureRow] = [
            DisclosureRow(
                label="Monthly price",
                value=f"${product.price:g}",
                note="includes the $5/mo AutoPay & paperless discount",
            ),
            DisclosureRow(
                label="Additional monthly fees",
                value=f"${_NETWORK_SURCHARGE_USD:g}/line Network Compliance Surcharge",
                note="an ACME Mobile charge, not a government tax; taxes vary by location",
            ),
            DisclosureRow(
                label="One-time fees",
                value="$35 activation, waived online",
            ),
            DisclosureRow(
                label="Early termination fee",
                value="$0"
                if attrs.get("contract_term", "none") == "none"
                else "$175, reduced $10 per completed month",
            ),
        ]
        if product.category == "home-internet":
            rows += [
                DisclosureRow(
                    label="Typical download speed",
                    value=f"{attrs.get('typical_download_mbps', '—')} Mbps",
                ),
                DisclosureRow(
                    label="Typical upload speed",
                    value=f"{attrs.get('typical_upload_mbps', '—')} Mbps",
                ),
                DisclosureRow(
                    label="Typical latency",
                    value=f"{attrs.get('typical_latency_ms', '—')} ms",
                ),
                DisclosureRow(
                    label="Data included",
                    value="Unlimited"
                    if attrs.get("data_cap") == "none"
                    else attrs.get("data_cap", "—"),
                    note="no overage charges",
                ),
                DisclosureRow(
                    label="Equipment fee",
                    value="$0, gateway included"
                    if attrs.get("equipment_fee", "0") == "0"
                    else f"${attrs.get('equipment_fee')}/mo",
                ),
            ]
        else:
            allowance = attrs.get("data_allowance_gb", "—")
            rows += [
                DisclosureRow(
                    label="High-speed data",
                    value="Unlimited" if allowance == "unlimited" else f"{allowance} GB",
                    note=None if allowance == "unlimited" else "then 512 Kbps, no overage charges",
                ),
                DisclosureRow(
                    label="Network management",
                    value=f"may be deprioritized past {attrs.get('deprioritization_threshold_gb', '—')} GB during congestion",
                ),
                DisclosureRow(
                    label="Video resolution",
                    value=attrs.get("video_quality", "—"),
                ),
            ]
        if attrs.get("price_guarantee", "none") != "none":
            rows.append(
                DisclosureRow(
                    label="Price guarantee",
                    value=attrs["price_guarantee"],
                    note="covers the plan price; taxes, fees, and add-ons excluded",
                )
            )
        # Summed here from the figures the rows above state.
        rows.append(
            DisclosureRow(
                label="Estimated all-in",
                value=f"${product.price + _NETWORK_SURCHARGE_USD:.2f}/mo",
                note="plan + ACME surcharge, before location taxes",
            )
        )

        sources = [
            "plan-pricing-disclosures",
            "network-management-disclosure",
            "data-top-ups-and-overage",
            "early-termination",
        ]
        return Disclosure(
            title=f"{product.title}: service facts",
            product_id=product.product_id,
            rows=rows,
            sources=sources,
            evidence=cited_evidence(self._policies, session, sources),
            footnotes=[
                "Prices shown include the AutoPay and paperless billing discount.",
                "Typical speeds are medians measured across the network in the last quarter.",
            ],
        )

    async def get_orders(self, session: ShoppingSessionContext, limit: int = 5) -> list[Order]:
        return orders_for(self._orders, session.user_id, limit)

    async def get_order(self, session: ShoppingSessionContext, order_id: str) -> Order | None:
        return find_order(self._orders, session.user_id, order_id)

    def recent_orders(self, limit: int = 6) -> list[Order]:
        return newest_orders(self._orders, limit)

    async def search_policies(self, session: ShoppingSessionContext, query: str) -> list[Policy]:
        del session
        return search_help(self._policies, query, synonyms=self._help_synonyms)

    async def get_fulfillment_options(
        self, session: ShoppingSessionContext, product_ids: list[str]
    ) -> list[FulfillmentOption]:
        """Activation, shipping or pickup, and installation, by what is in the order."""
        del session
        categories = {product.category for pid in product_ids if (product := self.product(pid))}
        options: list[FulfillmentOption] = []
        if "plans" in categories or "add-ons" in categories or not categories:
            options.append(
                FulfillmentOption(
                    method="delivery",
                    eta="eSIM; activates in minutes after checkout, QR code arrives by email",
                    fee=0.0,
                )
            )
            options.append(
                FulfillmentOption(
                    method="shipping",
                    eta="physical SIM kit, free 2-day shipping",
                    fee=0.0,
                )
            )
        if "devices" in categories:
            options.append(
                FulfillmentOption(
                    method="shipping",
                    eta="free 2-day shipping, signature on delivery",
                    fee=0.0,
                )
            )
            options.append(
                FulfillmentOption(
                    method="pickup",
                    eta="ready today",
                    fee=0.0,
                    location="ACME Mobile store",
                )
            )
        if "home-internet" in categories:
            options.append(
                FulfillmentOption(
                    method="shipping",
                    eta="self-install kit, 3-5 business days; setup takes about 15 minutes",
                    fee=0.0,
                )
            )
            options.append(
                FulfillmentOption(
                    method="delivery",
                    eta="technician installation; next available window within 7 days",
                    fee=0.0,
                )
            )
        return options
