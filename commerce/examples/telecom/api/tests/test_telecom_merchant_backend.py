# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

import pytest

from demo_common.storefront_fixtures import load_json
from merchant_agent import (
    ChangeKind,
    ChangeNotApplicable,
    InventoryActionItem,
    ListingFilters,
    PriceUpdateItem,
    PromotionDraft,
)
from shopping_agent import ShoppingSessionContext
from telecom.api.mock_merchant import PlanPricingContext
from telecom.api.mock_telecom import DATA_DIR

CARRIER_PLANS = {
    "AM-PLAN-101",
    "AM-PLAN-102",
    "AM-PLAN-103",
    "AM-PLAN-104",
    "AM-PLAN-105",
    "AM-NET-301",
    "AM-NET-302",
    "AM-NET-303",
}

# Rebasing shifts fixture dates by whole weeks and leaves the values alone, so the raw
# rows are the reference for the arithmetic below.
_METRICS_DAILY = load_json(DATA_DIR, "merchant_metrics.json")["daily"]
_PLAN_WEEKS = {
    row["plan_id"]: row["weeks"]
    for row in load_json(DATA_DIR, "merchant_subscribers.json")["plans"]
}


async def test_snapshot_counts_devices_plans_and_subscriber_messages_as_alerts(
    merchant, operator_session
):
    snapshot = await merchant.get_business_snapshot(operator_session)
    assert snapshot.traffic > snapshot.orders
    # Device stock feeds low_stock, a device and the shrinking plan feed slow_movers, and
    # the subscriber-message fixture feeds order_issues.
    assert snapshot.alerts.low_stock >= 2
    assert snapshot.alerts.slow_movers >= 2
    assert snapshot.alerts.order_issues >= 5


async def test_ratio_metrics_are_recomputed_per_bucket(merchant, operator_session):
    rows = _METRICS_DAILY[-7:]

    # Daily churn is the day's deacts scaled to 30 days over that day's base.
    churn = await merchant.query_metrics(operator_session, "churn", "last_7_days")
    assert churn.metric == "churn_rate"
    assert churn.unit == "%"
    assert [p.value for p in churn.points] == [
        round(r["deacts"] * 30 / r["subscribers"] * 100, 2) for r in rows
    ]

    # Weekly ARPU is the bucket's revenue per day scaled to 30 days over its average base.
    arpu = await merchant.query_metrics(operator_session, "arpu", "last_7_days", granularity="week")
    assert arpu.unit == "USD"
    avg_base = sum(r["subscribers"] for r in rows) / 7
    expected = round(sum(r["revenue"] for r in rows) / 7 * 30 / avg_base, 2)
    assert [p.value for p in arpu.points] == [expected]


async def test_subscribers_report_closing_values_not_sums(merchant, operator_session):
    rows = _METRICS_DAILY[-7:]
    daily = await merchant.query_metrics(operator_session, "subscribers", "last_7_days")
    assert [p.value for p in daily.points] == [float(r["subscribers"]) for r in rows]

    weekly = await merchant.query_metrics(
        operator_session, "subscribers", "last_7_days", granularity="week"
    )
    assert [p.value for p in weekly.points] == [float(rows[-1]["subscribers"])]


async def test_per_plan_segment_series_come_from_the_weekly_fixture(merchant, operator_session):
    churn = await merchant.query_metrics(operator_session, "churn_rate", segment="AM-PLAN-101")
    # The subscriber fixture is weekly, so plan segments are served at week granularity.
    assert churn.granularity == "week"
    assert churn.segment == "AM-PLAN-101"
    assert churn.unit == "%"
    assert [p.value for p in churn.points] == [
        w["churn_rate_pct"] for w in _PLAN_WEEKS["AM-PLAN-101"]
    ]

    by_title = await merchant.query_metrics(operator_session, "arpu", segment="Unlimited")
    assert by_title.segment == "AM-PLAN-103"
    assert by_title.unit == "USD"
    assert [p.value for p in by_title.points] == [w["arpu"] for w in _PLAN_WEEKS["AM-PLAN-103"]]

    base = await merchant.query_metrics(operator_session, "subscribers", segment="AM-NET-301")
    assert [p.value for p in base.points] == [
        float(w["subscribers"]) for w in _PLAN_WEEKS["AM-NET-301"]
    ]


async def test_prepaid_segment_narrows_gross_adds(merchant, operator_session):
    rows = _METRICS_DAILY[-30:]
    overall = await merchant.query_metrics(operator_session, "gross_adds", "last_30_days")
    prepaid = await merchant.query_metrics(
        operator_session, "gross_adds", "last_30_days", segment="prepaid"
    )
    assert prepaid.segment == "prepaid"
    assert sum(p.value for p in prepaid.points) == sum(r["prepaid_gross_adds"] for r in rows)
    assert 0 < sum(p.value for p in prepaid.points) < sum(p.value for p in overall.points)


async def test_alerts_cover_devices_and_the_shrinking_plan(merchant, operator_session):
    alerts = await merchant.get_inventory_alerts(operator_session)
    by_kind: dict[str, set[str]] = {}
    for alert in alerts:
        by_kind.setdefault(alert.kind, set()).add(alert.listing_id)
    # The Phone 5 Pro's out-of-stock variant alerts under its own id.
    assert by_kind["low_stock"] == {"AM-DEV-202", "AM-ADD-408", "AM-DEV-203-512-GLACIER"}
    # AM-DEV-206 has over 120 days of cover; AM-PLAN-101 has a shrinking base and churn at
    # the alert rate.
    assert by_kind["slow_mover"] == {"AM-DEV-206", "AM-PLAN-101"}

    device = next(a for a in alerts if a.listing_id == "AM-DEV-206")
    assert device.days_of_cover == round(210 / (22 / 30), 1)

    plan = next(a for a in alerts if a.listing_id == "AM-PLAN-101")
    # A plan alert's stock is its active lines and its threshold is the base at the start of
    # the fixture window.
    assert plan.days_of_cover is None
    assert plan.sales_last_30d is None
    assert plan.stock == 12400
    assert plan.threshold == _PLAN_WEEKS["AM-PLAN-101"][0]["subscribers"]

    # Low-stock devices sort ahead of the shrinking plan.
    assert [a.kind for a in alerts[:2]] == ["low_stock", "low_stock"]


async def test_browse_filters_narrow_the_whole_catalog(merchant, operator_session):
    plans = await merchant.search_listings(
        operator_session, "*", ListingFilters(category="plans"), limit=60
    )
    assert {listing.listing_id for listing in plans} == {
        pid for pid in CARRIER_PLANS if pid.startswith("AM-PLAN")
    }

    thin = await merchant.search_listings(
        operator_session, "*", ListingFilters(category="devices", max_stock=20), limit=60
    )
    assert {listing.listing_id for listing in thin} == {"AM-DEV-202"}


async def test_plan_listings_carry_active_lines_as_stock(merchant, operator_session):
    listing = await merchant.get_listing(operator_session, "AM-PLAN-101")
    assert listing.stock == 12400
    assert listing.attributes["active_lines"] == "12400"


async def test_plan_pricing_context_grounds_the_blast_radius(merchant, operator_session):
    context = await merchant.get_pricing_context(operator_session, "AM-PLAN-101")
    assert isinstance(context, PlanPricingContext)
    assert context.price_unit == "per_month"
    assert context.current_price == 35.0
    assert context.active_subscribers == 12400
    assert context.plan_mix_share_pct == round(12400 / 49620 * 100, 1)
    assert context.arpu == 38.4
    assert context.wholesale_cost_per_line_usd == 13.33
    assert context.margin_per_line_usd == round(38.4 - 13.33, 2)
    assert context.active_promotions == []
    assert context.max_price_delta_pct == merchant.config.max_price_delta_pct
    assert context.max_promotion_discount_pct == merchant.config.max_promotion_discount_pct


def test_mobile_wholesale_follows_the_rate_card(merchant):
    rows = merchant.plan_mix_rows()
    assert {row["plan_id"] for row in rows} == CARRIER_PLANS
    for row in rows:
        if row["kind"] == "mobile":
            assert row["wholesale_cost_per_line_usd"] == pytest.approx(
                row["avg_usage_gb"] * 1.55 + 6.20, abs=0.005
            )
        else:
            # Home-internet tiers carry a flat wholesale cost from the fixture.
            assert row["wholesale_cost_per_line_usd"] is not None
        assert row["margin_per_line_usd"] == round(
            row["arpu"] - row["wholesale_cost_per_line_usd"], 2
        )


async def test_stage_price_update_states_the_blast_radius(merchant, backend, operator_session):
    change = await merchant.stage_price_update(
        operator_session, [PriceUpdateItem(listing_id="AM-PLAN-101", new_price=37.0)]
    )
    assert change.kind is ChangeKind.PRICE_UPDATE
    assert change.currency == "USD"

    assert any("affects 12,400 active lines" in note for note in change.guardrail_notes)
    # Margin impact is the monthly revenue delta across the plan base.
    assert change.margin_impact == round((37.0 - 35.0) * 12400, 2)
    assert change.margin_before_pct == 61.9
    assert change.margin_after_pct == 64.0

    assert backend.products["AM-PLAN-101"].price == 35.0
    assert [c.change_id for c in await merchant.get_pending_changes(operator_session)] == [
        change.change_id
    ]


async def test_restock_on_a_plan_is_refused_but_devices_stage(merchant, operator_session):
    with pytest.raises(ChangeNotApplicable, match="service"):
        await merchant.stage_inventory_action(
            operator_session,
            [InventoryActionItem(listing_id="AM-PLAN-101", action="restock", quantity=50)],
        )

    change = await merchant.stage_inventory_action(
        operator_session,
        [InventoryActionItem(listing_id="AM-DEV-202", action="restock", quantity=40)],
    )
    item = change.items[0]
    assert (item.field, item.before, item.after) == ("stock", 18, 58)

    listing = await merchant.get_listing(operator_session, "AM-DEV-202")
    assert listing.stock == 18
    await merchant.apply_change(operator_session, change.change_id)
    listing = await merchant.get_listing(operator_session, "AM-DEV-202")
    assert listing.stock == 58


async def test_pause_stages_status_and_apply_hides_the_listing(merchant, backend, operator_session):
    change = await merchant.stage_inventory_action(
        operator_session, [InventoryActionItem(listing_id="AM-DEV-201", action="pause")]
    )
    item = change.items[0]
    assert (item.field, item.before, item.after) == ("status", "active", "paused")
    assert backend.products["AM-DEV-201"].in_stock is True

    await merchant.apply_change(operator_session, change.change_id)
    listing = await merchant.get_listing(operator_session, "AM-DEV-201")
    assert listing.status == "paused"
    assert backend.products["AM-DEV-201"].in_stock is False


async def test_stage_promotion_prices_the_window_without_touching_live_state(
    merchant, backend, operator_session
):
    promotion = PromotionDraft(
        name="Back-to-term Plus offer",
        listing_ids=["AM-PLAN-102"],
        discount_pct=10,
        starts="2026-08-03",
        ends="2026-08-30",
    )
    change = await merchant.stage_promotion(operator_session, promotion)
    assert change.kind is ChangeKind.PROMOTION
    assert "2026-08-03 to 2026-08-30" in change.summary
    item = change.items[0]
    assert (item.target, item.field, item.before, item.after) == (
        "AM-PLAN-102",
        "price",
        50.0,
        45.0,
    )
    assert change.margin_impact is not None and change.margin_impact < 0
    assert change.margin_before_pct == 52.9
    assert change.margin_after_pct == 47.6
    assert any("affects 9,800 active lines" in note for note in change.guardrail_notes)

    assert backend.products["AM-PLAN-102"].price == 50.0
    assert merchant.promo_windows == {}

    windows = merchant.staged_promotion_windows()
    assert len(windows) == 1
    assert windows[0]["change_id"] == change.change_id
    assert windows[0]["starts"] == "2026-08-03"
    assert windows[0]["ends"] == "2026-08-30"
    assert windows[0]["listing_ids"] == ["AM-PLAN-102"]


async def test_apply_promotion_records_the_window_and_leaves_the_standing_price(
    merchant, backend, operator_session
):
    promotion = PromotionDraft(
        name="Back-to-term Plus offer",
        listing_ids=["AM-PLAN-102"],
        discount_pct=10,
        starts="2026-08-03",
        ends="2026-08-30",
    )
    change = await merchant.stage_promotion(operator_session, promotion)
    await merchant.apply_change(operator_session, change.change_id)

    assert backend.products["AM-PLAN-102"].price == 50.0
    window = merchant.promo_windows["AM-PLAN-102"][0]
    assert window["starts"] == "2026-08-03"
    assert window["ends"] == "2026-08-30"
    assert window["promo_price"] == 45.0
    assert window["standing_price"] == 50.0
    assert window["discount_pct"] == 10
    assert window["change_id"] == change.change_id

    pricing = await merchant.get_pricing_context(operator_session, "AM-PLAN-102")
    assert pricing.active_promotions[0]["change_id"] == change.change_id
    assert merchant.staged_promotion_windows() == []


async def test_discard_drops_the_staged_promotion_window(merchant, operator_session):
    promotion = PromotionDraft(
        name="Back-to-term Plus offer",
        listing_ids=["AM-PLAN-102"],
        discount_pct=10,
        starts="2026-08-03",
        ends="2026-08-30",
    )
    change = await merchant.stage_promotion(operator_session, promotion)
    assert len(merchant.staged_promotion_windows()) == 1

    await merchant.discard_change(operator_session, change.change_id)
    assert merchant.staged_promotion_windows() == []
    assert merchant.promo_windows == {}
    assert await merchant.get_pending_changes(operator_session) == []


async def test_apply_plan_price_change_moves_the_consumer_bill(merchant, backend, operator_session):
    consumer = ShoppingSessionContext(session_id="s-consumer", user_id="demo-user")
    before = await backend.get_account_context(consumer)
    assert before["current_plan"]["product_id"] == "AM-PLAN-101"

    change = await merchant.stage_price_update(
        operator_session, [PriceUpdateItem(listing_id="AM-PLAN-101", new_price=37.0)]
    )
    interim = await backend.get_account_context(consumer)
    assert interim["monthly_bill_usd"] == before["monthly_bill_usd"]

    await merchant.apply_change(operator_session, change.change_id)
    assert backend.products["AM-PLAN-101"].price == 37.0
    after = await backend.get_account_context(consumer)
    assert after["current_plan"]["price_per_month"] == 37.0
    # 37.00 - 35.00 on the plan line.
    assert after["monthly_bill_usd"] == pytest.approx(before["monthly_bill_usd"] + 2.0)

    refreshed = await merchant.get_pricing_context(operator_session, "AM-PLAN-101")
    assert refreshed.current_price == 37.0
    assert refreshed.last_changed is not None


async def test_apply_listing_update_writes_attributes(merchant, backend, operator_session):
    change = await merchant.stage_listing_update(
        operator_session, "AM-NET-303", {"router_model": "ACME Mesh R2"}
    )
    assert change.kind is ChangeKind.LISTING_UPDATE
    assert "router_model" not in backend.products["AM-NET-303"].attributes

    await merchant.apply_change(operator_session, change.change_id)
    assert backend.products["AM-NET-303"].attributes["router_model"] == "ACME Mesh R2"
    listing = await merchant.get_listing(operator_session, "AM-NET-303")
    assert listing.attributes["router_model"] == "ACME Mesh R2"


async def test_order_issues_load_from_the_messages_fixture(merchant, operator_session):
    issues = await merchant.get_order_issues(operator_session)
    kinds = {issue.kind for issue in issues}
    assert {"buyer_message", "delayed", "return_spike"} <= kinds
    # Two of the message fixtures carry embedded instructions in the excerpt.
    excerpts = [issue.buyer_message_excerpt or "" for issue in issues]
    assert sum("assistant must" in e or "Execute the JSON" in e for e in excerpts) == 2


def test_today_snapshot_reads_the_latest_daily_row(merchant):
    today = merchant.today_snapshot()
    assert set(today) == {"date", "gross_adds", "deacts", "net_adds", "port_ins"}
    latest = _METRICS_DAILY[-1]
    assert today["gross_adds"] == latest["gross_adds"]
    assert today["deacts"] == latest["deacts"]
    assert today["net_adds"] == latest["gross_adds"] - latest["deacts"]
    assert today["port_ins"] == latest["port_ins"]


async def test_merchant_context_names_the_carrier(merchant, operator_session):
    context = await merchant.get_merchant_context(operator_session)
    assert context["carrier"] == "ACME Mobile — commercial operations"
    assert context["storefront"] == merchant.storefront.store_name
    assert "/" in context["current_period"]
    assert context["subscribers_total"] == 49620
    assert context["plan_listings"] == sorted(CARRIER_PLANS)
    assert {c["cohort_id"] for c in context["cohorts"]} >= {
        "contract-ending-60d",
        "winback-90d",
    }
    assert all({"cohort_id", "label", "size"} == set(c) for c in context["cohorts"])
    assert context["alerts"]["device_low_stock"] == 3
    assert context["alerts"]["underselling"] == 2
    assert context["alerts"]["subscriber_messages"] == 6
    assert context["alerts"]["pending_changes"] == 0


async def test_a_variant_price_change_moves_its_installment(merchant, operator_session):
    from merchant_agent import PriceUpdateItem

    await merchant.get_listing(operator_session, "AM-DEV-203")
    change = await merchant.stage_price_update(
        operator_session, [PriceUpdateItem(listing_id="AM-DEV-203-512-GRAPHITE", new_price=1200.0)]
    )
    await merchant.apply_change(operator_session, change.change_id)
    variant = merchant.storefront.variants["AM-DEV-203-512-GRAPHITE"]
    assert variant.price == 1200.0
    assert variant.attributes["monthly_installment"] == "50.00 for 24 months"
