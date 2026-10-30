# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The telecom example's ``MerchantBackend``: the carrier fixtures in ``data/`` (base
metrics, per-plan subscriber series and cohorts, device inventory, campaigns, subscriber
messages) overlaid on the ``MockTelecom`` the storefront serves. A service listing's stock
is its count of active lines, which every price move states as its blast radius; a
promotion applies as a promo window beside the standing price; a plan has no warehouse,
so restocking one is refused."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any

from demo_common.merchant_fixtures import (
    FAMILY_CONTENT_FIELDS,
    alert_counts,
    apply_campaign_item,
    family_pricing_context,
    filter_listings,
    is_browse,
    live_values,
    load_campaigns,
    load_issues,
    load_returns,
    margin_pct,
    metric_window,
    named_ids,
    promotion_targets,
    rebase_daily,
    rebase_weeks,
    refuse_outside_range,
    refuse_shared_content,
    returns_in_period,
    share_content,
    snapshot_of,
    stage_campaign,
    staged_promotion_windows,
)
from demo_common.storefront_fixtures import load_json, refresh_family
from merchant_agent import (
    ActorKind,
    AlertCounts,
    BusinessSnapshot,
    Campaign,
    CampaignDraft,
    ChangeItem,
    ChangeKind,
    ChangeLedger,
    ChangeNotApplicable,
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
    ReturnLog,
    StagedChange,
)
from shopping_agent import ProductDetails, SearchFilters, ShoppingSessionContext

from .mock_telecom import DATA_DIR, MockTelecom

# A device with more days of cover than this at its trailing pace is a slow mover; a
# shrinking plan is flagged once its latest monthly churn reaches the second figure.
_SLOW_MOVER_DAYS_OF_COVER = 120
_PLAN_CHURN_ALERT_PCT = 1.5

_MONEY_METRICS = {
    "sales",
    "storefront_sales",
    "revenue",
    "service_revenue",
    "average_order_value",
    "aov",
    "arpu",
}


class PlanPricingContext(PricingContext):
    """The pricing read for a service listing plus its active lines, per-line economics,
    and applied promo windows."""

    price_unit: str = "per_month"
    active_subscribers: int | None = None
    plan_mix_share_pct: float | None = None
    arpu: float | None = None
    avg_usage_gb: float | None = None
    wholesale_cost_per_line_usd: float | None = None
    margin_per_line_usd: float | None = None
    active_promotions: list[dict[str, Any]] = []


# Device installments in the catalog are the price over this many months.
_INSTALLMENT_MONTHS = 24


class MockTelecomMerchant(MerchantBackend):
    def __init__(
        self,
        storefront: MockTelecom,
        config: MerchantAgentConfig | None = None,
        data_dir: Path = DATA_DIR,
    ) -> None:
        self.storefront = storefront
        self.config = config or MerchantAgentConfig(brand_name=storefront.store_name)
        self.ledger = ChangeLedger(self.config)
        metrics = load_json(data_dir, "merchant_metrics.json")
        self._daily = rebase_daily(metrics["daily"])
        self._currency: str = metrics.get("currency", "USD")
        subscribers = load_json(data_dir, "merchant_subscribers.json")
        self.carrier_name: str = subscribers.get("carrier", "ACME Mobile commercial operations")
        self._wholesale: dict[str, Any] = subscribers.get("wholesale", {})
        self._plans: dict[str, dict[str, Any]] = {
            row["plan_id"]: {**row, "weeks": rebase_weeks(row.get("weeks") or [])}
            for row in subscribers["plans"]
        }
        self._cohorts: list[dict[str, Any]] = list(subscribers.get("cohorts", []))
        inventory = load_json(data_dir, "merchant_inventory.json")
        self._inventory: dict[str, dict[str, Any]] = {
            row["product_id"]: dict(row) for row in inventory["items"]
        }
        self._service_content: dict[str, dict[str, Any]] = {
            row["product_id"]: dict(row) for row in inventory.get("service_content", [])
        }
        self._campaigns = load_campaigns(data_dir)
        self._issues = load_issues(data_dir)
        self._returns = load_returns(data_dir, storefront.product)
        # Status and content state per listing, created on first touch.
        self._listing_state: dict[str, dict[str, Any]] = {}
        # Applied promotions, as promo windows keyed by listing; pending promotions'
        # date windows, keyed by change id.
        self.promo_windows: dict[str, list[dict[str, Any]]] = {}
        self._promotion_windows: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Listings
    # ------------------------------------------------------------------

    def _state_row(self, product_id: str) -> dict[str, Any]:
        if product_id not in self._listing_state:
            overlay = self._service_content.get(product_id, {})
            quality = overlay.get("content_quality")
            missing = list(overlay.get("missing_attributes", []))
            inventory = self._inventory.get(product_id)
            if inventory is not None:
                quality = quality or inventory.get("content_quality", "good")
                missing = missing or list(inventory.get("missing_attributes", []))
            self._listing_state[product_id] = {
                "product_id": product_id,
                "status": "active",
                "content_quality": quality or "good",
                "missing_attributes": missing,
            }
        return self._listing_state[product_id]

    def _stock_for(self, product_id: str) -> int:
        """Devices carry warehouse stock; a service listing's ``stock`` is its count of
        active lines — the blast radius of any change to it."""
        inventory = self._inventory.get(product_id)
        if inventory is not None:
            return int(inventory["stock"])
        plan = self._plans.get(product_id)
        if plan is not None:
            return int(plan["subscribers"])
        return 0

    def _product(self, listing_id: str) -> ProductDetails | None:
        """The storefront record behind a listing id: a plan, a device, a family, or a variant."""
        return self.storefront.product(listing_id)

    def _listing(self, product_id: str) -> Listing | None:
        """One listing row. A device family's price is its lowest variant's and its stock
        the sum of its variants'; a variant carries its option values and its family's id."""
        product = self._product(product_id)
        if product is None:
            return None
        product_id = product.product_id
        row = self._state_row(product_id)
        status = row.get("status", "active")
        variants = [v for variant in product.variants if (v := self._listing(variant.product_id))]
        stock = sum(v.stock for v in variants) if variants else self._stock_for(product_id)
        price = min((v.price for v in variants), default=product.price)
        if status == "active" and not product.in_stock:
            status = "out_of_stock"
        attributes = dict(product.attributes)
        if product_id in self._plans:
            attributes["active_lines"] = str(self._plans[product_id]["subscribers"])
        return Listing(
            listing_id=product_id,
            title=product.title,
            status=status,
            price=price,
            currency=product.currency,
            stock=stock,
            category=product.category,
            content_quality=row.get("content_quality", "good"),
            attributes=attributes,
            image_url=product.image_url,
            short_description=product.short_description,
            options=product.options,
            option_values=product.option_values,
            variant_of=product.variant_of,
        )

    def all_listings(self) -> list[Listing]:
        listings = [
            listing
            for product_id in self.storefront.products
            if (listing := self._listing(product_id)) is not None
        ]
        listings.sort(key=lambda listing: (listing.category or "", listing.listing_id))
        return listings

    # ------------------------------------------------------------------
    # Subscriber base: the per-plan series and the portal's reads of them
    # ------------------------------------------------------------------

    def total_subscribers(self) -> int:
        return sum(int(plan["subscribers"]) for plan in self._plans.values())

    def _plan_margin(self, plan: dict[str, Any]) -> float | None:
        arpu = plan["weeks"][-1]["arpu"] if plan.get("weeks") else None
        wholesale = plan.get("wholesale_cost_per_line_usd")
        if arpu is None or wholesale is None:
            return None
        return round(arpu - wholesale, 2)

    def plan_mix_rows(self, plan_ids: list[str] | None = None) -> list[dict[str, Any]]:
        """Subscriber-base rows per known plan, from the fixture and the catalog."""
        total = self.total_subscribers()
        rows: list[dict[str, Any]] = []
        for plan_id, plan in self._plans.items():
            if plan_ids is not None and plan_id not in plan_ids:
                continue
            product = self.storefront.products.get(plan_id)
            if product is None:
                continue
            latest = plan["weeks"][-1] if plan.get("weeks") else {}
            rows.append(
                {
                    "plan_id": plan_id,
                    "title": product.title,
                    "kind": plan.get("kind", "mobile"),
                    "price": product.price,
                    "currency": product.currency,
                    "subscribers": int(plan["subscribers"]),
                    "share_pct": round(plan["subscribers"] / total * 100, 1) if total else 0.0,
                    "churn_rate_pct": latest.get("churn_rate_pct"),
                    "arpu": latest.get("arpu"),
                    "avg_usage_gb": plan.get("avg_usage_gb"),
                    "wholesale_cost_per_line_usd": plan.get("wholesale_cost_per_line_usd"),
                    "margin_per_line_usd": self._plan_margin(plan),
                    "weeks": [dict(week) for week in plan.get("weeks", [])],
                }
            )
        return rows

    def base_overview(self) -> dict[str, Any]:
        """The portal's base view: every plan's rows, the cohorts, the rate card, and the
        pending promotion windows."""
        return {
            "total_subscribers": self.total_subscribers(),
            "plans": self.plan_mix_rows(),
            "cohorts": [dict(cohort) for cohort in self._cohorts],
            "wholesale": dict(self._wholesale),
            "staged_windows": self.staged_promotion_windows(),
        }

    def today_snapshot(self) -> dict[str, Any] | None:
        """Yesterday's base motion for the portal home page — gross adds, deacts, and
        port-ins from the latest daily row. Portal chrome only."""
        if not self._daily:
            return None
        latest = self._daily[-1]
        return {
            "date": latest["date"],
            "gross_adds": latest["gross_adds"],
            "deacts": latest["deacts"],
            "net_adds": latest["gross_adds"] - latest["deacts"],
            "port_ins": latest["port_ins"],
        }

    def staged_promotion_windows(self) -> list[dict[str, Any]]:
        return staged_promotion_windows(self.ledger, self._promotion_windows)

    # ------------------------------------------------------------------
    # Performance
    # ------------------------------------------------------------------

    def _alert_counts(self) -> AlertCounts:
        return alert_counts(self._compute_alerts(), self._issues, self.ledger)

    async def get_business_snapshot(
        self, session: MerchantSessionContext, period: str | None = None
    ) -> BusinessSnapshot:
        del session
        return snapshot_of(
            self._daily, period, currency=self._currency, alerts=self._alert_counts()
        )

    def _plan_for_segment(self, segment: str | None) -> tuple[str, dict[str, Any]] | None:
        """The plan a segment names, by id or title, with its weekly series."""
        if not segment:
            return None
        cleaned = segment.strip().lower()
        for plan_id, plan in self._plans.items():
            product = self.storefront.products.get(plan_id)
            title = (product.title if product else "").lower()
            if cleaned in {
                plan_id.lower(),
                title,
                title.replace(" ", "-"),
                title.replace(" ", "_"),
            }:
                return plan_id, plan
        return None

    async def query_metrics(
        self,
        session: MerchantSessionContext,
        metric: str,
        period: str | None = None,
        granularity: str = "day",
        segment: str | None = None,
    ) -> MetricSeries:
        del session
        cleaned = metric.strip().lower().replace(" ", "_").replace("-", "_")
        segment_cleaned = (segment or "").strip() or None

        # A segment naming a plan reads that plan's weekly series instead.
        plan_match = self._plan_for_segment(segment_cleaned)
        if plan_match is not None and cleaned in {"churn", "churn_rate", "arpu", "subscribers"}:
            plan_id, plan = plan_match
            key = {
                "churn": "churn_rate_pct",
                "churn_rate": "churn_rate_pct",
                "arpu": "arpu",
                "subscribers": "subscribers",
            }[cleaned]
            weeks = plan.get("weeks", [])
            unit = "%" if key == "churn_rate_pct" else (self._currency if key == "arpu" else None)
            return MetricSeries(
                metric="churn_rate" if key == "churn_rate_pct" else cleaned,
                unit=unit,
                granularity="week",
                period=f"{weeks[0]['week_start']}/{weeks[-1]['week_start']}" if weeks else None,
                segment=plan_id,
                points=[
                    MetricPoint(date=week["week_start"], value=float(week[key])) for week in weeks
                ],
            )

        current, _, label = metric_window(self._daily, period or "last_30_days")
        prepaid = segment_cleaned is not None and segment_cleaned.lower() == "prepaid"

        def value_for(rows: list[dict[str, Any]]) -> float:
            # Ratios are recomputed from the bucket's totals; base counts report the
            # bucket's closing value.
            sales = sum(r["sales"] for r in rows)
            orders = sum(r["orders"] for r in rows)
            traffic = sum(r["traffic"] for r in rows)
            revenue = sum(r["revenue"] for r in rows)
            gross = sum(r["prepaid_gross_adds"] if prepaid else r["gross_adds"] for r in rows)
            deacts = sum(r["deacts"] for r in rows)
            closing_base = rows[-1]["subscribers"]
            avg_base = sum(r["subscribers"] for r in rows) / len(rows)
            days = len(rows)
            if cleaned in {"sales", "storefront_sales"}:
                return round(sales, 2)
            if cleaned == "orders":
                return float(orders)
            if cleaned == "traffic":
                return float(traffic)
            if cleaned in {"conversion", "conversion_rate"}:
                return round(orders / traffic * 100, 2) if traffic else 0.0
            if cleaned in {"average_order_value", "aov"}:
                return round(sales / orders, 2) if orders else 0.0
            if cleaned in {"revenue", "service_revenue"}:
                return round(revenue, 2)
            if cleaned in {"subscribers", "base", "active_lines"}:
                return float(closing_base)
            if cleaned == "gross_adds":
                return float(gross)
            if cleaned in {"deacts", "deactivations"}:
                return float(deacts)
            if cleaned == "net_adds":
                return float(gross - deacts)
            if cleaned in {"port_ins", "port_in"}:
                return float(sum(r["port_ins"] for r in rows))
            if cleaned in {"port_outs", "port_out"}:
                return float(sum(r["port_outs"] for r in rows))
            if cleaned in {"churn", "churn_rate"}:
                # Monthly-equivalent churn: the bucket's deacts scaled to 30 days,
                # over the bucket's average base.
                return round(deacts / days * 30 / avg_base * 100, 2) if avg_base else 0.0
            if cleaned == "arpu":
                # Monthly-equivalent ARPU from recognized service revenue.
                return round(revenue / days * 30 / avg_base, 2) if avg_base else 0.0
            return round(revenue, 2)

        if granularity == "week":
            points = [
                MetricPoint(
                    date=current[start]["date"], value=value_for(current[start : start + 7])
                )
                for start in range(0, len(current), 7)
            ]
        else:
            points = [MetricPoint(date=row["date"], value=value_for([row])) for row in current]
        metric_name = {"churn": "churn_rate", "deactivations": "deacts"}.get(cleaned, cleaned)
        unit = (
            self._currency
            if cleaned in _MONEY_METRICS
            else (
                "%" if cleaned in {"churn", "churn_rate", "conversion", "conversion_rate"} else None
            )
        )
        return MetricSeries(
            metric=metric_name,
            unit=unit,
            granularity="week" if granularity == "week" else "day",
            period=label,
            segment="prepaid" if prepaid else segment_cleaned,
            points=points,
        )

    async def get_campaign_performance(
        self, session: MerchantSessionContext, campaign_id: str | None = None
    ) -> list[Campaign]:
        del session
        campaigns = list(self._campaigns.values())
        if campaign_id:
            campaigns = [c for c in campaigns if c.campaign_id == campaign_id]
        return campaigns

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    async def search_listings(
        self,
        session: MerchantSessionContext,
        query: str,
        filters: ListingFilters | None = None,
        limit: int = 8,
    ) -> list[Listing]:
        if ids := named_ids(query, [*self.storefront.products, *self.storefront.variants]):
            listings = [listing for pid in ids if (listing := self._listing(pid))]
        elif is_browse(query):
            listings = self.all_listings()
        else:
            shopper = ShoppingSessionContext(
                session_id=session.session_id, user_id="merchant-portal"
            )
            products = await self.storefront.search_products(
                shopper, query, SearchFilters(), limit=max(limit, 8)
            )
            listings = [listing for p in products if (listing := self._listing(p.product_id))]
        return filter_listings(
            listings,
            filters,
            limit,
            sales_of=lambda listing_id: self._sales_last_30d(listing_id) or 0,
        )

    def _sales_last_30d(self, product_id: str) -> int | None:
        inventory = self._inventory.get(product_id)
        if inventory is not None:
            return int(inventory["sales_last_30d"])
        return None

    async def get_listing(
        self, session: MerchantSessionContext, listing_id: str
    ) -> ListingDetails | None:
        del session
        product = self._product(listing_id)
        if product is None:
            return None
        listing = self._listing(product.product_id)
        if listing is None:
            return None
        row = self._state_row(product.product_id)
        variants = [v for variant in product.variants if (v := self._listing(variant.product_id))]
        sales = [s for v in variants if (s := self._sales_last_30d(v.listing_id)) is not None]
        return ListingDetails(
            **listing.model_dump(),
            long_description=product.long_description,
            review_snippets=product.review_highlights,
            sales_last_30d=(sum(sales) if sales else None)
            if variants
            else self._sales_last_30d(product.product_id),
            missing_attributes=row.get("missing_attributes") or [],
            variants=variants,
        )

    # ------------------------------------------------------------------
    # Inventory and order health
    # ------------------------------------------------------------------

    def _compute_alerts(self) -> list[InventoryAlert]:
        """Devices alert on stock and days of cover; a plan whose base shrank and whose
        churn reached the alert rate is a ``slow_mover`` with its active lines as stock."""
        alerts: list[InventoryAlert] = []
        for product_id, row in self._inventory.items():
            product = self._product(product_id)
            if product is None or product.has_options:
                continue  # a family's stock lives on its variants' rows
            stock = int(row["stock"])
            threshold = int(row["threshold"])
            sales = int(row["sales_last_30d"])
            daily_pace = sales / 30
            days_of_cover = round(stock / daily_pace, 1) if daily_pace else None
            state = self._state_row(product_id)
            visible = product.in_stock and state.get("status") != "paused"
            if stock <= threshold:
                alerts.append(
                    InventoryAlert(
                        listing_id=product_id,
                        title=product.title,
                        kind="low_stock",
                        option_values=product.option_values,
                        variant_of=product.variant_of,
                        stock=stock,
                        threshold=threshold,
                        days_of_cover=days_of_cover,
                        sales_last_30d=sales,
                        storefront_visible=visible,
                    )
                )
            elif days_of_cover is not None and days_of_cover > _SLOW_MOVER_DAYS_OF_COVER:
                alerts.append(
                    InventoryAlert(
                        listing_id=product_id,
                        title=product.title,
                        kind="slow_mover",
                        stock=stock,
                        threshold=threshold,
                        days_of_cover=days_of_cover,
                        sales_last_30d=sales,
                        storefront_visible=visible,
                    )
                )
        for plan_id, plan in self._plans.items():
            product = self.storefront.products.get(plan_id)
            weeks = plan.get("weeks") or []
            if product is None or len(weeks) < 2:
                continue
            declined = weeks[-1]["subscribers"] < weeks[0]["subscribers"]
            churn = weeks[-1]["churn_rate_pct"]
            if declined and churn >= _PLAN_CHURN_ALERT_PCT:
                alerts.append(
                    InventoryAlert(
                        listing_id=plan_id,
                        title=product.title,
                        kind="slow_mover",
                        stock=int(plan["subscribers"]),
                        threshold=int(weeks[0]["subscribers"]),
                        days_of_cover=None,
                        sales_last_30d=None,
                        storefront_visible=product.in_stock,
                    )
                )
        # Low stock first (devices about to disappear from the storefront), then the
        # shrinking plans, largest base at stake first.
        alerts.sort(key=lambda alert: (alert.kind != "low_stock", -alert.stock))
        return alerts

    async def get_inventory_alerts(self, session: MerchantSessionContext) -> list[InventoryAlert]:
        del session
        return self._compute_alerts()

    async def get_order_issues(self, session: MerchantSessionContext) -> list[OrderIssue]:
        del session
        return list(self._issues)

    async def get_returns(
        self,
        session: MerchantSessionContext,
        period: str | None = None,
        listing_id: str | None = None,
    ) -> ReturnLog:
        del session
        end = date.fromisoformat(self._daily[-1]["date"])
        return returns_in_period(self._returns, period, end, listing_id)

    # ------------------------------------------------------------------
    # Pricing
    # ------------------------------------------------------------------

    def _unit_cost(self, product_id: str) -> float | None:
        inventory = self._inventory.get(product_id)
        if inventory is not None:
            return float(inventory["unit_cost"])
        plan = self._plans.get(product_id)
        if plan is not None:
            return plan.get("wholesale_cost_per_line_usd")
        return None

    async def get_pricing_context(
        self, session: MerchantSessionContext, listing_id: str
    ) -> PricingContext | None:
        del session
        product = self._product(listing_id)
        if product is None:
            return None
        listing_id = product.product_id
        if product.has_options:
            return family_pricing_context(
                product,
                [self._device_pricing_context(variant) for variant in product.variants],
                self.config,
            )
        row = self._state_row(listing_id)
        unit_cost = self._unit_cost(listing_id)
        margin = margin_pct(product.price, unit_cost) if unit_cost is not None else None
        plan = self._plans.get(listing_id)
        if plan is not None:
            weeks = plan.get("weeks") or []
            latest = weeks[-1] if weeks else {}
            if len(weeks) >= 5:
                recent_delta = weeks[-1]["subscribers"] - weeks[-5]["subscribers"]
                demand = (
                    "falling" if recent_delta < 0 else "rising" if recent_delta > 40 else "steady"
                )
            else:
                demand = "steady"
            total = self.total_subscribers()
            return PlanPricingContext(
                listing_id=listing_id,
                current_price=product.price,
                currency=product.currency,
                unit_cost=unit_cost,
                margin_pct=margin,
                min_price=round(unit_cost * 1.15, 2) if unit_cost else None,
                max_price=round(product.price * 1.2, 2),
                max_price_delta_pct=self.config.max_price_delta_pct,
                max_promotion_discount_pct=self.config.max_promotion_discount_pct,
                demand_signal=demand,
                last_changed=row.get("last_price_change"),
                active_subscribers=int(plan["subscribers"]),
                plan_mix_share_pct=round(plan["subscribers"] / total * 100, 1) if total else None,
                arpu=latest.get("arpu"),
                avg_usage_gb=plan.get("avg_usage_gb"),
                wholesale_cost_per_line_usd=plan.get("wholesale_cost_per_line_usd"),
                margin_per_line_usd=self._plan_margin(plan),
                active_promotions=list(self.promo_windows.get(listing_id, [])),
            )
        return self._device_pricing_context(product)

    def _device_pricing_context(self, product: ProductDetails) -> PricingContext:
        listing_id = product.product_id
        row = self._state_row(listing_id)
        unit_cost = self._unit_cost(listing_id)
        margin = margin_pct(product.price, unit_cost) if unit_cost is not None else None
        sales = self._sales_last_30d(listing_id)
        if sales is not None and sales >= 80:
            demand = "rising"
        elif sales is not None and sales <= 25:
            demand = "falling"
        else:
            demand = "steady"
        return PricingContext(
            listing_id=listing_id,
            current_price=product.price,
            currency=product.currency,
            unit_cost=unit_cost,
            margin_pct=margin,
            min_price=round(unit_cost * 1.1, 2) if unit_cost is not None else None,
            max_price=round(product.price * 1.2, 2),
            max_price_delta_pct=self.config.max_price_delta_pct,
            max_promotion_discount_pct=self.config.max_promotion_discount_pct,
            demand_signal=demand,
            last_changed=row.get("last_price_change"),
            option_values=product.option_values,
        )

    # ------------------------------------------------------------------
    # Staged writes
    # ------------------------------------------------------------------

    def _blast_radius_note(self, product_id: str) -> str | None:
        plan = self._plans.get(product_id)
        product = self._product(product_id)
        if plan is None or product is None:
            return None
        return (
            f"{product_id} affects {int(plan['subscribers']):,} active lines on "
            f"{product.title}; every one sees the new price at their next bill cycle"
        )

    async def stage_listing_update(
        self,
        session: MerchantSessionContext,
        listing_id: str,
        fields: dict[str, Any],
        note: str | None = None,
    ) -> StagedChange:
        listing = await self.get_listing(session, listing_id)
        if listing is None:
            raise ValueError(f"no listing {listing_id}")
        refuse_shared_content(listing, fields)
        items = [
            ChangeItem(
                target=listing.listing_id,
                field=name,
                before=getattr(listing, name, listing.attributes.get(name)),
                after=value,
            )
            for name, value in fields.items()
        ]
        return self.ledger.stage(
            kind=ChangeKind.LISTING_UPDATE,
            summary=note or f"Update listing content on {listing.listing_id}",
            items=items,
            actor=session.operator,
            actor_kind=ActorKind.AGENT,
        )

    async def stage_price_update(
        self,
        session: MerchantSessionContext,
        items: list[PriceUpdateItem],
        note: str | None = None,
    ) -> StagedChange:
        """Standing price changes; a service's notes state the lines it touches and its
        margin impact is the monthly revenue delta across them."""
        change_items = []
        margin_impact = 0.0
        margins: list[tuple[float, float]] = []
        notes: list[str] = []
        currency: str | None = None
        for item in items:
            # An id that resolves to nothing is refused: staged, it would preview
            # cleanly and then apply as a silent no-op.
            product = self._product(item.listing_id)
            if product is None:
                raise ValueError(f"no listing {item.listing_id}")
            if product.has_options:
                # The executor holds this first; a price lives on the variants.
                raise ValueError(f"{product.product_id} is priced per variant")
            resolved = product.product_id
            context = await self.get_pricing_context(session, resolved)
            if context is not None:
                refuse_outside_range(resolved, item.new_price, context)
            before = product.price
            if currency is None:
                currency = product.currency
            plan = self._plans.get(resolved)
            unit_cost = self._unit_cost(resolved)
            if plan is not None:
                # Monthly revenue impact across every active line on the plan.
                margin_impact += (item.new_price - before) * int(plan["subscribers"])
                radius = self._blast_radius_note(resolved)
                if radius:
                    notes.append(radius)
            else:
                sales = self._sales_last_30d(resolved) or 0
                margin_impact += (item.new_price - before) * sales / 30 * 7
            if unit_cost is not None:
                margin_before = margin_pct(before, unit_cost)
                margin_after = margin_pct(item.new_price, unit_cost)
                margins.append((margin_before, margin_after))
                notes.append(
                    f"{resolved} margin: {margin_before}% → {margin_after}% "
                    f"({margin_after - margin_before:+.1f} pts)"
                )
            change_items.append(
                ChangeItem(target=resolved, field="price", before=before, after=item.new_price)
            )
        return self.ledger.stage(
            kind=ChangeKind.PRICE_UPDATE,
            summary=note or f"Price update for {len(items)} listing(s)",
            items=change_items,
            actor=session.operator,
            actor_kind=ActorKind.AGENT,
            currency=currency,
            margin_impact=round(margin_impact, 2),
            margin_before_pct=margins[0][0] if len(margins) == 1 else None,
            margin_after_pct=margins[0][1] if len(margins) == 1 else None,
            guardrail_notes=notes or None,
        )

    async def stage_inventory_action(
        self,
        session: MerchantSessionContext,
        items: list[InventoryActionItem],
        note: str | None = None,
    ) -> StagedChange:
        """Restocks apply to devices; a service has no warehouse and is refused.
        Pause and activate apply to any listing."""
        change_items = []
        for item in items:
            product = self._product(item.listing_id)
            if product is None:
                raise ValueError(f"no listing {item.listing_id}")
            resolved = product.product_id
            if item.action == "restock":
                if product.has_options:
                    raise ValueError(f"{resolved} is restocked per variant")
                inventory = self._inventory.get(resolved)
                if inventory is None:
                    raise ChangeNotApplicable(
                        f"{product.title} is a service, not stocked "
                        "hardware — ACME Mobile holds no inventory for it. Pause or activate "
                        "its availability, or use the pricing tools instead."
                    )
                current: Any = int(inventory["stock"])
                after: Any = current + (item.quantity or 0)
                field = "stock"
            else:
                after = "paused" if item.action == "pause" else "active"
                field = "status"
                listing = self._listing(resolved)
                current = listing.status if listing else None
            change_items.append(
                ChangeItem(target=resolved, field=field, before=current, after=after)
            )
        return self.ledger.stage(
            kind=ChangeKind.INVENTORY_ACTION,
            summary=note or f"Availability action for {len(items)} listing(s)",
            items=change_items,
            actor=session.operator,
            actor_kind=ActorKind.AGENT,
        )

    async def stage_promotion(
        self, session: MerchantSessionContext, promotion: PromotionDraft
    ) -> StagedChange:
        """A promotional price for a date window, recorded as a window when applied; the
        standing price does not move and ``nights`` is ignored."""
        try:
            window_days = max(
                1,
                (date.fromisoformat(promotion.ends) - date.fromisoformat(promotion.starts)).days
                + 1,
            )
        except ValueError:
            window_days = 30
        items = []
        margin_impact = 0.0
        margins: list[tuple[float, float]] = []
        notes: list[str] = []
        currency: str | None = None
        requested = {listing_id: self._product(listing_id) for listing_id in promotion.listing_ids}
        if missing := [listing_id for listing_id, found in requested.items() if found is None]:
            raise ValueError(f"no listing {missing[0]}")
        # A promotion on a family is a promotion on each of its variants.
        targets = promotion_targets(requested.values())
        for product in targets:
            resolved = product.product_id
            if currency is None:
                currency = product.currency
            discount_value = product.price * promotion.discount_pct / 100
            promo_price = round(product.price * (1 - promotion.discount_pct / 100), 2)
            plan = self._plans.get(resolved)
            if plan is not None:
                # Revenue impact across the plan's base for the window's share of a month.
                margin_impact -= discount_value * int(plan["subscribers"]) * window_days / 30
                radius = self._blast_radius_note(resolved)
                if radius:
                    notes.append(radius)
            else:
                sales = self._sales_last_30d(resolved) or 0
                margin_impact -= discount_value * sales / 30 * window_days
            unit_cost = self._unit_cost(resolved)
            if unit_cost is not None and promo_price > 0:
                margin_before = margin_pct(product.price, unit_cost)
                margin_after = margin_pct(promo_price, unit_cost)
                margins.append((margin_before, margin_after))
                notes.append(
                    f"{resolved} margin: {margin_before}% → {margin_after}% "
                    f"({margin_after - margin_before:+.1f} pts) for the window"
                )
            items.append(
                ChangeItem(target=resolved, field="price", before=product.price, after=promo_price)
            )
        direction = "off" if promotion.discount_pct >= 0 else "increase on"
        change = self.ledger.stage(
            kind=ChangeKind.PROMOTION,
            summary=f"{promotion.name} ({abs(promotion.discount_pct):.0f}% {direction} "
            f"the monthly price, {promotion.starts} to {promotion.ends})",
            items=items,
            actor=session.operator,
            actor_kind=ActorKind.AGENT,
            currency=currency,
            margin_impact=round(margin_impact, 2),
            margin_before_pct=margins[0][0] if len(margins) == 1 else None,
            margin_after_pct=margins[0][1] if len(margins) == 1 else None,
            guardrail_notes=notes or None,
        )
        self._promotion_windows[change.change_id] = {
            "starts": promotion.starts,
            "ends": promotion.ends,
            "discount_pct": promotion.discount_pct,
            "name": promotion.name,
        }
        return change

    async def stage_campaign(
        self, session: MerchantSessionContext, campaign: CampaignDraft
    ) -> StagedChange:
        return stage_campaign(
            self.ledger, self._campaigns, campaign, actor=session.operator, currency=self._currency
        )

    async def get_pending_changes(self, session: MerchantSessionContext) -> list[StagedChange]:
        del session
        return self.ledger.pending()

    async def apply_change(self, session: MerchantSessionContext, change_id: str) -> StagedChange:
        live = await live_values(self, session, self.ledger.get(change_id), self._campaigns)
        applied = self.ledger.apply(change_id, actor=session.operator, live=live)
        self._apply_to_live_state(applied)
        return applied

    async def discard_change(
        self,
        session: MerchantSessionContext,
        change_id: str,
        actor_kind: ActorKind = ActorKind.OPERATOR,
    ) -> StagedChange:
        discarded = self.ledger.discard(change_id, actor=session.operator, actor_kind=actor_kind)
        self._promotion_windows.pop(change_id, None)
        return discarded

    def _apply_to_live_state(self, change: StagedChange) -> None:
        """Make an approved change visible in the shared consumer-facing state — a plan
        price change moves the storefront price AND the demo account's derived bill."""
        for item in change.items:
            product = self._product(item.target)
            if product is not None and change.kind in {
                ChangeKind.PRICE_UPDATE,
                ChangeKind.INVENTORY_ACTION,
                ChangeKind.LISTING_UPDATE,
            }:
                row = self._state_row(item.target)
                family = self._product(product.variant_of) if product.variant_of else None
                if change.kind is ChangeKind.PRICE_UPDATE:
                    product.price = float(item.after)
                    row["last_price_change"] = datetime.now(UTC).date().isoformat()
                    if "monthly_installment" in product.attributes:
                        # The catalog's installment string follows the device price.
                        cents = Decimal(str(product.price)) / _INSTALLMENT_MONTHS
                        monthly = cents.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                        product.attributes["monthly_installment"] = (
                            f"{monthly} for {_INSTALLMENT_MONTHS} months"
                        )
                elif change.kind is ChangeKind.INVENTORY_ACTION:
                    if item.field == "stock":
                        inventory = self._inventory.get(item.target)
                        stock = int(item.after)
                        if inventory is not None:
                            # The staged delta, so two restocks staged against the
                            # same starting stock both count.
                            delta = int(item.after) - int(item.before or 0)
                            inventory["stock"] = int(inventory["stock"]) + delta
                            stock = int(inventory["stock"])
                        product.in_stock = stock > 0 and row.get("status") != "paused"
                    elif item.field == "status":
                        row["status"] = "paused" if item.after == "paused" else "active"
                        # Pausing a family takes every variant off sale and reactivating it
                        # returns each variant to what its own stock says; a variant or a
                        # plain listing follows its own row.
                        for variant in product.variants or [product]:
                            if product.has_options:
                                self._state_row(variant.product_id)["status"] = (
                                    "paused" if item.after == "paused" else "active"
                                )
                            stocked = self._inventory.get(variant.product_id)
                            has_stock = stocked is None or int(stocked.get("stock", 0)) > 0
                            variant.in_stock = item.after != "paused" and has_stock
                refresh_family(family or product)
                if change.kind is ChangeKind.LISTING_UPDATE:
                    if item.field in FAMILY_CONTENT_FIELDS:
                        share_content(product, item.field, item.after)
                    elif item.field == "content_quality":
                        row["content_quality"] = item.after
                    else:
                        product.attributes[item.field] = str(item.after)
                        if item.field in row.get("missing_attributes", []):
                            row["missing_attributes"].remove(item.field)
                    if row.get("content_quality") == "needs_work" and item.field in {
                        "short_description",
                        "long_description",
                    }:
                        row["content_quality"] = "good"
            elif change.kind is ChangeKind.PROMOTION:
                window = self._promotion_windows.get(change.change_id, {})
                self.promo_windows.setdefault(item.target, []).append(
                    {
                        "starts": window.get("starts"),
                        "ends": window.get("ends"),
                        "promo_price": float(item.after),
                        "standing_price": float(item.before) if item.before is not None else None,
                        "discount_pct": window.get("discount_pct"),
                        "summary": change.summary,
                        "change_id": change.change_id,
                    }
                )
            elif change.kind is ChangeKind.CAMPAIGN:
                apply_campaign_item(self._campaigns, item)

    # ------------------------------------------------------------------
    # Merchant context
    # ------------------------------------------------------------------

    async def get_merchant_context(self, session: MerchantSessionContext) -> dict[str, Any] | None:
        counts = self._alert_counts()
        latest = self._daily[-1]["date"]
        week_start = (date.fromisoformat(latest) - timedelta(days=6)).isoformat()
        return {
            "carrier": self.carrier_name,
            "storefront": self.storefront.store_name,
            "operator": session.operator,
            "current_period": f"{week_start}/{latest}",
            "subscribers_total": self.total_subscribers(),
            "plan_listings": sorted(self._plans),
            "cohorts": [
                {"cohort_id": c["cohort_id"], "label": c["label"], "size": c["size"]}
                for c in self._cohorts
            ],
            "alerts": {
                "device_low_stock": counts.low_stock,
                "underselling": counts.slow_movers,
                "subscriber_messages": counts.order_issues,
                "pending_changes": counts.pending_changes,
            },
        }
