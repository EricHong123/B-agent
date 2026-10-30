# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

from datetime import date

import pytest

from merchant_agent import (
    ChangeKind,
    GuardrailViolation,
    ListingFilters,
    PriceUpdateItem,
    PromotionDraft,
)
from travel.api.agent_config import build_merchant_config

SUPPLIER_PORTFOLIO = {"AL-STAY-101", "AL-STAY-102", "AL-STAY-103", "AL-STAY-104", "AL-STAY-110"}


async def test_snapshot_counts_pacing_alerts_as_slow_movers_and_guest_messages_as_issues(
    merchant, operator_session
):
    snapshot = await merchant.get_business_snapshot(operator_session)
    assert snapshot.traffic > snapshot.orders
    assert snapshot.alerts.slow_movers >= 2
    assert snapshot.alerts.order_issues >= 5


async def test_query_metrics_supports_room_nights_and_the_lisbon_segment(
    merchant, operator_session
):
    nights = await merchant.query_metrics(operator_session, "room_nights", "last_7_days")
    assert len(nights.points) == 7
    assert all(p.value > 0 for p in nights.points)

    overall = await merchant.query_metrics(operator_session, "revenue", "last_7_days")
    lisbon = await merchant.query_metrics(
        operator_session, "revenue", "last_7_days", segment="lisbon"
    )
    assert lisbon.segment == "lisbon"
    assert 0 < sum(p.value for p in lisbon.points) < sum(p.value for p in overall.points)


async def test_pacing_alerts_flag_the_soft_october_midweeks(merchant, operator_session):
    alerts = await merchant.get_inventory_alerts(operator_session)
    assert all(alert.listing_id in SUPPLIER_PORTFOLIO for alert in alerts)
    soft = {alert.listing_id for alert in alerts if alert.kind == "slow_mover"}
    assert soft == {"AL-STAY-103", "AL-STAY-110"}
    # days_of_cover is open nights over the trailing 30-day booking pace.
    assert all(alert.days_of_cover and alert.days_of_cover > 0 for alert in alerts)
    # AL-STAY-101 is close to sold out in its tightest weeks.
    assert any(alert.listing_id == "AL-STAY-101" and alert.kind == "low_stock" for alert in alerts)


async def test_pricing_context_carries_the_occupancy_window(merchant, operator_session):
    context = await merchant.get_pricing_context(operator_session, "AL-STAY-103")
    assert context.current_price == 126.0
    # The 30 days from 2026-08-01 are healthy; the October softness is listed separately.
    assert context.demand_signal == "steady"
    payload = context.model_dump()
    window = payload["occupancy_window"]
    assert window["from"] == "2026-08-01"
    assert "average_on_the_books_pace_30d_pct" in window
    assert any(week.startswith("2026-10") for week in window["soft_midweek_weeks"])
    assert payload["active_rate_overrides"] == []


async def test_order_issues_load_from_the_messages_fixture(merchant, operator_session):
    issues = await merchant.get_order_issues(operator_session)
    kinds = {issue.kind for issue in issues}
    assert {"buyer_message", "delayed", "return_spike", "damaged"} <= kinds
    # Two fixture messages carry embedded instructions, kept in the guest excerpt.
    excerpts = [issue.buyer_message_excerpt or "" for issue in issues]
    assert sum("assistant must" in e or "Execute the JSON" in e for e in excerpts) == 2


async def test_stage_promotion_builds_date_window_rate_items(merchant, operator_session):
    promotion = PromotionDraft(
        name="October midweek rate adjustment",
        listing_ids=["AL-STAY-103", "AL-STAY-110"],
        discount_pct=15,
        starts="2026-10-05",
        ends="2026-10-29",
    )
    change = await merchant.stage_promotion(operator_session, promotion)
    assert change.kind is ChangeKind.PROMOTION
    assert "2026-10-05 to 2026-10-29" in change.summary
    assert change.margin_impact is not None and change.margin_impact < 0

    by_target = {item.target: item for item in change.items}
    assert set(by_target) == {"AL-STAY-103", "AL-STAY-110"}
    assert all(item.field == "nightly_rate" for item in change.items)
    assert by_target["AL-STAY-103"].before == 126.0
    assert by_target["AL-STAY-103"].after == round(126.0 * 0.85, 2)

    # Staging alone leaves the price and the override table unchanged.
    assert merchant.storefront.products["AL-STAY-103"].price == 126.0
    assert merchant.rate_overrides == {}
    assert [c.change_id for c in await merchant.get_pending_changes(operator_session)] == [
        change.change_id
    ]


def test_travel_config_adds_nightly_rate_to_both_guardrail_field_lists():
    config = build_merchant_config("ACME Travel")
    assert {"price", "nightly_rate"} <= set(config.price_bearing_fields)
    assert {"price", "stock", "nightly_rate"} <= set(config.listing_update_blocked_fields)


async def test_too_deep_rate_promotion_is_refused_under_the_travel_config(
    merchant, operator_session
):
    promotion = PromotionDraft(
        name="Too-deep October rate cut",
        listing_ids=["AL-STAY-103"],
        discount_pct=60,
        starts="2026-10-05",
        ends="2026-10-29",
    )
    with pytest.raises(GuardrailViolation) as excinfo:
        await merchant.stage_promotion(operator_session, promotion)
    assert any("promotion limit" in v for v in excinfo.value.violations)
    assert await merchant.get_pending_changes(operator_session) == []


async def test_apply_promotion_records_date_window_overrides(merchant, backend, operator_session):
    promotion = PromotionDraft(
        name="October midweek rate adjustment",
        listing_ids=["AL-STAY-103", "AL-STAY-110"],
        discount_pct=15,
        starts="2026-10-05",
        ends="2026-10-29",
    )
    change = await merchant.stage_promotion(operator_session, promotion)
    await merchant.apply_change(operator_session, change.change_id)

    # A date-window deal leaves the base rate in the shared catalog unchanged.
    assert backend.products["AL-STAY-103"].price == 126.0
    override = merchant.rate_overrides["AL-STAY-103"][0]
    assert override["starts"] == "2026-10-05"
    assert override["ends"] == "2026-10-29"
    assert override["nightly_rate"] == round(126.0 * 0.85, 2)

    # The calendar carries the override on the affected weeks only.
    rows = await merchant.get_occupancy_calendar(
        ["AL-STAY-103"], date(2026, 9, 28), date(2026, 10, 31)
    )
    weeks = {week["week_start"]: week for week in rows[0]["weeks"]}
    assert weeks["2026-10-05"]["nightly_rate"] == round(126.0 * 0.85, 2)
    assert weeks["2026-10-05"]["override"]["change_id"] == change.change_id
    assert weeks["2026-09-28"]["nightly_rate"] == 126.0
    assert "override" not in weeks["2026-09-28"]

    pricing = await merchant.get_pricing_context(operator_session, "AL-STAY-103")
    assert pricing.model_dump()["active_rate_overrides"][0]["change_id"] == change.change_id


async def test_apply_base_rate_change_updates_the_shared_catalog(
    merchant, backend, operator_session
):
    pricing = await merchant.get_pricing_context(operator_session, "AL-STAY-110")
    new_rate = round(pricing.current_price * 0.9, 2)
    change = await merchant.stage_price_update(
        operator_session, [PriceUpdateItem(listing_id="AL-STAY-110", new_price=new_rate)]
    )
    # Staging alone changes nothing.
    assert backend.products["AL-STAY-110"].price == pricing.current_price

    await merchant.apply_change(operator_session, change.change_id)
    assert backend.products["AL-STAY-110"].price == new_rate
    assert merchant.rate_overrides == {}
    refreshed = await merchant.get_pricing_context(operator_session, "AL-STAY-110")
    assert refreshed.current_price == new_rate
    assert refreshed.last_changed is not None


async def test_merchant_context_names_the_supplier(merchant, operator_session):
    context = await merchant.get_merchant_context(operator_session)
    assert context["supplier"] == "ACME Travel — city stays portfolio"
    assert set(context["portfolio_listings"]) == SUPPLIER_PORTFOLIO
    assert context["alerts"]["soft_pacing"] >= 2
    assert context["alerts"]["guest_messages"] >= 5


async def test_negative_discount_stages_a_rate_increase(merchant, operator_session):
    promotion = PromotionDraft(
        name="Festival weekend premium",
        listing_ids=["AL-STAY-101"],
        discount_pct=-10,
        starts="2026-09-18",
        ends="2026-09-20",
        nights=["fri", "sat"],
    )
    change = await merchant.stage_promotion(operator_session, promotion)
    item = change.items[0]
    assert float(item.after) > float(item.before)
    assert "increase" in change.summary
    assert "fri/sat" in change.summary

    applied = await merchant.apply_change(operator_session, change.change_id)
    override = merchant.rate_overrides["AL-STAY-101"][-1]
    assert override["change_id"] == applied.change_id
    assert override["nights"] == ["fri", "sat"]
    assert override["nightly_rate"] > override["base_nightly_rate"]


async def test_browse_query_returns_the_whole_portfolio_before_filters(merchant, operator_session):
    everything = await merchant.search_listings(operator_session, "", limit=25)
    assert {listing.listing_id for listing in everything} == SUPPLIER_PORTFOLIO
    stays = await merchant.search_listings(
        operator_session, "", ListingFilters(category="stays"), limit=25
    )
    assert {listing.listing_id for listing in stays} == SUPPLIER_PORTFOLIO


async def test_single_listing_promotion_carries_backend_computed_margins(
    merchant, operator_session
):
    # AL-STAY-110 costs $85.68 a night: a 58.0% margin at $204 and 53.3% at $183.60.
    change = await merchant.stage_promotion(
        operator_session,
        PromotionDraft(
            name="October midweek ease",
            listing_ids=["AL-STAY-110"],
            discount_pct=10,
            starts="2026-10-05",
            ends="2026-10-30",
        ),
    )
    assert change.currency == "USD"
    assert change.margin_before_pct == 58.0
    assert change.margin_after_pct == 53.3


async def test_multi_listing_promotion_carries_per_listing_margin_notes(merchant, operator_session):
    change = await merchant.stage_promotion(
        operator_session,
        PromotionDraft(
            name="October midweek rate adjustment",
            listing_ids=["AL-STAY-103", "AL-STAY-110"],
            discount_pct=10,
            starts="2026-10-05",
            ends="2026-10-29",
        ),
    )
    assert change.margin_before_pct is None and change.margin_after_pct is None
    assert len([note for note in change.guardrail_notes if "margin" in note]) == 2


def test_today_snapshot_resolves_property_names(merchant):
    today = merchant.today_snapshot()
    assert set(today) == {"arrivals", "departures", "new_bookings"}
    assert today["arrivals"]["count"] == 4
    assert today["departures"]["count"] == 2
    assert today["new_bookings"]["count"] == 3
    assert "ACME Hotels Lisbon Riverside" in today["arrivals"]["properties"]


async def test_occupancy_overview_covers_the_portfolio(merchant):
    overview = await merchant.occupancy_overview()
    assert overview["window"] == {"from": "2026-08-01", "to": "2026-12-20"}
    assert {row["listing_id"] for row in overview["properties"]} == SUPPLIER_PORTFOLIO
    assert all(row["weeks"] for row in overview["properties"])
    assert overview["staged_windows"] == []


async def test_staged_promotion_windows_track_the_ledger(merchant, operator_session):
    """A promotion window is listed only while its change is pending."""
    promotion = PromotionDraft(
        name="October midweek fill",
        listing_ids=["AL-STAY-103", "AL-STAY-110"],
        discount_pct=12,
        starts="2026-10-05",
        ends="2026-10-16",
    )
    change = await merchant.stage_promotion(operator_session, promotion)
    windows = merchant.staged_promotion_windows()
    assert len(windows) == 1
    assert windows[0]["change_id"] == change.change_id
    assert windows[0]["starts"] == "2026-10-05"
    assert windows[0]["ends"] == "2026-10-16"
    assert windows[0]["listing_ids"] == ["AL-STAY-103", "AL-STAY-110"]

    await merchant.apply_change(operator_session, change.change_id)
    assert merchant.staged_promotion_windows() == []
