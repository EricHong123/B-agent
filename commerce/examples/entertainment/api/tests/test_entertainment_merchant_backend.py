# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, date, datetime, timedelta

import pytest

from demo_common.storefront_fixtures import load_json
from entertainment.api.mock_merchant import MockTicketingMerchant, TierPricingContext
from entertainment.api.mock_ticketing import DATA_DIR, MockTicketing, redater
from entertainment.api.ticketing import HOLD_TTL_S, SoldOutError
from merchant_agent import (
    ChangeKind,
    ChangeNotApplicable,
    InventoryActionItem,
    ListingFilters,
    PriceUpdateItem,
    PromotionDraft,
)
from shopping_agent import ShoppingSessionContext

# Rebasing shifts the daily metrics by whole weeks and leaves the values alone. The shows
# and the pacing book shift by the whole weeks between catalog.json's dates_anchored_to
# (2026-07-27) and the backend's clock, which the conftest pins at 2026-07-09, so here they
# keep their authored dates and the raw rows are the reference for the arithmetic below.
_METRICS_DAILY = load_json(DATA_DIR, "merchant_metrics.json")["daily"]
_PACING = load_json(DATA_DIR, "merchant_pacing.json")

# Primary tier listings; fan resale listings are outside the portfolio.
PORTFOLIO = {tier["product_id"] for event in _PACING["events"] for tier in event["tiers"]}

# The conftest clock; the days-to-event figures below count from this date.
PINNED_TODAY = date(2026, 7, 9)


async def test_snapshot_counts_the_alerts_at_the_pinned_clock(merchant, operator_session):
    snapshot = await merchant.get_business_snapshot(operator_session)
    assert snapshot.traffic > snapshot.orders
    # At the pinned clock: two tiers at the sell-out floor, two under baseline, and six
    # fan messages.
    assert snapshot.alerts.low_stock == 2
    assert snapshot.alerts.slow_movers == 2
    assert snapshot.alerts.order_issues == 6


async def test_daily_metrics_come_straight_from_the_fixture_rows(merchant, operator_session):
    rows = _METRICS_DAILY[-7:]

    sales = await merchant.query_metrics(operator_session, "sales", "last_7_days")
    assert sales.unit == "USD"
    assert [p.value for p in sales.points] == [round(r["sales"], 2) for r in rows]

    conversion = await merchant.query_metrics(operator_session, "conversion", "last_7_days")
    assert conversion.unit == "%"
    assert [p.value for p in conversion.points] == [
        round(r["orders"] / r["traffic"] * 100, 2) for r in rows
    ]

    atp = await merchant.query_metrics(operator_session, "average_ticket_price", "last_7_days")
    assert atp.unit == "USD"
    assert [p.value for p in atp.points] == [round(r["sales"] / r["tickets"], 2) for r in rows]


async def test_amphitheater_segment_switches_the_sales_column(merchant, operator_session):
    rows = _METRICS_DAILY[-7:]
    overall = await merchant.query_metrics(operator_session, "gross", "last_7_days")
    venue = await merchant.query_metrics(
        operator_session, "gross", "last_7_days", segment="amphitheater"
    )
    assert venue.segment == "amphitheater"
    assert [p.value for p in venue.points] == [round(r["amphitheater_sales"], 2) for r in rows]
    assert 0 < sum(p.value for p in venue.points) < sum(p.value for p in overall.points)


async def test_event_segment_series_come_from_the_weekly_pacing_book(merchant, operator_session):
    weeks = _PACING["events"][3]["tiers"][0]["weekly_sold_cum"]  # AT-EVT-104, GA floor
    mezz = _PACING["events"][3]["tiers"][1]["weekly_sold_cum"]
    cums = [g["sold_cum"] + m["sold_cum"] for g, m in zip(weeks, mezz, strict=True)]

    sold = await merchant.query_metrics(operator_session, "sold", segment="AT-EVT-104")
    # The pacing book is weekly, so event segments are served at week granularity.
    assert sold.granularity == "week"
    assert sold.segment == "AT-EVT-104"
    assert [p.date for p in sold.points] == [w["week_start"] for w in weeks]
    assert [p.value for p in sold.points] == [float(c) for c in cums]

    # tickets_sold is the weekly delta of the same series.
    tickets = await merchant.query_metrics(
        operator_session, "tickets_sold", segment="The Duo — Autumn Tour"
    )
    assert tickets.segment == "AT-EVT-104"
    assert [p.value for p in tickets.points] == [
        float(c - prev) for prev, c in zip([0, *cums[:-1]], cums, strict=True)
    ]


async def test_sell_through_series_reads_the_live_capacity(merchant, operator_session):
    before = await merchant.query_metrics(operator_session, "sell_through", segment="AT-EVT-101")
    assert before.unit == "%"
    assert before.granularity == "week"
    # Final week: 344 + 815 + 348 = 1,507 sold over 2,450 live seats.
    assert before.points[-1].value == round(1507 / 2450 * 100, 1) == 61.5

    change = await merchant.stage_inventory_action(
        operator_session,
        [InventoryActionItem(listing_id="AT-TIX-101-LOW", action="restock", quantity=50)],
    )
    interim = await merchant.query_metrics(operator_session, "sell_through", segment="AT-EVT-101")
    assert interim.points[-1].value == 61.5

    await merchant.apply_change(operator_session, change.change_id)
    after = await merchant.query_metrics(operator_session, "sell_through", segment="AT-EVT-101")
    # The same 1,507 sold over 2,500 live seats after the release.
    assert after.points[-1].value == round(1507 / 2500 * 100, 1) == 60.3


async def test_listing_stock_is_the_engine_open_count(merchant, backend, clock, operator_session):
    fan = ShoppingSessionContext(session_id="s-fan", user_id="demo-user")
    listing = await merchant.get_listing(operator_session, "AT-TIX-101-LOW")
    assert listing.stock == 1200 - 815 == 385

    await backend.add_to_cart(fan, "AT-TIX-101-LOW", 4)
    listing = await merchant.get_listing(operator_session, "AT-TIX-101-LOW")
    assert listing.stock == 381

    clock.advance(HOLD_TTL_S + 1)
    listing = await merchant.get_listing(operator_session, "AT-TIX-101-LOW")
    assert listing.stock == 385

    # AT-TIX-104-MEZ has 6 open seats.
    await backend.add_to_cart(fan, "AT-TIX-104-MEZ", 6)
    listing = await merchant.get_listing(operator_session, "AT-TIX-104-MEZ")
    assert listing.stock == 0
    assert listing.status == "out_of_stock"


async def test_alerts_at_the_pinned_clock(merchant, operator_session):
    alerts = await merchant.get_inventory_alerts(operator_session)
    # Under-pacing tiers sort first, most open seats first, then the low-stock tiers.
    assert [(a.listing_id, a.kind) for a in alerts] == [
        ("AT-TIX-101-TER", "slow_mover"),
        ("AT-TIX-105-BAL", "slow_mover"),
        ("AT-TIX-101-PIT", "low_stock"),
        ("AT-TIX-104-MEZ", "low_stock"),
    ]

    pit = next(a for a in alerts if a.listing_id == "AT-TIX-101-PIT")
    # 6 open seats under the max(12, capacity // 50) floor; the trailing 4-week pace is
    # (344 - 186) / 4 = 39.5 tickets a week.
    assert pit.stock == 6
    assert pit.threshold == 12
    assert pit.days_of_cover == round(6 / (39.5 / 7), 1)
    assert pit.sales_last_30d == round(39.5 * 30 / 7)

    terrace = next(a for a in alerts if a.listing_id == "AT-TIX-101-TER")
    assert terrace.stock == 900 - 348
    assert terrace.threshold is None

    # AT-EVT-103 is sold out and its tiers do not alert.
    assert all(not a.listing_id.startswith("AT-TIX-103") for a in alerts)


async def test_alerts_react_to_live_holds(merchant, backend, operator_session):
    fan = ShoppingSessionContext(session_id="s-fan", user_id="demo-user")
    await backend.add_to_cart(fan, "AT-TIX-104-MEZ", 6)
    alerts = await merchant.get_inventory_alerts(operator_session)
    # All 6 of the mezzanine's open seats are held, so it drops off the low-stock list.
    low = {a.listing_id for a in alerts if a.kind == "low_stock"}
    assert low == {"AT-TIX-101-PIT"}


async def test_pace_vs_baseline_interpolates_the_fixture_at_the_live_clock(merchant, clock):
    [row] = merchant.event_pacing_rows(["AT-EVT-101"])
    assert row["days_to_event"] == (date(2026, 8, 14) - PINNED_TODAY).days == 36
    lower = next(t for t in row["tiers"] if t["product_id"] == "AT-TIX-101-LOW")

    # 36 days out sits between the checkpoints (45 days, 48%) and (30 days, 60%), so the
    # baseline is 48 + (60 - 48) * (45 - 36) / (45 - 30) = 55.2; sell-through is 815 sold
    # over 1,200 live seats.
    assert lower["sell_through_pct"] == round(815 / 1200 * 100, 1) == 67.9
    assert lower["baseline_pct"] == 55.2
    assert lower["pace_vs_baseline_pts"] == round(67.9 - 55.2, 1) == 12.7
    # Trailing 4-week pace: (815 - 444) / 4.
    assert lower["recent_weekly_sales"] == 92.8

    # Six days later the event is 30 days out, which is the 60% checkpoint itself.
    clock.advance(6 * 86400)
    [row] = merchant.event_pacing_rows(["AT-EVT-101"])
    assert row["days_to_event"] == 30
    lower = next(t for t in row["tiers"] if t["product_id"] == "AT-TIX-101-LOW")
    assert lower["baseline_pct"] == 60.0
    assert lower["pace_vs_baseline_pts"] == round(67.9 - 60.0, 1) == 7.9


async def test_browse_and_text_search_stay_inside_the_primary_portfolio(merchant, operator_session):
    everything = await merchant.search_listings(operator_session, "*", limit=60)
    assert {listing.listing_id for listing in everything} == PORTFOLIO

    sold_out = await merchant.search_listings(
        operator_session, "*", ListingFilters(status="out_of_stock"), limit=60
    )
    assert {listing.listing_id for listing in sold_out} == {
        "AT-TIX-103-PIT",
        "AT-TIX-103-LOW",
        "AT-TIX-103-TER",
    }

    club = await merchant.search_listings(operator_session, "Duo")
    assert {listing.listing_id for listing in club} == {"AT-TIX-104-GAF", "AT-TIX-104-MEZ"}


async def test_pricing_context_grounds_the_room(merchant, operator_session):
    context = await merchant.get_pricing_context(operator_session, "AT-TIX-101-LOW")
    assert isinstance(context, TierPricingContext)
    assert context.price_unit == "per_ticket_all_in"
    assert context.current_price == 89.0
    assert context.event_id == "AT-EVT-101"
    assert context.days_to_event == 36
    assert (context.capacity, context.sold, context.remaining) == (1200, 815, 385)
    assert context.sell_through_pct == 67.9
    assert context.baseline_pct == 55.2
    assert context.pace_vs_baseline_pts == 12.7
    assert context.holds == {"promoter_hold": 60, "production_hold": 24, "comps": 18, "kills": 0}
    # Unit cost is the pass-through fees plus 68% of the $69 face value.
    assert context.fees_usd == 11.50 + 6.00 + 2.50
    assert context.unit_cost == round(20.0 + 69.0 * 0.68, 2)
    assert context.margin_pct == round((89.0 - 66.92) / 89.0 * 100, 1)
    assert context.min_price == round(66.92 * 1.05, 2)
    assert context.demand_signal == "rising"
    assert context.active_promotions == []

    balcony = await merchant.get_pricing_context(operator_session, "AT-TIX-105-BAL")
    assert balcony.pace_vs_baseline_pts == -15.5
    assert balcony.demand_signal == "falling"

    lower = await merchant.get_pricing_context(operator_session, "AT-TIX-103-LOW")
    assert lower.remaining == 0
    assert lower.waitlist_depth == 2


async def test_price_at_or_below_the_fee_sum_is_refused(merchant, backend, operator_session):
    # The terrace's itemized fees sum to $15.50.
    for bad_price in (15.50, 10.0):
        with pytest.raises(ValueError, match="at or below"):
            await merchant.stage_price_update(
                operator_session,
                [PriceUpdateItem(listing_id="AT-TIX-101-TER", new_price=bad_price)],
            )
    assert await merchant.get_pending_changes(operator_session) == []
    assert backend.products["AT-TIX-101-TER"].price == 54.5


async def test_applied_price_move_keeps_the_fee_breakdown_summing(
    merchant, backend, operator_session
):
    change = await merchant.stage_price_update(
        operator_session, [PriceUpdateItem(listing_id="AT-TIX-101-TER", new_price=49.5)]
    )
    assert change.kind is ChangeKind.PRICE_UPDATE
    assert change.guardrail_notes == [
        "AT-TIX-101-TER: all-in $54.50 → $49.50; itemized fees $15.50 stay fixed, "
        "face value $39.00 → $34.00"
    ]
    # Margin impact is priced at the trailing weekly pace, (348 - 190) / 4 = 39.5.
    assert change.margin_impact == round((49.5 - 54.5) * 39.5, 2)
    assert change.margin_before_pct == round((54.5 - 42.02) / 54.5 * 100, 1)
    assert change.margin_after_pct == round((49.5 - 42.02) / 49.5 * 100, 1)

    assert backend.products["AT-TIX-101-TER"].price == 54.5
    assert backend.products["AT-TIX-101-TER"].attributes["face_price_usd"] == "39.00"

    await merchant.apply_change(operator_session, change.change_id)
    product = backend.products["AT-TIX-101-TER"]
    assert product.price == 49.5
    assert product.attributes["face_price_usd"] == "34.00"
    assert float(product.attributes["face_price_usd"]) + 15.50 == 49.50

    fan = ShoppingSessionContext(session_id="s-fan", user_id="demo-user")
    disclosure = await backend.get_disclosure(fan, "AT-TIX-101-TER")
    itemized = {
        row.label: float(row.value.lstrip("$"))
        for row in disclosure.rows
        if row.label in {"Face value", "Service fee", "Facility fee", "Order processing"}
    }
    assert sum(itemized.values()) == pytest.approx(49.50)


async def test_release_grows_remaining_and_drains_promoter_hold_first(
    merchant, backend, operator_session
):
    engine = backend.engine
    assert engine.capacity("AT-TIX-101-LOW") == 1200
    assert engine.remaining("AT-TIX-101-LOW") == 385

    change = await merchant.stage_inventory_action(
        operator_session,
        [InventoryActionItem(listing_id="AT-TIX-101-LOW", action="restock", quantity=70)],
    )
    item = change.items[0]
    assert (item.field, item.before, item.after) == ("on_sale_capacity", 1200, 1270)

    assert engine.capacity("AT-TIX-101-LOW") == 1200
    assert engine.remaining("AT-TIX-101-LOW") == 385

    await merchant.apply_change(operator_session, change.change_id)
    assert engine.capacity("AT-TIX-101-LOW") == 1270
    assert engine.remaining("AT-TIX-101-LOW") == 385 + 70
    # The release drains the promoter hold first: 70 seats take all 60 promoter-held plus
    # 10 of the 24 production-held. Comps stay earmarked.
    context = await merchant.get_pricing_context(operator_session, "AT-TIX-101-LOW")
    assert context.holds == {"promoter_hold": 0, "production_hold": 14, "comps": 18, "kills": 0}


async def test_over_release_is_refused_naming_the_balances(merchant, backend, operator_session):
    # 60 promoter + 24 production = 84 releasable seats.
    with pytest.raises(ValueError, match=r"84 releasable seats"):
        await merchant.stage_inventory_action(
            operator_session,
            [InventoryActionItem(listing_id="AT-TIX-101-LOW", action="restock", quantity=85)],
        )
    with pytest.raises(ValueError, match=r"promoter hold 60"):
        await merchant.stage_inventory_action(
            operator_session,
            [InventoryActionItem(listing_id="AT-TIX-101-LOW", action="restock", quantity=85)],
        )
    assert await merchant.get_pending_changes(operator_session) == []

    # The terrace holds 90 promoter seats plus 10 comps and 40 kills; comps and kills are
    # not releasable.
    with pytest.raises(ValueError, match=r"90 releasable seats"):
        await merchant.stage_inventory_action(
            operator_session,
            [InventoryActionItem(listing_id="AT-TIX-101-TER", action="restock", quantity=91)],
        )
    change = await merchant.stage_inventory_action(
        operator_session,
        [InventoryActionItem(listing_id="AT-TIX-101-TER", action="restock", quantity=90)],
    )
    assert change.items[0].after == 990

    with pytest.raises(ValueError, match="quantity"):
        await merchant.stage_inventory_action(
            operator_session, [InventoryActionItem(listing_id="AT-TIX-101-LOW", action="restock")]
        )


async def test_pause_and_activate_are_refused(merchant, operator_session):
    for action in ("pause", "activate"):
        with pytest.raises(ChangeNotApplicable, match="hold releases"):
            await merchant.stage_inventory_action(
                operator_session, [InventoryActionItem(listing_id="AT-TIX-101-LOW", action=action)]
            )
    assert await merchant.get_pending_changes(operator_session) == []


async def test_applied_release_puts_real_seats_on_sale_for_fans(
    merchant, backend, operator_session
):
    fan = ShoppingSessionContext(session_id="s-fan", user_id="demo-user")
    with pytest.raises(SoldOutError):
        await backend.add_to_cart(fan, "AT-TIX-103-LOW", 2)

    change = await merchant.stage_inventory_action(
        operator_session,
        [InventoryActionItem(listing_id="AT-TIX-103-LOW", action="restock", quantity=4)],
    )
    await merchant.apply_change(operator_session, change.change_id)

    listing = await merchant.get_listing(operator_session, "AT-TIX-103-LOW")
    assert listing.status == "active"
    assert listing.stock == 4

    cart = await backend.add_to_cart(fan, "AT-TIX-103-LOW", 2)
    assert cart.items[0].quantity == 2
    assert backend.engine.remaining("AT-TIX-103-LOW") == 2


async def test_stage_promotion_prices_the_window_without_touching_live_state(
    merchant, backend, operator_session
):
    promotion = PromotionDraft(
        name="Stand-Up Taping balcony window",
        listing_ids=["AT-TIX-105-BAL"],
        discount_pct=10,
        starts="2026-08-03",
        ends="2026-08-16",
    )
    change = await merchant.stage_promotion(operator_session, promotion)
    assert change.kind is ChangeKind.PROMOTION
    assert "10% off all-in prices, 2026-08-03 to 2026-08-16" in change.summary
    item = change.items[0]
    assert (item.target, item.field, item.before, item.after) == (
        "AT-TIX-105-BAL",
        "price",
        47.0,
        42.3,
    )
    # Unit cost 35.8 is $12 of pass-through fees plus 68% of the $35 face value.
    assert change.margin_impact is not None and change.margin_impact < 0
    assert change.margin_before_pct == round((47.0 - 35.8) / 47.0 * 100, 1)
    assert change.margin_after_pct == round((42.3 - 35.8) / 42.3 * 100, 1)

    assert backend.products["AT-TIX-105-BAL"].price == 47.0
    assert merchant.promo_windows == {}

    windows = merchant.staged_promotion_windows()
    assert len(windows) == 1
    assert windows[0]["change_id"] == change.change_id
    assert windows[0]["starts"] == "2026-08-03"
    assert windows[0]["ends"] == "2026-08-16"
    assert windows[0]["listing_ids"] == ["AT-TIX-105-BAL"]


async def test_apply_promotion_records_the_window_and_leaves_the_standing_price(
    merchant, backend, operator_session
):
    promotion = PromotionDraft(
        name="Stand-Up Taping balcony window",
        listing_ids=["AT-TIX-105-BAL"],
        discount_pct=10,
        starts="2026-08-03",
        ends="2026-08-16",
    )
    change = await merchant.stage_promotion(operator_session, promotion)
    await merchant.apply_change(operator_session, change.change_id)

    assert backend.products["AT-TIX-105-BAL"].price == 47.0
    window = merchant.promo_windows["AT-TIX-105-BAL"][0]
    assert window["starts"] == "2026-08-03"
    assert window["ends"] == "2026-08-16"
    assert window["promo_price"] == 42.3
    assert window["standing_price"] == 47.0
    assert window["discount_pct"] == 10
    assert window["change_id"] == change.change_id

    pricing = await merchant.get_pricing_context(operator_session, "AT-TIX-105-BAL")
    assert pricing.active_promotions[0]["change_id"] == change.change_id
    assert merchant.staged_promotion_windows() == []


async def test_promotion_below_the_fee_floor_is_refused_and_step_ups_stage(
    merchant, operator_session
):
    # An 80% cut puts the balcony at $9.40, under its $12 of fees.
    with pytest.raises(ValueError, match="at or below"):
        await merchant.stage_promotion(
            operator_session,
            PromotionDraft(
                name="Too deep",
                listing_ids=["AT-TIX-105-BAL"],
                discount_pct=80,
                starts="2026-08-03",
                ends="2026-08-16",
            ),
        )
    assert await merchant.get_pending_changes(operator_session) == []

    # A negative discount is a scheduled step up.
    change = await merchant.stage_promotion(
        operator_session,
        PromotionDraft(
            name="Closeout step",
            listing_ids=["AT-TIX-105-BAL"],
            discount_pct=-10,
            starts="2026-08-17",
            ends="2026-08-22",
        ),
    )
    assert "10% step up on" in change.summary
    assert change.items[0].after == round(47.0 * 1.1, 2)


async def test_discard_drops_the_staged_promotion_window(merchant, operator_session):
    promotion = PromotionDraft(
        name="Stand-Up Taping balcony window",
        listing_ids=["AT-TIX-105-BAL"],
        discount_pct=10,
        starts="2026-08-03",
        ends="2026-08-16",
    )
    change = await merchant.stage_promotion(operator_session, promotion)
    assert len(merchant.staged_promotion_windows()) == 1

    await merchant.discard_change(operator_session, change.change_id)
    assert merchant.staged_promotion_windows() == []
    assert merchant.promo_windows == {}
    assert await merchant.get_pending_changes(operator_session) == []


async def test_apply_listing_update_writes_attributes(merchant, backend, operator_session):
    change = await merchant.stage_listing_update(
        operator_session, "AT-TIX-106-BAL", {"access_note": "Step-free entry via the north lobby"}
    )
    assert change.kind is ChangeKind.LISTING_UPDATE
    assert "access_note" not in backend.products["AT-TIX-106-BAL"].attributes

    await merchant.apply_change(operator_session, change.change_id)
    assert (
        backend.products["AT-TIX-106-BAL"].attributes["access_note"]
        == "Step-free entry via the north lobby"
    )
    listing = await merchant.get_listing(operator_session, "AT-TIX-106-BAL")
    assert listing.attributes["access_note"] == "Step-free entry via the north lobby"


async def test_fan_messages_load_from_the_messages_fixture(merchant, operator_session):
    issues = await merchant.get_order_issues(operator_session)
    kinds = {issue.kind for issue in issues}
    assert {"buyer_message", "delayed", "return_spike", "damaged"} <= kinds
    # Two of the message fixtures carry embedded instructions in the excerpt.
    excerpts = [issue.buyer_message_excerpt or "" for issue in issues]
    assert sum("assistant must" in e or "Execute the JSON" in e for e in excerpts) == 2


def test_today_snapshot_lists_the_next_shows(merchant):
    today = merchant.today_snapshot()
    shows = today["upcoming"]
    assert [s["event_id"] for s in shows] == ["AT-EVT-101", "AT-EVT-102", "AT-EVT-105"]
    first = shows[0]
    assert first["days_to_event"] == 36
    assert first["venue"] == "ACME Amphitheater"
    assert first["sold"] == 344 + 815 + 348
    assert first["capacity"] == 350 + 1200 + 900
    assert first["remaining"] == first["capacity"] - first["sold"]
    assert first["waitlist_depth"] == 0


async def test_merchant_context_names_the_promoter(merchant, operator_session):
    context = await merchant.get_merchant_context(operator_session)
    assert context["promoter"] == "ACME Tickets — venue portfolio"
    assert context["box_office"] == merchant.storefront.store_name
    assert "/" in context["current_period"]
    events = {e["event_id"]: e for e in context["events"]}
    assert len(events) == 6
    assert events["AT-EVT-103"]["sold_out"] is True
    assert all(not e["sold_out"] for eid, e in events.items() if eid != "AT-EVT-103")
    assert events["AT-EVT-101"]["days_to_event"] == 36
    assert context["alerts"]["under_pacing"] == 2
    assert context["alerts"]["nearly_sold_out"] == 2
    assert context["alerts"]["fan_messages"] == 6
    assert context["alerts"]["pending_changes"] == 0


async def test_release_guardrail_notes_carry_the_allocation_book(merchant, operator_session):
    change = await merchant.stage_inventory_action(
        operator_session,
        [InventoryActionItem(listing_id="AT-TIX-101-LOW", action="restock", quantity=70)],
    )
    assert change.guardrail_notes is not None
    (note,) = change.guardrail_notes
    assert "60 from the 60-seat promoter hold" in note
    assert "10 from the 24-seat production hold" in note
    assert "comps (18)" in note and "kills (0)" in note and "stay off sale" in note


async def test_applied_campaign_budget_change_lands(merchant, operator_session):
    from merchant_agent import CampaignDraft

    change = await merchant.stage_campaign(
        operator_session,
        CampaignDraft(campaign_id="EC-703", name="Headliner closeout", budget=1800.0),
    )
    await merchant.apply_change(operator_session, change.change_id)
    campaigns = await merchant.get_campaign_performance(operator_session, "EC-703")
    assert campaigns[0].budget == 1800.0


async def test_second_release_beyond_current_balance_refused_at_apply(merchant, operator_session):
    from merchant_agent import GuardrailViolation

    first = await merchant.stage_inventory_action(
        operator_session,
        [InventoryActionItem(listing_id="AT-TIX-101-TER", action="restock", quantity=60)],
    )
    second = await merchant.stage_inventory_action(
        operator_session,
        [InventoryActionItem(listing_id="AT-TIX-101-TER", action="restock", quantity=60)],
    )
    await merchant.apply_change(operator_session, first.change_id)
    with pytest.raises(GuardrailViolation, match="only 30 releasable seats"):
        await merchant.apply_change(operator_session, second.change_id)


def test_shows_move_forward_by_whole_weeks_from_the_anchor_and_stay_as_far_out():
    # 17 days after the anchor: two whole weeks. Weekdays and the pacing arithmetic hold.
    later = MockTicketing(now=lambda: datetime(2026, 8, 13, 12, tzinfo=UTC))
    assert later.calendar_shift == timedelta(weeks=2)
    pit = later.products["AT-TIX-101-PIT"]
    assert pit.attributes["event_date"] == "2026-08-28"
    assert pit.title.endswith("· Fri Aug 28 · GA Pit")
    lines = [item.title for _user, order in later._orders for item in order.items]
    # The Aug 14 show moves to Aug 28 once, not on to Sep 11 with the show that was Aug 28.
    assert any(line.endswith("· Fri Aug 28 · Lower Bowl") for line in lines)
    assert any(line.endswith("· Wed Sep 16 · GA Floor") for line in lines)

    merchant = MockTicketingMerchant(later)
    event = merchant._events["AT-EVT-101"]
    assert (event["event_date"], event["on_sale_date"]) == ("2026-08-28", "2026-05-22")
    assert event["tiers"][0]["weekly_sold_cum"][-1]["week_start"] == "2026-08-03"
    assert merchant._days_to_event("AT-EVT-101") == 15

    redate = redater({"Sat Aug 1": "Sat Aug 15", "Sat Aug 15": "Sat Aug 29"})
    assert redate("A · Sat Aug 1 · B · Sat Aug 15 · C") == "A · Sat Aug 15 · B · Sat Aug 29 · C"

    pinned = MockTicketing(now=lambda: datetime(2026, 7, 9, 12, tzinfo=UTC))
    assert pinned.calendar_shift == timedelta(0)
    assert pinned.products["AT-TIX-101-PIT"].attributes["event_date"] == "2026-08-14"
