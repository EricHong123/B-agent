# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The entertainment example's ``MerchantBackend``: the promoter fixtures in ``data/``
(sales metrics, the pacing and allocation book, campaigns, fan messages) over the same
ticketing engine the storefront sells from. A tier's stock is the engine's live open
count; a restock releases held seats and applies as real capacity; a price move keeps the
itemized fees fixed and moves the face value; pausing a tier on sale is refused; pacing
compares live counts against a baseline of comparable events."""

from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from demo_common.merchant_fixtures import (
    alert_counts,
    apply_campaign_item,
    filter_listings,
    is_browse,
    live_values,
    load_campaigns,
    load_issues,
    load_returns,
    margin_pct,
    metric_window,
    named_ids,
    rebase_daily,
    returns_in_period,
    snapshot_of,
    stage_campaign,
    staged_promotion_windows,
)
from demo_common.storefront_fixtures import find_by_id, load_json
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
    ReturnLog,
    StagedChange,
)
from shopping_agent import SearchFilters, ShoppingSessionContext

from .mock_ticketing import DATA_DIR, MockTicketing

# A tier with this few open seats is a low_stock alert (the storefront's "selling fast"
# floor); a tier this many points under its baseline is a slow mover.
_NEARLY_SOLD_OUT_FLOOR = 12
_UNDER_PACE_ALERT_PTS = 15.0
# Fee attributes pass through unchanged when the face value moves; their sum is the
# floor under any price.
_FEE_ATTRS = ("service_fee_usd", "facility_fee_usd", "processing_fee_usd")
# The share of face value owed to the artist and house.
_HOUSE_COST_SHARE = 0.68
# Hold buckets a release may draw from, in order; comps and kills are not sellable.
_RELEASABLE_BUCKETS = ("promoter_hold", "production_hold")
_MONEY_METRICS = {"sales", "gross", "average_order_value", "aov", "average_ticket_price"}


class TierPricingContext(PricingContext):
    """The pricing read for a tier plus its live sell-through, pace against the
    baseline, waitlist depth, and fee floor."""

    price_unit: str = "per_ticket_all_in"
    event_id: str | None = None
    event_date: str | None = None
    days_to_event: int | None = None
    capacity: int | None = None
    sold: int | None = None
    remaining: int | None = None
    sell_through_pct: float | None = None
    baseline_pct: float | None = None
    pace_vs_baseline_pts: float | None = None
    waitlist_depth: int | None = None
    holds: dict[str, int] = {}
    fees_usd: float | None = None
    active_promotions: list[dict[str, Any]] = []


def _shift_day(day: str, delta: timedelta) -> str:
    return (date.fromisoformat(day) + delta).isoformat()


def _shift_pacing(pacing: dict[str, Any], delta: timedelta) -> dict[str, Any]:
    """The pacing book with every event date, on-sale date, and weekly row moved by
    ``delta``, in place."""
    if delta:
        for event in pacing["events"]:
            for key in ("event_date", "on_sale_date"):
                if event.get(key):
                    event[key] = _shift_day(event[key], delta)
            for tier in event["tiers"]:
                for week in tier.get("weekly_sold_cum", []):
                    week["week_start"] = _shift_day(week["week_start"], delta)
    return pacing


class MockTicketingMerchant(MerchantBackend):
    def __init__(
        self,
        storefront: MockTicketing,
        config: MerchantAgentConfig | None = None,
        data_dir: Path = DATA_DIR,
    ) -> None:
        self.storefront = storefront
        self.config = config or MerchantAgentConfig(brand_name=storefront.store_name)
        self.ledger = ChangeLedger(self.config)
        metrics = load_json(data_dir, "merchant_metrics.json")
        self._daily = rebase_daily(metrics["daily"])
        self._currency: str = metrics.get("currency", "USD")
        # The pacing book moves with the catalog's shows (shift_event_dates in
        # mock_ticketing), so each show stays as many days out as it was written to be.
        pacing = _shift_pacing(
            load_json(data_dir, "merchant_pacing.json"), storefront.calendar_shift
        )
        self.promoter_name: str = pacing.get("promoter", "ACME Tickets promoter")
        self._baselines: dict[str, list[list[float]]] = pacing.get("baselines", {})
        self._events: dict[str, dict[str, Any]] = {
            row["event_id"]: dict(row) for row in pacing["events"]
        }
        # The allocation book per tier is an opening balance that releases draw down.
        self._allocations: dict[str, dict[str, int]] = {}
        self._tier_history: dict[str, list[dict[str, Any]]] = {}
        self._tier_event: dict[str, str] = {}
        for event in self._events.values():
            for tier in event["tiers"]:
                pid = tier["product_id"]
                self._allocations[pid] = dict(tier["allocations"])
                self._tier_history[pid] = list(tier["weekly_sold_cum"])
                self._tier_event[pid] = event["event_id"]
        self._campaigns = load_campaigns(data_dir)
        self._issues = load_issues(data_dir)
        self._returns = load_returns(data_dir, storefront.product)
        # Content state per listing, created on first touch.
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
            self._listing_state[product_id] = {
                "product_id": product_id,
                "content_quality": "good",
                "missing_attributes": [],
            }
        return self._listing_state[product_id]

    def _listing(self, product_id: str) -> Listing | None:
        product = self.storefront.products.get(product_id)
        if product is None or product_id not in self._tier_event:
            return None
        row = self._state_row(product_id)
        engine = self.storefront.engine
        remaining = engine.remaining(product_id)
        return Listing(
            listing_id=product.product_id,
            title=product.title,
            status="out_of_stock" if remaining == 0 else "active",
            price=product.price,
            currency=product.currency,
            # The live open count — capacity − sold − holds − offers, straight from
            # the engine. Truthful scarcity holds on the operator side too.
            stock=remaining,
            category=product.category,
            content_quality=row.get("content_quality", "good"),
            attributes=dict(product.attributes),
            image_url=product.image_url,
            short_description=product.short_description,
        )

    def all_listings(self) -> list[Listing]:
        listings = [
            listing
            for product_id in self._portfolio_ids()
            if (listing := self._listing(product_id)) is not None
        ]
        listings.sort(key=lambda listing: listing.listing_id)
        return listings

    # ------------------------------------------------------------------
    # Pacing: the allocation book, the baseline, and the portal's reads of them
    # ------------------------------------------------------------------

    def _portfolio_ids(self) -> list[str]:
        """The tiers the box office manages: the primary ticket listings. Fan resale
        listings belong to fans — the operator observes them, never edits them."""
        return [pid for pid in self._tier_event if pid in self.storefront.products]

    def _today(self) -> date:
        """Time flows through the engine's injectable clock, so tests can drive
        days-to-event deterministically."""
        return self.storefront.engine.now().date()

    def _days_to_event(self, event_id: str) -> int:
        event = self._events[event_id]
        return (date.fromisoformat(event["event_date"]) - self._today()).days

    def _baseline_at(self, kind: str, days_before: float) -> float | None:
        points = self._baselines.get(kind)
        if not points:
            return None
        if days_before >= points[0][0]:
            return float(points[0][1])
        for (d1, p1), (d2, p2) in zip(points, points[1:], strict=False):
            if d2 <= days_before <= d1:
                span = d1 - d2
                t = (d1 - days_before) / span if span else 1.0
                return round(p1 + (p2 - p1) * t, 1)
        return 100.0

    def _tier_pacing(self, product_id: str) -> dict[str, Any] | None:
        """The live pacing row for one tier: engine counts now, the fixture's weekly
        history, and the gap to the comparable baseline at today's days-to-event."""
        event_id = self._tier_event.get(product_id)
        product = self.storefront.products.get(product_id)
        if event_id is None or product is None:
            return None
        event = self._events[event_id]
        engine = self.storefront.engine
        capacity = engine.capacity(product_id)
        sold = engine.sold(product_id)
        remaining = engine.remaining(product_id)
        sell_through = round(sold / capacity * 100, 1) if capacity else 0.0
        days_to_event = self._days_to_event(event_id)
        baseline = self._baseline_at(event.get("baseline_kind", ""), max(days_to_event, 0))
        history = self._tier_history.get(product_id, [])
        weekly_pace = None
        if len(history) >= 5:
            weekly_pace = round((history[-1]["sold_cum"] - history[-5]["sold_cum"]) / 4, 1)
        # The baseline sampled at each history week's closing day, clamped at the event.
        event_date = date.fromisoformat(event["event_date"])
        weekly_baseline = [
            self._baseline_at(
                event.get("baseline_kind", ""),
                max(
                    (
                        event_date - (date.fromisoformat(week["week_start"]) + timedelta(days=6))
                    ).days,
                    0,
                ),
            )
            for week in history
        ]
        return {
            "product_id": product_id,
            "tier": product.attributes.get("tier"),
            "tier_code": product.attributes.get("tier_code"),
            "weekly_baseline_pct": weekly_baseline,
            "price": product.price,
            "currency": product.currency,
            "capacity": capacity,
            "sold": sold,
            "remaining": remaining,
            "sell_through_pct": sell_through,
            "baseline_pct": baseline,
            "pace_vs_baseline_pts": round(sell_through - baseline, 1)
            if baseline is not None
            else None,
            "waitlist_depth": engine.waitlist_depth(product_id),
            "holds": dict(self._allocations.get(product_id, {})),
            "weekly_sold_cum": [dict(week) for week in history],
            "recent_weekly_sales": weekly_pace,
        }

    def event_pacing_rows(self, event_ids: list[str]) -> list[dict[str, Any]]:
        """Pacing rows per known event: live counts from the engine, baseline and history
        from the fixture."""
        rows: list[dict[str, Any]] = []
        for event_id in event_ids:
            event = self._events.get(event_id)
            if event is None:
                continue
            tiers = [
                pacing
                for tier in event["tiers"]
                if (pacing := self._tier_pacing(tier["product_id"])) is not None
            ]
            sample = self.storefront.products.get(event["tiers"][0]["product_id"])
            attributes = sample.attributes if sample else {}
            rows.append(
                {
                    "event_id": event_id,
                    "event_name": attributes.get("event_name", event_id),
                    "venue": attributes.get("venue"),
                    "venue_id": attributes.get("venue_id"),
                    "city": attributes.get("city"),
                    "event_date": event["event_date"],
                    "on_sale_date": event["on_sale_date"],
                    "days_to_event": self._days_to_event(event_id),
                    "baseline_kind": event.get("baseline_kind"),
                    "tiers": tiers,
                }
            )
        return rows

    def pacing_overview(self) -> dict[str, Any]:
        """The portal's pacing read: every event's rows, pending promotion windows, and
        the venue geometry the holds view shades (sections bind to tiers by tier_code)."""
        events = self.event_pacing_rows(list(self._events))
        venue_ids = {event.get("venue_id") for event in events if event.get("venue_id")}
        return {
            "events": events,
            "staged_windows": self.staged_promotion_windows(),
            "venues": {
                venue_id: dict(self.storefront.venues[venue_id])
                for venue_id in venue_ids
                if venue_id in self.storefront.venues
            },
        }

    def staged_promotion_windows(self) -> list[dict[str, Any]]:
        return staged_promotion_windows(self.ledger, self._promotion_windows)

    def today_snapshot(self) -> dict[str, Any] | None:
        """The next shows on the calendar for the portal home page — each with its
        live sold/remaining totals. Portal chrome only."""
        upcoming = sorted(
            (event_id for event_id in self._events if self._days_to_event(event_id) >= 0),
            key=self._days_to_event,
        )[:3]
        if not upcoming:
            return None
        engine = self.storefront.engine
        shows = []
        for event_id in upcoming:
            event = self._events[event_id]
            tier_ids = [tier["product_id"] for tier in event["tiers"]]
            sample = self.storefront.products.get(tier_ids[0])
            attributes = sample.attributes if sample else {}
            shows.append(
                {
                    "event_id": event_id,
                    "event_name": attributes.get("event_name", event_id),
                    "venue": attributes.get("venue"),
                    "event_date": event["event_date"],
                    "days_to_event": self._days_to_event(event_id),
                    "sold": sum(engine.sold(pid) for pid in tier_ids),
                    "capacity": sum(engine.capacity(pid) for pid in tier_ids),
                    "remaining": sum(engine.remaining(pid) for pid in tier_ids),
                    "waitlist_depth": sum(engine.waitlist_depth(pid) for pid in tier_ids),
                }
            )
        return {"upcoming": shows}

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

    def _event_for_segment(self, segment: str | None) -> str | None:
        if not segment:
            return None
        cleaned = segment.strip().lower()
        for event_id, event in self._events.items():
            sample = self.storefront.products.get(event["tiers"][0]["product_id"])
            name = (sample.attributes.get("event_name", "") if sample else "").lower()
            if cleaned == event_id.lower() or (name and cleaned in {name, name.replace(" ", "-")}):
                return event_id
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

        # A segment naming an event reads the pacing book's weekly history instead.
        event_id = self._event_for_segment(segment_cleaned)
        if event_id is not None and cleaned in {
            "sold",
            "sold_cum",
            "tickets",
            "tickets_sold",
            "sell_through",
            "sell_through_pct",
        }:
            tier_ids = [tier["product_id"] for tier in self._events[event_id]["tiers"]]
            histories = [self._tier_history[pid] for pid in tier_ids if pid in self._tier_history]
            weeks = [entry["week_start"] for entry in max(histories, key=len)]
            capacity = sum(self.storefront.engine.capacity(pid) for pid in tier_ids)

            def cum_at(week_start: str) -> int:
                total = 0
                for history in histories:
                    value = 0
                    for entry in history:
                        if entry["week_start"] <= week_start:
                            value = entry["sold_cum"]
                    total += value
                return total

            points = []
            prev = 0
            for week_start in weeks:
                cum = cum_at(week_start)
                if cleaned in {"tickets", "tickets_sold"}:
                    value = float(cum - prev)
                elif cleaned in {"sell_through", "sell_through_pct"}:
                    value = round(cum / capacity * 100, 1) if capacity else 0.0
                else:
                    value = float(cum)
                points.append(MetricPoint(date=week_start, value=value))
                prev = cum
            unit = "%" if cleaned.startswith("sell_through") else None
            return MetricSeries(
                metric="sell_through" if cleaned.startswith("sell_through") else cleaned,
                unit=unit,
                granularity="week",
                period=f"{weeks[0]}/{weeks[-1]}" if weeks else None,
                segment=event_id,
                points=points,
            )

        current, _, label = metric_window(self._daily, period or "last_30_days")
        amphitheater = segment_cleaned is not None and segment_cleaned.lower() == "amphitheater"

        def value_for(rows: list[dict[str, Any]]) -> float:
            sales = sum(r["amphitheater_sales"] if amphitheater else r["sales"] for r in rows)
            orders = sum(r["orders"] for r in rows)
            tickets = sum(r["tickets"] for r in rows)
            traffic = sum(r["traffic"] for r in rows)
            if cleaned in {"sales", "gross"}:
                return round(sales, 2)
            if cleaned == "orders":
                return float(orders)
            if cleaned in {"tickets", "tickets_sold"}:
                return float(tickets)
            if cleaned == "traffic":
                return float(traffic)
            if cleaned in {"conversion", "conversion_rate"}:
                return round(orders / traffic * 100, 2) if traffic else 0.0
            if cleaned in {"average_order_value", "aov"}:
                return round(sales / orders, 2) if orders else 0.0
            if cleaned == "average_ticket_price":
                return round(sales / tickets, 2) if tickets else 0.0
            return round(sales, 2)

        if granularity == "week":
            points = [
                MetricPoint(
                    date=current[start]["date"], value=value_for(current[start : start + 7])
                )
                for start in range(0, len(current), 7)
            ]
        else:
            points = [MetricPoint(date=row["date"], value=value_for([row])) for row in current]
        unit = (
            self._currency
            if cleaned in _MONEY_METRICS
            else ("%" if cleaned in {"conversion", "conversion_rate"} else None)
        )
        return MetricSeries(
            metric="gross" if cleaned == "gross" else cleaned,
            unit=unit,
            granularity="week" if granularity == "week" else "day",
            period=label,
            segment="amphitheater" if amphitheater else segment_cleaned,
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
        portfolio = set(self._portfolio_ids())
        if ids := named_ids(query, portfolio):
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
            listings = [
                listing
                for p in products
                if p.product_id in portfolio and (listing := self._listing(p.product_id))
            ]
        return filter_listings(listings, filters, limit, sales_of=self.storefront.engine.sold)

    async def get_listing(
        self, session: MerchantSessionContext, listing_id: str
    ) -> ListingDetails | None:
        del session
        resolved = find_by_id(self._tier_event, listing_id)
        product = self.storefront.products.get(resolved) if resolved else None
        if product is None:
            return None
        listing = self._listing(product.product_id)
        if listing is None:
            return None
        row = self._state_row(product.product_id)
        pacing = self._tier_pacing(product.product_id) or {}
        weekly = pacing.get("recent_weekly_sales")
        return ListingDetails(
            **listing.model_dump(),
            long_description=product.long_description,
            review_snippets=product.review_highlights,
            sales_last_30d=round(weekly * 30 / 7) if weekly is not None else None,
            missing_attributes=row.get("missing_attributes") or [],
        )

    # ------------------------------------------------------------------
    # Inventory and order health
    # ------------------------------------------------------------------

    def _compute_alerts(self) -> list[InventoryAlert]:
        """``low_stock`` is a tier about to sell out; ``slow_mover`` is a tier pacing well
        under its baseline. ``stock`` is the engine's live open count."""
        alerts: list[InventoryAlert] = []
        for product_id in self._portfolio_ids():
            pacing = self._tier_pacing(product_id)
            if pacing is None:
                continue
            capacity = pacing["capacity"]
            remaining = pacing["remaining"]
            floor = max(_NEARLY_SOLD_OUT_FLOOR, capacity // 50)
            weekly = pacing.get("recent_weekly_sales")
            sales_30d = round(weekly * 30 / 7) if weekly is not None else None
            title = self.storefront.products[product_id].title
            if 0 < remaining <= floor:
                alerts.append(
                    InventoryAlert(
                        listing_id=product_id,
                        title=title,
                        kind="low_stock",
                        stock=remaining,
                        threshold=floor,
                        days_of_cover=round(remaining / (weekly / 7), 1) if weekly else None,
                        sales_last_30d=sales_30d,
                        storefront_visible=True,
                    )
                )
                continue
            pace = pacing.get("pace_vs_baseline_pts")
            if remaining > 0 and pace is not None and pace <= -_UNDER_PACE_ALERT_PTS:
                alerts.append(
                    InventoryAlert(
                        listing_id=product_id,
                        title=title,
                        kind="slow_mover",
                        stock=remaining,
                        threshold=None,
                        days_of_cover=None,
                        sales_last_30d=sales_30d,
                        storefront_visible=True,
                    )
                )
        # Under-pacing tiers are the actionable items for a promoter — list them ahead
        # of the nearly-sold-out notices, biggest open count (most at stake) first.
        alerts.sort(key=lambda alert: (alert.kind != "slow_mover", -alert.stock))
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

    def _fees_sum(self, product_id: str) -> float:
        product = self.storefront.products.get(product_id)
        if product is None:
            return 0.0
        return round(sum(float(product.attributes.get(attr, 0) or 0) for attr in _FEE_ATTRS), 2)

    def _unit_cost(self, product_id: str) -> float | None:
        """The fees at face plus the artist and house share of the face value."""
        product = self.storefront.products.get(product_id)
        if product is None:
            return None
        fees = self._fees_sum(product_id)
        face = float(product.attributes.get("face_price_usd", product.price - fees))
        return round(fees + face * _HOUSE_COST_SHARE, 2)

    async def get_pricing_context(
        self, session: MerchantSessionContext, listing_id: str
    ) -> PricingContext | None:
        del session
        resolved = find_by_id(self._tier_event, listing_id)
        if resolved is None:
            return None
        product = self.storefront.products[resolved]
        pacing = self._tier_pacing(resolved) or {}
        row = self._state_row(resolved)
        unit_cost = self._unit_cost(resolved)
        pace = pacing.get("pace_vs_baseline_pts")
        if pace is None:
            demand = "steady"
        elif pace <= -_UNDER_PACE_ALERT_PTS:
            demand = "falling"
        elif pace >= 10:
            demand = "rising"
        else:
            demand = "steady"
        fees = self._fees_sum(resolved)
        event_id = self._tier_event.get(resolved)
        return TierPricingContext(
            listing_id=resolved,
            current_price=product.price,
            currency=product.currency,
            unit_cost=unit_cost,
            margin_pct=margin_pct(product.price, unit_cost) if unit_cost else None,
            # The floor under any move: fees pass through untouched, and the face
            # value must keep covering the artist/house share.
            min_price=round(unit_cost * 1.05, 2) if unit_cost else None,
            max_price=round(product.price * 1.25, 2),
            max_price_delta_pct=self.config.max_price_delta_pct,
            max_promotion_discount_pct=self.config.max_promotion_discount_pct,
            demand_signal=demand,
            last_changed=row.get("last_price_change"),
            event_id=event_id,
            event_date=self._events[event_id]["event_date"] if event_id else None,
            days_to_event=self._days_to_event(event_id) if event_id else None,
            capacity=pacing.get("capacity"),
            sold=pacing.get("sold"),
            remaining=pacing.get("remaining"),
            sell_through_pct=pacing.get("sell_through_pct"),
            baseline_pct=pacing.get("baseline_pct"),
            pace_vs_baseline_pts=pace,
            waitlist_depth=pacing.get("waitlist_depth"),
            holds=pacing.get("holds", {}),
            fees_usd=fees,
            active_promotions=list(self.promo_windows.get(resolved, [])),
        )

    # ------------------------------------------------------------------
    # Staged writes
    # ------------------------------------------------------------------

    def _face_note(self, product_id: str, new_price: float) -> str:
        fees = self._fees_sum(product_id)
        product = self.storefront.products[product_id]
        old_face = float(product.attributes.get("face_price_usd", product.price - fees))
        return (
            f"{product_id}: all-in ${product.price:.2f} → ${new_price:.2f}; itemized fees "
            f"${fees:.2f} stay fixed, face value ${old_face:.2f} → ${new_price - fees:.2f}"
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
        """All-in price moves; a price at or under the fee lines is refused."""
        change_items = []
        margin_impact = 0.0
        margins: list[tuple[float, float]] = []
        notes: list[str] = []
        currency: str | None = None
        for item in items:
            # An id that resolves to nothing is refused, never staged as a dead item:
            # a no-op ChangeItem would dodge the fee floor and then "apply" as nothing.
            resolved = find_by_id(self._tier_event, item.listing_id)
            if resolved is None:
                raise ValueError(f"no listing {item.listing_id}")
            product = self.storefront.products[resolved]
            fees = self._fees_sum(resolved)
            if item.new_price <= fees:
                # A guardrail refusal, which the model can quote; not a tool failure.
                raise GuardrailViolation(
                    [
                        f"{resolved}: ${item.new_price:.2f} is at or below the ${fees:.2f} of "
                        "itemized pass-through fees — the face value would be zero or negative; "
                        "price above the fee floor"
                    ]
                )
            if currency is None:
                currency = product.currency
            pacing = self._tier_pacing(resolved) or {}
            weekly = pacing.get("recent_weekly_sales") or 0
            margin_impact += (item.new_price - product.price) * weekly
            unit_cost = self._unit_cost(resolved)
            if unit_cost is not None:
                margin_before = margin_pct(product.price, unit_cost)
                margin_after = margin_pct(item.new_price, unit_cost)
                margins.append((margin_before, margin_after))
            notes.append(self._face_note(resolved, item.new_price))
            change_items.append(
                ChangeItem(
                    target=resolved, field="price", before=product.price, after=item.new_price
                )
            )
        return self.ledger.stage(
            kind=ChangeKind.PRICE_UPDATE,
            summary=note or f"Price update for {len(items)} tier(s)",
            items=change_items,
            actor=session.operator,
            actor_kind=ActorKind.AGENT,
            currency=currency,
            margin_impact=round(margin_impact, 2),
            margin_before_pct=margins[0][0] if len(margins) == 1 else None,
            margin_after_pct=margins[0][1] if len(margins) == 1 else None,
            guardrail_notes=notes or None,
        )

    def _releasable(self, product_id: str) -> int:
        allocations = self._allocations.get(product_id, {})
        return sum(int(allocations.get(bucket, 0)) for bucket in _RELEASABLE_BUCKETS)

    async def stage_inventory_action(
        self,
        session: MerchantSessionContext,
        items: list[InventoryActionItem],
        note: str | None = None,
    ) -> StagedChange:
        """A restock releases seats from the promoter and production holds and carries
        the allocation book in its notes; comps and kills are not releasable, and pausing
        a tier is refused."""
        change_items = []
        notes: list[str] = []
        for item in items:
            resolved = find_by_id(self._tier_event, item.listing_id)
            if resolved is None:
                raise ValueError(f"no listing {item.listing_id}")
            if item.action != "restock":
                raise ChangeNotApplicable(
                    "ACME Tickets doesn't pause tiers mid-sale in this example — "
                    "right-size the room with hold releases and pricing instead."
                )
            quantity = item.quantity or 0
            releasable = self._releasable(resolved)
            allocations = self._allocations.get(resolved, {})
            if quantity < 1:
                raise GuardrailViolation(["a release needs a quantity of seats"])
            if quantity > releasable:
                # Same rule-refusal contract as the fee floor: the allocation math is
                # the answer, and it must reach the operator as a guardrail message.
                raise GuardrailViolation(
                    [
                        f"{resolved} has {releasable} releasable seats "
                        f"(promoter hold {allocations.get('promoter_hold', 0)}, production "
                        f"hold {allocations.get('production_hold', 0)}); comps and kills "
                        "can't be released — reduce the quantity"
                    ]
                )
            current = self.storefront.engine.capacity(resolved)
            promoter = int(allocations.get("promoter_hold", 0))
            from_promoter = min(quantity, promoter)
            from_production = quantity - from_promoter
            source = f"{from_promoter} from the {promoter}-seat promoter hold"
            if from_production:
                source += (
                    f" and {from_production} from the "
                    f"{int(allocations.get('production_hold', 0))}-seat production hold"
                )
            notes.append(
                f"{resolved}: releases {source}; comps "
                f"({int(allocations.get('comps', 0))}) and kills "
                f"({int(allocations.get('kills', 0))}) stay off sale"
            )
            change_items.append(
                ChangeItem(
                    target=resolved,
                    field="on_sale_capacity",
                    before=current,
                    after=current + quantity,
                )
            )
        return self.ledger.stage(
            kind=ChangeKind.INVENTORY_ACTION,
            summary=note or f"Release held seats on {len(items)} tier(s)",
            items=change_items,
            actor=session.operator,
            actor_kind=ActorKind.AGENT,
            guardrail_notes=notes or None,
        )

    async def stage_promotion(
        self, session: MerchantSessionContext, promotion: PromotionDraft
    ) -> StagedChange:
        """A dated price step, down (early bird) or up (closeout), recorded as a window
        when applied; the standing price does not move and ``nights`` is ignored."""
        try:
            window_days = max(
                1,
                (date.fromisoformat(promotion.ends) - date.fromisoformat(promotion.starts)).days
                + 1,
            )
        except ValueError:
            window_days = 7
        items = []
        margin_impact = 0.0
        margins: list[tuple[float, float]] = []
        notes: list[str] = []
        currency: str | None = None
        for listing_id in promotion.listing_ids:
            resolved = find_by_id(self._tier_event, listing_id)
            if resolved is None:
                raise ValueError(f"no listing {listing_id}")
            product = self.storefront.products[resolved]
            if currency is None:
                currency = product.currency
            fees = self._fees_sum(resolved)
            promo_price = round(product.price * (1 - promotion.discount_pct / 100), 2)
            if promo_price <= fees:
                raise GuardrailViolation(
                    [
                        f"{resolved}: the windowed price ${promo_price:.2f} is at or below the "
                        f"${fees:.2f} of itemized pass-through fees — use a shallower discount"
                    ]
                )
            pacing = self._tier_pacing(resolved) or {}
            weekly = pacing.get("recent_weekly_sales") or 0
            discount_value = product.price * promotion.discount_pct / 100
            margin_impact -= discount_value * weekly / 7 * window_days
            unit_cost = self._unit_cost(resolved)
            if unit_cost is not None:
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
        direction = "off" if promotion.discount_pct >= 0 else "step up on"
        change = self.ledger.stage(
            kind=ChangeKind.PROMOTION,
            summary=f"{promotion.name} ({abs(promotion.discount_pct):.0f}% {direction} "
            f"all-in prices, {promotion.starts} to {promotion.ends})",
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
        # Two releases staged against the same balances can each pass at stage time
        # and together exceed the buckets, so a release is re-checked at apply.
        pending = next(
            (change for change in self.ledger.pending() if change.change_id == change_id),
            None,
        )
        if pending is not None and pending.kind is ChangeKind.INVENTORY_ACTION:
            for item in pending.items:
                if item.field != "on_sale_capacity":
                    continue
                released = int(item.after) - int(item.before)
                releasable = self._releasable(item.target)
                if released > releasable:
                    raise GuardrailViolation(
                        [
                            f"{item.target} now has only {releasable} releasable seats "
                            f"(another release drained the holds since this was staged) — "
                            "re-stage the release at the current balance"
                        ]
                    )
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

    def _drain_release(self, product_id: str, quantity: int) -> None:
        """Take released seats out of the hold buckets, promoter hold first."""
        allocations = self._allocations.setdefault(product_id, {})
        remaining = quantity
        for bucket in _RELEASABLE_BUCKETS:
            take = min(int(allocations.get(bucket, 0)), remaining)
            if take:
                allocations[bucket] = int(allocations.get(bucket, 0)) - take
                remaining -= take
            if remaining == 0:
                break

    def _apply_to_live_state(self, change: StagedChange) -> None:
        """Write an applied change through: a release adds engine capacity; a price move
        updates the sticker and the face-value attribute together."""
        for item in change.items:
            product = self.storefront.products.get(item.target)
            if product is None:
                if change.kind is ChangeKind.CAMPAIGN:  # campaign items target campaign ids
                    apply_campaign_item(self._campaigns, item)
                continue
            row = self._state_row(item.target)
            if change.kind is ChangeKind.PRICE_UPDATE:
                fees = self._fees_sum(item.target)
                product.price = float(item.after)
                product.attributes["face_price_usd"] = f"{float(item.after) - fees:.2f}"
                row["last_price_change"] = datetime.now(UTC).date().isoformat()
            elif change.kind is ChangeKind.INVENTORY_ACTION and item.field == "on_sale_capacity":
                released = int(item.after) - int(item.before)
                if released > 0:
                    self.storefront.engine.add_capacity(item.target, released)
                    self._drain_release(item.target, released)
            elif change.kind is ChangeKind.LISTING_UPDATE:
                if item.field in {"title", "short_description", "long_description", "category"}:
                    setattr(product, item.field, item.after)
                elif item.field == "content_quality":
                    row["content_quality"] = item.after
                else:
                    product.attributes[item.field] = str(item.after)
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

    # ------------------------------------------------------------------
    # Merchant context
    # ------------------------------------------------------------------

    async def get_merchant_context(self, session: MerchantSessionContext) -> dict[str, Any] | None:
        counts = self._alert_counts()
        latest = self._daily[-1]["date"]
        week_start = (date.fromisoformat(latest) - timedelta(days=6)).isoformat()
        engine = self.storefront.engine
        return {
            "promoter": self.promoter_name,
            "box_office": self.storefront.store_name,
            "operator": session.operator,
            "current_period": f"{week_start}/{latest}",
            "events": [
                {
                    "event_id": event_id,
                    "event_date": event["event_date"],
                    "days_to_event": self._days_to_event(event_id),
                    "sold_out": all(
                        engine.remaining(tier["product_id"]) == 0 for tier in event["tiers"]
                    ),
                }
                for event_id, event in self._events.items()
            ],
            "alerts": {
                "under_pacing": counts.slow_movers,
                "nearly_sold_out": counts.low_stock,
                "fan_messages": counts.order_issues,
                "pending_changes": counts.pending_changes,
            },
        }
