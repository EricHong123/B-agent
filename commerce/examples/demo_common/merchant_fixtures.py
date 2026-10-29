# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Helpers the mock merchant backends share: fixture loading, the daily-metrics window
arithmetic, the returns window, listing lookup and filtering, campaign staging, the live
values a change is checked against at apply, and the promotion-window bookkeeping the portals chart. Vertical arithmetic (what a restock or a promotion means
for stock, rooms, lines, or seats) stays in each mock."""

from __future__ import annotations

import re
from collections.abc import Callable, Iterable, Mapping
from datetime import date, timedelta
from pathlib import Path
from typing import Any

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
    InventoryAlert,
    Listing,
    ListingFilters,
    MerchantAgentConfig,
    MerchantBackend,
    MerchantSessionContext,
    OrderIssue,
    PricingContext,
    ReturnLog,
    ReturnRecord,
    StagedChange,
)
from shopping_agent import ProductDetails

from .storefront_fixtures import anchored_shift, load_json, weeks_since

DailyRows = list[dict[str, Any]]

_ID_SEPARATORS = re.compile(r"[\s,;]+")
_BROWSE_QUERIES = {"", "*", "all"}
_LISTING_SORTS: dict[str, Callable[[Listing], Any]] = {
    "stock_asc": lambda listing: listing.stock,
    "price_desc": lambda listing: -listing.price,
    "price_asc": lambda listing: listing.price,
}


def _shift_day(day: str, delta: timedelta) -> str:
    return (date.fromisoformat(day) + delta).isoformat()


def load_campaigns(data_dir: Path) -> dict[str, Campaign]:
    raw = load_json(data_dir, "merchant_campaigns.json")
    delta = anchored_shift(raw)
    campaigns = {}
    for row in raw["campaigns"]:
        shifted = {key: _shift_day(row[key], delta) for key in ("starts", "ends") if row.get(key)}
        campaigns[row["campaign_id"]] = Campaign.model_validate(row | shifted)
    return campaigns


def load_issues(data_dir: Path) -> list[OrderIssue]:
    raw = load_json(data_dir, "merchant_messages.json")
    delta = anchored_shift(raw)
    issues = []
    for row in raw["issues"]:
        issue = OrderIssue.model_validate(row)
        if issue.opened_at is not None:
            issue = issue.model_copy(update={"opened_at": issue.opened_at + delta})
        issues.append(issue)
    return issues


def load_returns(
    data_dir: Path, lookup: Callable[[str], ProductDetails | None]
) -> list[ReturnRecord]:
    """``merchant_returns.json`` as records, dates shifted like the issues', each named
    with its listing's title and, for a variant, its family. An id the catalog does not
    resolve fails at boot."""
    raw = load_json(data_dir, "merchant_returns.json")
    delta = anchored_shift(raw)
    records = []
    for row in raw["returns"]:
        product = lookup(row["listing_id"])
        if product is None:
            raise ValueError(f"merchant_returns.json: unknown listing {row['listing_id']}")
        record = ReturnRecord.model_validate(
            row | {"title": product.title, "variant_of": product.variant_of}
        )
        records.append(record.model_copy(update={"returned_on": record.returned_on + delta}))
    return records


def returns_in_period(
    records: Iterable[ReturnRecord], period: str | None, end: date, listing_id: str | None
) -> ReturnLog:
    """The returns in a period ending on ``end``, the last metrics date, so a window here
    is the window ``metric_window`` reports for the same name: 30 days unless the period
    names 7 or 90 days or an ISO date range. A listing id narrows to that listing or
    family."""
    days = 30
    start = None
    cleaned = (period or "").strip().lower()
    if cleaned in {"last_7_days", "last 7 days", "7d", "this week"}:
        days = 7
    elif cleaned in {"last_90_days", "last 90 days", "90d", "quarter"}:
        days = 90
    elif "/" in cleaned:
        try:
            start_text, end_text = cleaned.split("/", 1)
            start, end = (
                date.fromisoformat(start_text.strip()),
                date.fromisoformat(end_text.strip()),
            )
        except ValueError:
            start = None
    if start is None or start > end:
        start = end - timedelta(days=days - 1)
    kept = [
        record
        for record in records
        if start <= record.returned_on <= end
        and (listing_id is None or listing_id in {record.listing_id, record.variant_of})
    ]
    return ReturnLog(period=f"{start.isoformat()}/{end.isoformat()}", records=kept)


def _rebase(rows: DailyRows, key: str) -> DailyRows:
    """A dated series shifted so its last row lands in the week before today; the
    series was written as if the day after its last row were today."""
    if not rows:
        return rows
    delta = weeks_since(date.fromisoformat(rows[-1][key]) + timedelta(days=1))
    if not delta:
        return rows
    return [{**row, key: _shift_day(row[key], delta)} for row in rows]


def rebase_daily(rows: DailyRows) -> DailyRows:
    return _rebase(rows, "date")


def rebase_weeks(rows: DailyRows) -> DailyRows:
    return _rebase(rows, "week_start")


def metric_window(rows: DailyRows, period: str | None) -> tuple[DailyRows, DailyRows, str]:
    """The rows for a period (7 days unless it names 30 or 90 days or an ISO date range)
    plus the prior window of the same length and the period's label."""
    days = 7
    if period:
        cleaned = period.strip().lower()
        if cleaned in {"last_30_days", "last 30 days", "30d"}:
            days = 30
        elif cleaned in {"last_90_days", "last 90 days", "90d", "quarter"}:
            days = min(90, len(rows))
        elif "/" in cleaned:
            try:
                start_text, end_text = cleaned.split("/", 1)
                start = date.fromisoformat(start_text.strip())
                end = date.fromisoformat(end_text.strip())
                selected = [r for r in rows if start <= date.fromisoformat(r["date"]) <= end]
                if selected:
                    days = len(selected)
                    end_index = rows.index(selected[-1]) + 1
                    prior = rows[max(0, end_index - 2 * days) : end_index - days]
                    return selected, prior, f"{selected[0]['date']}/{selected[-1]['date']}"
            except ValueError:
                days = 7
    current = rows[-days:]
    prior = rows[-2 * days : -days]
    return current, prior, f"{current[0]['date']}/{current[-1]['date']}"


def change_pct(current: float, prior: float) -> float | None:
    if prior <= 0:
        return None
    return round((current - prior) / prior * 100, 1)


def margin_pct(price: float, unit_cost: float) -> float:
    return round((price - unit_cost) / price * 100, 1)


def alert_counts(
    alerts: Iterable[InventoryAlert], issues: list[Any], ledger: ChangeLedger
) -> AlertCounts:
    alerts = list(alerts)
    return AlertCounts(
        low_stock=sum(1 for alert in alerts if alert.kind == "low_stock"),
        slow_movers=sum(1 for alert in alerts if alert.kind == "slow_mover"),
        order_issues=len(issues),
        pending_changes=len(ledger.pending()),
    )


def snapshot_of(
    rows: DailyRows,
    period: str | None,
    *,
    sales_key: str = "sales",
    orders_key: str = "orders",
    currency: str,
    alerts: AlertCounts,
) -> BusinessSnapshot:
    """The period's totals and their change against the prior window, from daily rows
    carrying a sales figure, an order count, and traffic under the given keys."""
    current, prior, label = metric_window(rows, period)
    sales = round(sum(r[sales_key] for r in current), 2)
    orders = sum(r[orders_key] for r in current)
    traffic = sum(r["traffic"] for r in current)
    prior_sales = round(sum(r[sales_key] for r in prior), 2) if prior else 0.0
    prior_orders = sum(r[orders_key] for r in prior) if prior else 0
    prior_traffic = sum(r["traffic"] for r in prior) if prior else 0
    conversion = round(orders / traffic * 100, 2) if traffic else 0.0
    prior_conversion = round(prior_orders / prior_traffic * 100, 2) if prior_traffic else 0.0
    return BusinessSnapshot(
        period=label,
        compare_to=f"{prior[0]['date']}/{prior[-1]['date']}" if prior else None,
        sales=sales,
        orders=orders,
        traffic=traffic,
        conversion_rate=conversion,
        average_order_value=round(sales / orders, 2) if orders else 0.0,
        sales_change_pct=change_pct(sales, prior_sales),
        orders_change_pct=change_pct(orders, prior_orders),
        traffic_change_pct=change_pct(traffic, prior_traffic),
        conversion_change_pct=change_pct(conversion, prior_conversion)
        if prior_conversion
        else None,
        currency=currency,
        alerts=alerts,
    )


def promotion_targets(products: Iterable[ProductDetails]) -> list[ProductDetails]:
    """The records a promotion prices: each plain product, and every variant of a family,
    once each, in the order named."""
    targets: list[ProductDetails] = []
    for product in products:
        for target in product.variants or [product]:
            if target not in targets:
                targets.append(target)
    return targets


def family_pricing_context(
    family: ProductDetails, variants: list[PricingContext], config: MerchantAgentConfig
) -> PricingContext:
    """A family's pricing context: the caps and the lowest variant price on the family row,
    one context per variant beneath it. Cost and margin live on the variants."""
    return PricingContext(
        listing_id=family.product_id,
        current_price=min((v.current_price for v in variants), default=family.price),
        currency=family.currency,
        max_price_delta_pct=config.max_price_delta_pct,
        max_promotion_discount_pct=config.max_promotion_discount_pct,
        variants=variants,
    )


# Content a variant shares with its family in these catalogs; an edit to it names the family.
FAMILY_CONTENT_FIELDS = frozenset({"title", "short_description", "long_description", "category"})


def refuse_outside_range(listing_id: str, new_price: float, context: PricingContext) -> None:
    """Raise when a new price falls outside the range ``get_pricing_context`` reported; the
    percentage caps are the guardrail's, the floor and ceiling are the backend's."""
    if context.min_price is not None and new_price < context.min_price:
        raise ChangeNotApplicable(
            f"{listing_id}: {new_price:.2f} is below the floor of {context.min_price:.2f} "
            f"({context.min_price_basis or 'store rule'})."
        )
    if context.max_price is not None and new_price > context.max_price:
        raise ChangeNotApplicable(
            f"{listing_id}: {new_price:.2f} is above the ceiling of {context.max_price:.2f}."
        )


def refuse_shared_content(listing: Listing, fields: Mapping[str, Any]) -> None:
    """Raise when a content edit names a variant for a field its family owns."""
    if listing.variant_of and (shared := set(fields) & FAMILY_CONTENT_FIELDS):
        raise ChangeNotApplicable(
            f"{', '.join(sorted(shared))} is shared by every variant of "
            f"{listing.variant_of}; stage the edit against {listing.variant_of}."
        )


def share_content(product: ProductDetails, field: str, value: Any) -> None:
    """Set a content field on a record and, for a family, on each of its variants, which
    carry the family's content fields in these catalogs."""
    for record in (product, *product.variants):
        setattr(record, field, value)


def named_ids(query: str, ids: Iterable[str]) -> list[str]:
    """The listing ids a query names outright, in query order. A query naming ids is a
    lookup: text scoring would rank a raw id poorly and leave it out of the session's
    provenance even though the operator named it."""
    by_fold = {listing_id.casefold(): listing_id for listing_id in ids}
    found = (by_fold.get(token.casefold()) for token in _ID_SEPARATORS.split(query.strip()))
    return list(dict.fromkeys(listing_id for listing_id in found if listing_id))


def is_browse(query: str) -> bool:
    return query.strip().lower() in _BROWSE_QUERIES


def filter_listings(
    listings: list[Listing],
    filters: ListingFilters | None,
    limit: int,
    *,
    sales_of: Callable[[str], float],
) -> list[Listing]:
    """Apply the shared listing filters and sort, then cut to ``limit``. ``sales_of``
    supplies the trailing sales figure the ``sales_desc`` sort ranks by."""
    if filters is None:
        return listings[:limit]
    if filters.status:
        listings = [listing for listing in listings if listing.status == filters.status]
    if filters.category:
        wanted = filters.category.lower()
        listings = [listing for listing in listings if wanted in (listing.category or "").lower()]
    if filters.max_stock is not None:
        listings = [listing for listing in listings if listing.stock <= filters.max_stock]
    if filters.content_quality:
        listings = [
            listing for listing in listings if listing.content_quality == filters.content_quality
        ]
    if filters.sort == "sales_desc":
        listings.sort(key=lambda listing: -sales_of(listing.listing_id))
    elif filters.sort in _LISTING_SORTS:
        listings.sort(key=_LISTING_SORTS[filters.sort])
    return listings[:limit]


def stage_campaign(
    ledger: ChangeLedger,
    campaigns: Mapping[str, Campaign],
    draft: CampaignDraft,
    *,
    actor: str,
    currency: str,
) -> StagedChange:
    """A campaign draft as change items: a budget item when the draft sets one or the
    campaign is new, plus the audience and copy the draft carries. A draft with none of
    these is refused."""
    existing = campaigns.get(draft.campaign_id) if draft.campaign_id else None
    target = draft.campaign_id or draft.name
    items = []
    if draft.budget is not None or existing is None:
        items.append(
            ChangeItem(
                target=target,
                field="budget",
                before=existing.budget if existing else None,
                after=draft.budget,
            )
        )
    for name in ("audience", "copy_text"):
        if value := getattr(draft, name):
            items.append(ChangeItem(target=target, field=name, before=None, after=value))
    if not items:
        raise ChangeNotApplicable(f"{target}: the draft changes no budget, audience, or copy.")
    return ledger.stage(
        kind=ChangeKind.CAMPAIGN,
        summary=f"Campaign draft: {draft.name}",
        items=items,
        actor=actor,
        actor_kind=ActorKind.AGENT,
        currency=currency,
    )


async def live_values(
    backend: MerchantBackend,
    session: MerchantSessionContext,
    change: StagedChange | None,
    campaigns: Mapping[str, Campaign],
) -> dict[tuple[str, str], object]:
    """The current value of each item ``change`` would write, read the way staging read
    its ``before``, for ``ChangeLedger.apply`` to compare. A restock, a campaign's
    audience, and its copy are not read: the first applies as a delta and the others are
    staged without a current value."""
    live: dict[tuple[str, str], object] = {}
    for item in change.items if change is not None else []:
        key = (item.target, item.field)
        if change.kind is ChangeKind.CAMPAIGN:
            if item.field == "budget":
                existing = campaigns.get(item.target)
                live[key] = existing.budget if existing else None
            continue
        if change.kind is ChangeKind.INVENTORY_ACTION and item.field != "status":
            continue
        listing = await backend.get_listing(session, item.target)
        if listing is None:
            live[key] = None
        elif change.kind in {ChangeKind.PRICE_UPDATE, ChangeKind.PROMOTION}:
            live[key] = listing.price
        elif change.kind is ChangeKind.INVENTORY_ACTION:
            live[key] = listing.status
        else:
            live[key] = getattr(listing, item.field, listing.attributes.get(item.field))
    return live


def apply_campaign_item(campaigns: dict[str, Campaign], item: ChangeItem) -> None:
    """An applied budget item updates the existing campaign; a new campaign's draft is
    recorded by the ledger only."""
    existing = campaigns.get(item.target)
    if existing is not None and item.field == "budget" and item.after is not None:
        campaigns[item.target] = existing.model_copy(update={"budget": float(item.after)})


def staged_promotion_windows(
    ledger: ChangeLedger, windows: Mapping[str, Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """The date windows of promotions still pending, keyed by the listings they touch,
    for the portal views that outline where an approved move would land."""
    pending = {change.change_id: change for change in ledger.pending()}
    result = []
    for change_id, window in windows.items():
        change = pending.get(change_id)
        if change is None:
            continue
        entry: dict[str, Any] = {
            "change_id": change_id,
            "name": window.get("name"),
            "starts": window.get("starts"),
            "ends": window.get("ends"),
        }
        if "nights" in window:
            entry["nights"] = window["nights"]
        entry["listing_ids"] = sorted({item.target for item in change.items})
        result.append(entry)
    return result
