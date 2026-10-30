# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The travel example's ``MerchantBackend``: the supplier fixtures in ``data/`` (booking
metrics, the occupancy calendar, campaigns, guest messages) overlaid on the ``MockTravel``
the storefront serves. A promotion is a date-window rate move that applies as a rate
override; a price update moves the base nightly rate, which is the catalog price."""

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

from .mock_travel import DATA_DIR, MockTravel, load_occupancy

# Pacing thresholds: average midweek occupancy below the first reads as soft; weekly
# occupancy at or above the second reads as nearly sold out.
_SOFT_MIDWEEK_PCT = 55
_NEARLY_SOLD_OUT_PCT = 93
_DEFAULT_ROOMS = 12
_MONEY_METRICS = {
    "sales",
    "revenue",
    "average_order_value",
    "aov",
    "average_booking_value",
    "adr",
    "average_daily_rate",
    "average_nightly_rate",
}


class StayPricingContext(PricingContext):
    """The pricing read plus the occupancy summary and active rate overrides a rate
    decision is grounded in."""

    price_unit: str = "per_night"
    occupancy_window: dict[str, Any] | None = None
    active_rate_overrides: list[dict[str, Any]] = []


class MockTravelMerchant(MerchantBackend):
    def __init__(
        self,
        storefront: MockTravel,
        config: MerchantAgentConfig | None = None,
        data_dir: Path = DATA_DIR,
    ) -> None:
        self.storefront = storefront
        self.config = config or MerchantAgentConfig(brand_name=storefront.store_name)
        self.ledger = ChangeLedger(self.config)
        metrics = load_json(data_dir, "merchant_metrics.json")
        self._daily = rebase_daily(metrics["daily"])
        self._currency: str = metrics.get("currency", "USD")
        # The calendar moves with the storefront's clock (load_occupancy in mock_travel),
        # so both sides read the same weeks.
        occupancy = load_occupancy(data_dir, storefront.today)
        self.supplier_name: str = occupancy.get("supplier", "ACME Travel supplier")
        self._occupancy_window: dict[str, str] = occupancy.get("window", {})
        self._occupancy: dict[str, dict[str, Any]] = {
            row["listing_id"]: dict(row) for row in occupancy["listings"]
        }
        self._today: dict[str, Any] = occupancy.get("today", {})
        self._campaigns = load_campaigns(data_dir)
        self._issues = load_issues(data_dir)
        self._returns = load_returns(data_dir, storefront.product)
        # Status and content state per listing, created on first touch.
        self._listing_state: dict[str, dict[str, Any]] = {}
        # Applied promotions, as rate overrides keyed by listing; pending promotions'
        # date windows, keyed by change id.
        self.rate_overrides: dict[str, list[dict[str, Any]]] = {}
        self._promotion_windows: dict[str, dict[str, Any]] = {}

    # ------------------------------------------------------------------
    # Listings
    # ------------------------------------------------------------------

    def _state_row(self, product_id: str) -> dict[str, Any]:
        if product_id not in self._listing_state:
            occupancy = self._occupancy.get(product_id, {})
            self._listing_state[product_id] = {
                "product_id": product_id,
                "rooms": int(occupancy.get("rooms", _DEFAULT_ROOMS)),
                "bookings_last_30d": int(occupancy.get("bookings_last_30d", 9)),
                "status": "active",
                "content_quality": "good",
            }
        return self._listing_state[product_id]

    def _listing(self, product_id: str) -> Listing | None:
        product = self.storefront.products.get(product_id)
        if product is None:
            return None
        row = self._state_row(product_id)
        status = row.get("status", "active")
        if status == "active" and not product.in_stock:
            status = "out_of_stock"
        return Listing(
            listing_id=product.product_id,
            title=product.title,
            status=status,
            price=product.price,
            currency=product.currency,
            stock=int(row.get("rooms", _DEFAULT_ROOMS)),
            category=product.category,
            content_quality=row.get("content_quality", "good"),
            attributes=product.attributes,
            image_url=product.image_url,
            short_description=product.short_description,
        )

    def _portfolio_ids(self) -> list[str]:
        return [lid for lid in self._occupancy if lid in self.storefront.products]

    def all_listings(self) -> list[Listing]:
        """The supplier's portfolio (the occupancy fixture's stays), not the marketplace."""
        listings = [
            listing
            for product_id in self._portfolio_ids()
            if (listing := self._listing(product_id)) is not None
        ]
        listings.sort(key=lambda listing: (listing.category or "", listing.listing_id))
        return listings

    # ------------------------------------------------------------------
    # Occupancy: the portfolio's date-bound view and the portal's reads of it
    # ------------------------------------------------------------------

    @staticmethod
    def _week_overlaps(week_start: date, start: date, end: date) -> bool:
        return week_start <= end and week_start + timedelta(days=6) >= start

    def _override_for(self, listing_id: str, week_start: date) -> dict[str, Any] | None:
        """The most recently applied rate override whose window overlaps this week."""
        for override in reversed(self.rate_overrides.get(listing_id, [])):
            try:
                starts = date.fromisoformat(override["starts"])
                ends = date.fromisoformat(override["ends"])
            except (TypeError, ValueError):
                continue
            if self._week_overlaps(week_start, starts, ends):
                return override
        return None

    async def get_occupancy_calendar(
        self, listing_ids: list[str], start: date, end: date
    ) -> list[dict[str, Any]]:
        """Weekly occupancy, pace, and effective nightly rate per known portfolio stay
        over the window."""
        rows: list[dict[str, Any]] = []
        for listing_id in listing_ids:
            occupancy = self._occupancy.get(listing_id)
            product = self.storefront.products.get(listing_id)
            if occupancy is None or product is None:
                continue
            weeks: list[dict[str, Any]] = []
            for week in occupancy["weeks"]:
                week_start = date.fromisoformat(week["week_start"])
                if not self._week_overlaps(week_start, start, end):
                    continue
                override = self._override_for(listing_id, week_start)
                entry: dict[str, Any] = {
                    "week_start": week["week_start"],
                    "nightly_rate": override["nightly_rate"] if override else product.price,
                    "occupancy_pct": week["occupancy_pct"],
                    "midweek_occupancy_pct": week["midweek_occupancy_pct"],
                    "weekend_occupancy_pct": week["weekend_occupancy_pct"],
                    "on_the_books_pace_pct": week["on_the_books_pace_pct"],
                }
                if override is not None:
                    entry["override"] = {
                        "starts": override["starts"],
                        "ends": override["ends"],
                        "nightly_rate": override["nightly_rate"],
                        "change_id": override.get("change_id"),
                    }
                weeks.append(entry)
            rows.append(
                {
                    "listing_id": listing_id,
                    "title": product.title,
                    "rooms": int(occupancy.get("rooms", _DEFAULT_ROOMS)),
                    "base_nightly_rate": product.price,
                    "currency": product.currency,
                    "weeks": weeks,
                }
            )
        return rows

    def today_snapshot(self) -> dict[str, Any] | None:
        """Today's arrivals, departures, and new bookings for the portal home page."""
        if not self._today:
            return None

        def block(kind: str) -> dict[str, Any]:
            entries = self._today.get(kind) or []
            properties: list[str] = []
            count = 0
            for entry in entries:
                product = self.storefront.products.get(entry.get("listing_id", ""))
                if product is None:
                    continue
                count += int(entry.get("count", 0))
                properties.append(product.title)
            return {"count": count, "properties": properties}

        return {
            "arrivals": block("arrivals"),
            "departures": block("departures"),
            "new_bookings": block("new_bookings"),
        }

    async def occupancy_overview(self) -> dict[str, Any]:
        """The portal's occupancy read: every portfolio property's weekly occupancy over
        the full fixture window, plus staged promotion windows. Portal chrome only."""
        try:
            start = date.fromisoformat(self._occupancy_window.get("from", ""))
            end = date.fromisoformat(self._occupancy_window.get("to", ""))
        except (TypeError, ValueError):
            start = end = datetime.now(UTC).date()
        rows = await self.get_occupancy_calendar(self._portfolio_ids(), start, end)
        return {
            "window": {"from": start.isoformat(), "to": end.isoformat()},
            "properties": rows,
            "staged_windows": self.staged_promotion_windows(),
        }

    def staged_promotion_windows(self) -> list[dict[str, Any]]:
        return staged_promotion_windows(self.ledger, self._promotion_windows)

    def _occupancy_summary(self, listing_id: str) -> dict[str, Any] | None:
        occupancy = self._occupancy.get(listing_id)
        if occupancy is None:
            return None
        weeks = occupancy["weeks"]
        if not weeks:
            return None
        soft_weeks = [
            w["week_start"] for w in weeks if w["midweek_occupancy_pct"] < _SOFT_MIDWEEK_PCT
        ]
        # The average names its 30-day basis; the calendar shows per-week pace beside it.
        window_from = self._occupancy_window.get("from")
        try:
            cutoff = date.fromisoformat(window_from) + timedelta(days=30) if window_from else None
        except ValueError:
            cutoff = None
        pace_weeks = (
            [w for w in weeks if date.fromisoformat(w["week_start"]) < cutoff]
            if cutoff is not None
            else weeks
        ) or weeks
        return {
            "from": self._occupancy_window.get("from"),
            "to": self._occupancy_window.get("to"),
            "grain": "week",
            "average_occupancy_pct": round(sum(w["occupancy_pct"] for w in weeks) / len(weeks), 1),
            "average_midweek_occupancy_pct": round(
                sum(w["midweek_occupancy_pct"] for w in weeks) / len(weeks), 1
            ),
            "average_weekend_occupancy_pct": round(
                sum(w["weekend_occupancy_pct"] for w in weeks) / len(weeks), 1
            ),
            "average_on_the_books_pace_30d_pct": round(
                sum(w["on_the_books_pace_pct"] for w in pace_weeks) / len(pace_weeks), 1
            ),
            "soft_midweek_weeks": soft_weeks,
        }

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
            self._daily,
            period,
            sales_key="revenue",
            orders_key="bookings",
            currency=self._currency,
            alerts=self._alert_counts(),
        )

    async def query_metrics(
        self,
        session: MerchantSessionContext,
        metric: str,
        period: str | None = None,
        granularity: str = "day",
        segment: str | None = None,
    ) -> MetricSeries:
        del session
        current, _, label = metric_window(self._daily, period or "last_30_days")
        cleaned = metric.strip().lower().replace(" ", "_")
        segment_cleaned = (segment or "").strip().lower().replace(" ", "-") or None

        def value_for(rows: list[dict[str, Any]]) -> float:
            """The metric over one bucket of daily rows (a single day or a week) — ratio
            metrics are recomputed from the bucket's totals, never summed per day."""
            revenue = sum(r["revenue"] for r in rows)
            bookings = sum(r["bookings"] for r in rows)
            room_nights = sum(r["room_nights"] for r in rows)
            traffic = sum(r["traffic"] for r in rows)
            if segment_cleaned == "lisbon" and cleaned in {"sales", "revenue"}:
                return round(sum(r["lisbon_revenue"] for r in rows), 2)
            if cleaned in {"sales", "revenue"}:
                return round(revenue, 2)
            if cleaned in {"orders", "bookings"}:
                return float(bookings)
            if cleaned == "room_nights":
                return float(room_nights)
            if cleaned == "traffic":
                return float(traffic)
            if cleaned in {"conversion", "conversion_rate"}:
                return round(bookings / traffic * 100, 2) if traffic else 0.0
            if cleaned in {"average_order_value", "aov", "average_booking_value"}:
                return round(revenue / bookings, 2) if bookings else 0.0
            if cleaned in {"adr", "average_daily_rate", "average_nightly_rate"}:
                return round(revenue / room_nights, 2) if room_nights else 0.0
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
        unit = self._currency if cleaned in _MONEY_METRICS else None
        return MetricSeries(
            metric=cleaned,
            unit=unit,
            granularity="week" if granularity == "week" else "day",
            period=label,
            segment=segment_cleaned,
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
            # Search wide, then keep the portfolio: the storefront ranks flights and
            # experiences beside stays, so a limit applied first can drop every property.
            products = await self.storefront.search_products(
                shopper, query, SearchFilters(), limit=len(self.storefront.products)
            )
            listings = [
                listing
                for p in products
                if p.product_id in portfolio and (listing := self._listing(p.product_id))
            ][: max(limit, 8)]
        return filter_listings(
            listings,
            filters,
            limit,
            sales_of=lambda listing_id: self._state_row(listing_id).get("bookings_last_30d") or 0,
        )

    async def get_listing(
        self, session: MerchantSessionContext, listing_id: str
    ) -> ListingDetails | None:
        del session
        resolved = find_by_id(self.storefront.products, listing_id)
        listing = self._listing(resolved) if resolved else None
        if resolved is None or listing is None:
            return None
        product = self.storefront.products[resolved]
        row = self._state_row(resolved)
        return ListingDetails(
            **listing.model_dump(),
            long_description=product.long_description,
            review_snippets=product.review_highlights,
            sales_last_30d=row.get("bookings_last_30d"),
            missing_attributes=row.get("missing_attributes") or [],
        )

    # ------------------------------------------------------------------
    # Inventory and order health
    # ------------------------------------------------------------------

    def _compute_alerts(self) -> list[InventoryAlert]:
        """``slow_mover`` is a stay pacing soft midweek over a coming window; ``low_stock``
        is a stay nearly sold out. ``stock`` is the open room-nights in the flagged window
        and ``days_of_cover`` how long they last at the trailing booking pace."""
        alerts: list[InventoryAlert] = []
        for listing_id in self._portfolio_ids():
            product = self.storefront.products[listing_id]
            occupancy = self._occupancy[listing_id]
            row = self._state_row(listing_id)
            rooms = int(row.get("rooms", _DEFAULT_ROOMS))
            nightly_pace = (row.get("bookings_last_30d") or 0) / 30
            weeks = occupancy["weeks"]
            soft_weeks = [w for w in weeks if w["midweek_occupancy_pct"] < _SOFT_MIDWEEK_PCT]
            if soft_weeks:
                avg_midweek = sum(w["midweek_occupancy_pct"] for w in soft_weeks) / len(soft_weeks)
                open_midweek_nights = round(rooms * 5 * len(soft_weeks) * (1 - avg_midweek / 100))
                alerts.append(
                    InventoryAlert(
                        listing_id=listing_id,
                        title=product.title,
                        kind="slow_mover",
                        stock=open_midweek_nights,
                        threshold=rooms,
                        days_of_cover=(
                            round(open_midweek_nights / nightly_pace, 1) if nightly_pace else None
                        ),
                        sales_last_30d=row.get("bookings_last_30d"),
                    )
                )
                continue
            tight_weeks = [w for w in weeks if w["occupancy_pct"] >= _NEARLY_SOLD_OUT_PCT]
            if tight_weeks:
                peak = max(w["occupancy_pct"] for w in tight_weeks)
                open_nights = round(rooms * 7 * len(tight_weeks) * (1 - peak / 100))
                alerts.append(
                    InventoryAlert(
                        listing_id=listing_id,
                        title=product.title,
                        kind="low_stock",
                        stock=open_nights,
                        threshold=rooms,
                        days_of_cover=round(open_nights / nightly_pace, 1)
                        if nightly_pace
                        else None,
                        sales_last_30d=row.get("bookings_last_30d"),
                    )
                )
        # Soft-pacing windows are the actionable items for a stays supplier — list them
        # ahead of the nearly-sold-out notices.
        alerts.sort(key=lambda alert: (alert.kind != "slow_mover", alert.stock))
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

    def _nightly_cost(self, listing_id: str) -> float:
        """A simple per-night operating cost estimate for margin math in the example."""
        product = self.storefront.products[listing_id]
        return round(product.price * 0.42, 2)

    async def get_pricing_context(
        self, session: MerchantSessionContext, listing_id: str
    ) -> PricingContext | None:
        del session
        product = self.storefront.products.get(listing_id)
        if product is None:
            return None
        row = self._state_row(listing_id)
        unit_cost = self._nightly_cost(listing_id)
        margin_pct = round((product.price - unit_cost) / product.price * 100, 1)
        summary = self._occupancy_summary(listing_id)
        if summary is None:
            demand = "steady"
        else:
            pace = summary["average_on_the_books_pace_30d_pct"]
            demand = "falling" if pace < 0 else "rising" if pace > 5 else "steady"
        return StayPricingContext(
            listing_id=listing_id,
            current_price=product.price,
            currency=product.currency,
            unit_cost=unit_cost,
            margin_pct=margin_pct,
            min_price=round(unit_cost * 1.15, 2),
            max_price=round(product.price * 1.3, 2),
            max_price_delta_pct=self.config.max_price_delta_pct,
            max_promotion_discount_pct=self.config.max_promotion_discount_pct,
            demand_signal=demand,
            last_changed=row.get("last_rate_change"),
            occupancy_window=summary,
            active_rate_overrides=list(self.rate_overrides.get(listing_id, [])),
        )

    # ------------------------------------------------------------------
    # Staged writes
    # ------------------------------------------------------------------

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
        """Base nightly-rate changes: the listing's standing price, not a date window."""
        change_items = []
        margin_impact = 0.0
        # Before/after margins are computed here, from the per-night cost model — the
        # staged record is the only source the agent may quote margin figures from.
        margins: list[tuple[float, float]] = []
        margin_notes: list[str] = []
        currency: str | None = None
        for item in items:
            # An id that resolves to nothing is refused: staged, it would preview cleanly
            # and then apply as a silent no-op.
            resolved = find_by_id(self.storefront.products, item.listing_id)
            if resolved is None:
                raise ValueError(f"no listing {item.listing_id}")
            product = self.storefront.products[resolved]
            before = product.price
            if currency is None:
                currency = product.currency
            row = self._state_row(resolved)
            nightly_pace = (row.get("bookings_last_30d") or 0) / 30
            margin_impact += (item.new_price - before) * nightly_pace * 7
            nightly_cost = self._nightly_cost(resolved)
            margin_before = margin_pct(before, nightly_cost)
            margin_after = margin_pct(item.new_price, nightly_cost)
            margins.append((margin_before, margin_after))
            margin_notes.append(
                f"{resolved} margin: {margin_before}% → {margin_after}% "
                f"({margin_after - margin_before:+.1f} pts)"
            )
            change_items.append(
                ChangeItem(target=resolved, field="price", before=before, after=item.new_price)
            )
        return self.ledger.stage(
            kind=ChangeKind.PRICE_UPDATE,
            summary=note or f"Base nightly-rate update for {len(items)} listing(s)",
            items=change_items,
            actor=session.operator,
            actor_kind=ActorKind.AGENT,
            currency=currency,
            margin_impact=round(margin_impact, 2),
            margin_before_pct=margins[0][0] if len(margins) == 1 else None,
            margin_after_pct=margins[0][1] if len(margins) == 1 else None,
            guardrail_notes=margin_notes if len(margins) > 1 else None,
        )

    async def stage_inventory_action(
        self,
        session: MerchantSessionContext,
        items: list[InventoryActionItem],
        note: str | None = None,
    ) -> StagedChange:
        """Availability actions: ``restock`` releases more rooms to the marketplace,
        pause/activate toggles whether the listing is bookable at all."""
        change_items = []
        for item in items:
            resolved = find_by_id(self.storefront.products, item.listing_id)
            if resolved is None:
                raise ValueError(f"no listing {item.listing_id}")
            row = self._state_row(resolved)
            if item.action == "restock":
                current: Any = int(row.get("rooms", _DEFAULT_ROOMS))
                after: Any = current + (item.quantity or 0)
                field = "rooms"
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
        """A nightly-rate move for a date window, recorded as an override when applied;
        the base rate does not move."""
        try:
            window_days = max(
                1,
                (date.fromisoformat(promotion.ends) - date.fromisoformat(promotion.starts)).days
                + 1,
            )
        except ValueError:
            window_days = 7
        # A move limited to some nights of the week earns that share of the week's pace.
        night_share = len(promotion.nights) / 7 if promotion.nights else 1.0
        items = []
        margin_impact = 0.0
        margins: list[tuple[float, float]] = []
        margin_notes: list[str] = []
        currency: str | None = None
        for requested_id in promotion.listing_ids:
            listing_id = find_by_id(self.storefront.products, requested_id)
            if listing_id is None:
                raise ValueError(f"no listing {requested_id}")
            product = self.storefront.products[listing_id]
            if currency is None:
                currency = product.currency
            row = self._state_row(listing_id)
            nightly_pace = (row.get("bookings_last_30d") or 0) / 30
            discount_value = product.price * promotion.discount_pct / 100
            margin_impact -= discount_value * nightly_pace * window_days * night_share
            promo_rate = round(product.price * (1 - promotion.discount_pct / 100), 2)
            if promo_rate > 0:
                nightly_cost = self._nightly_cost(listing_id)
                margin_before = margin_pct(product.price, nightly_cost)
                margin_after = margin_pct(promo_rate, nightly_cost)
                margins.append((margin_before, margin_after))
                margin_notes.append(
                    f"{listing_id} margin: {margin_before}% → {margin_after}% "
                    f"({margin_after - margin_before:+.1f} pts) for the window"
                )
            items.append(
                ChangeItem(
                    target=listing_id,
                    field="nightly_rate",
                    before=product.price,
                    after=promo_rate,
                )
            )
        direction = "off" if promotion.discount_pct >= 0 else "increase on"
        nights_note = f", {'/'.join(promotion.nights)} nights" if promotion.nights else ""
        change = self.ledger.stage(
            kind=ChangeKind.PROMOTION,
            summary=f"{promotion.name} ({abs(promotion.discount_pct):.0f}% {direction} "
            f"nightly rates, {promotion.starts} to {promotion.ends}{nights_note})",
            items=items,
            actor=session.operator,
            actor_kind=ActorKind.AGENT,
            currency=currency,
            margin_impact=round(margin_impact, 2),
            margin_before_pct=margins[0][0] if len(margins) == 1 else None,
            margin_after_pct=margins[0][1] if len(margins) == 1 else None,
            guardrail_notes=margin_notes if len(margins) > 1 else None,
        )
        self._promotion_windows[change.change_id] = {
            "starts": promotion.starts,
            "ends": promotion.ends,
            "discount_pct": promotion.discount_pct,
            "name": promotion.name,
            "nights": list(promotion.nights) if promotion.nights else None,
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
        # A discarded promotion will never apply, so its date window has nothing left to do.
        self._promotion_windows.pop(change_id, None)
        return discarded

    def _apply_to_live_state(self, change: StagedChange) -> None:
        """Make an approved change visible in the shared traveler-facing state."""
        for item in change.items:
            product = self.storefront.products.get(item.target)
            if product is not None and change.kind in {
                ChangeKind.PRICE_UPDATE,
                ChangeKind.INVENTORY_ACTION,
                ChangeKind.LISTING_UPDATE,
            }:
                row = self._state_row(item.target)
                if change.kind is ChangeKind.PRICE_UPDATE:
                    # The base nightly rate is the shared catalog price.
                    product.price = float(item.after)
                    row["last_rate_change"] = datetime.now(UTC).date().isoformat()
                elif change.kind is ChangeKind.INVENTORY_ACTION:
                    if item.field == "rooms":
                        # Apply the staged delta rather than the staged total, so two
                        # releases staged against the same room count both count.
                        row["rooms"] = int(row.get("rooms", _DEFAULT_ROOMS)) + (
                            int(item.after) - int(item.before or 0)
                        )
                        product.in_stock = row["rooms"] > 0 and row.get("status") != "paused"
                    elif item.field == "status":
                        row["status"] = "paused" if item.after == "paused" else "active"
                        product.in_stock = item.after != "paused" and int(row.get("rooms", 1)) > 0
                else:  # LISTING_UPDATE
                    if item.field in {"title", "short_description", "long_description", "category"}:
                        setattr(product, item.field, item.after)
                    elif item.field == "content_quality":
                        row["content_quality"] = item.after
                    else:
                        product.attributes[item.field] = str(item.after)
            elif change.kind is ChangeKind.PROMOTION:
                # A date-window rate adjustment becomes a recorded override; the base
                # nightly rate (the shared product price) is untouched.
                window = self._promotion_windows.get(change.change_id, {})
                self.rate_overrides.setdefault(item.target, []).append(
                    {
                        "starts": window.get("starts"),
                        "ends": window.get("ends"),
                        "nights": window.get("nights"),
                        "nightly_rate": float(item.after),
                        "base_nightly_rate": float(item.before)
                        if item.before is not None
                        else None,
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
            "supplier": self.supplier_name,
            "marketplace": self.storefront.store_name,
            "operator": session.operator,
            "current_period": f"{week_start}/{latest}",
            "portfolio_listings": self._portfolio_ids(),
            "occupancy_window": self._occupancy_window,
            "alerts": {
                "soft_pacing": counts.slow_movers,
                "nearly_sold_out": counts.low_stock,
                "guest_messages": counts.order_issues,
                "pending_changes": counts.pending_changes,
            },
        }
