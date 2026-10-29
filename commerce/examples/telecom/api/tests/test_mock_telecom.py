# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

from datetime import date, timedelta

from shopping_agent import SearchFilters, ShoppingSessionContext
from telecom.api.mock_telecom import _add_months


def test_catalog_loads_and_validates(backend):
    assert len(backend.products) >= 20
    assert backend.store_name == "ACME Mobile"
    plan = backend.products["AM-PLAN-103"]
    assert plan.attributes["data_allowance_gb"] == "unlimited"
    assert plan.attributes["price_unit"] == "per_month"
    fiber = backend.products["AM-NET-302"]
    assert fiber.attributes["typical_download_mbps"]
    assert fiber.attributes["typical_latency_ms"]


async def test_search_synonyms_land(backend, session):
    phones = await backend.search_products(session, "new phone")
    assert phones and any(p.category == "devices" for p in phones[:3])
    fiber = await backend.search_products(session, "home internet")
    assert any(p.category == "home-internet" for p in fiber[:3])
    plans = await backend.search_products(session, "unlimited plan")
    assert any(p.product_id == "AM-PLAN-103" for p in plans[:3])


async def test_min_data_gb_is_a_hard_filter(backend, session):
    filters = SearchFilters(category="plans", attributes={"min_data_gb": "15"})
    plans = await backend.search_products(session, "phone plan", filters)
    ids = {p.product_id for p in plans}
    assert "AM-PLAN-101" not in ids  # 5GB < 15
    assert "AM-PLAN-105" not in ids  # 10GB < 15
    assert "AM-PLAN-102" in ids  # exactly 15
    assert "AM-PLAN-103" in ids  # unlimited always qualifies


async def test_soft_filters_relax_when_they_zero_out(backend, session):
    filters = SearchFilters(attributes={"color": "chartreuse"})
    results = await backend.search_products(session, "unlimited plan", filters)
    assert results


async def test_price_sort(backend, session):
    filters = SearchFilters(category="plans", sort="price_asc")
    plans = await backend.search_products(session, "plan", filters)
    prices = [p.price for p in plans]
    assert prices == sorted(prices)


async def test_plan_add_replaces_existing_plan(backend, session):
    await backend.add_to_cart(session, "AM-PLAN-101", 1)
    cart = await backend.add_to_cart(session, "AM-PLAN-103", 1)
    plan_lines = [i for i in cart.items if i.product_id.startswith("AM-PLAN")]
    assert len(plan_lines) == 1
    assert plan_lines[0].product_id == "AM-PLAN-103"


async def test_plan_quantity_clamped_to_one(backend, session):
    cart = await backend.add_to_cart(session, "AM-PLAN-103", 5)
    assert cart.items[0].quantity == 1
    cart = await backend.update_cart_item(session, "AM-PLAN-103", 4)
    assert cart.items[0].quantity == 1


async def test_internet_and_plan_coexist_but_each_is_single(backend, session):
    await backend.add_to_cart(session, "AM-PLAN-103", 1)
    await backend.add_to_cart(session, "AM-NET-301", 1)
    cart = await backend.add_to_cart(session, "AM-NET-302", 1)
    ids = {i.product_id for i in cart.items}
    assert "AM-PLAN-103" in ids
    assert "AM-NET-302" in ids and "AM-NET-301" not in ids


async def test_account_context_eligible_with_trade_in_at_boot(backend, session):
    # The contract clock re-anchors to the boot date at month 23 of 24.
    account = await backend.get_account_context(session)
    assert account is not None
    assert account["contract"]["month"] == 23
    assert account["contract"]["of_months"] == 24
    assert account["upgrade_eligibility"]["eligible"] is True
    assert account["upgrade_eligibility"]["kind"] == "early-with-trade-in"
    assert account["contract"]["ends"] in account["upgrade_eligibility"]["reason"]
    # 24 installments, 23 elapsed.
    assert account["device"]["installments_remaining"] == 1
    # Essential 5GB $35.00 + ACME Phone 4 $699 / 24.
    assert account["monthly_bill_usd"] == 64.13
    # Tier B is $200 in the trade-in policy table.
    trade_in = account["trade_in_estimate"]
    assert trade_in["tier"] == "B"
    assert trade_in["estimated_credit_usd"] == 200
    assert "powers on" in trade_in["condition_assumption"]
    quoted_on = date.today()
    assert trade_in["quote_valid_through"] == (quoted_on + timedelta(days=30)).isoformat()


async def test_account_context_figures_are_catalog_derived(backend, session):
    account = await backend.get_account_context(session)
    assert account["current_plan"]["data_allowance_gb"] == "5"
    usage = account["recent_usage"]
    cycles = usage["cycles_gb_last_3"]
    assert round(sum(cycles) / len(cycles), 1) == usage["avg_gb_per_month_last_3"]
    # 4 top-ups at the $10 catalog price.
    assert usage["top_up_spend_usd_last_3_months"] == 40.0
    # $699 over 24 payments.
    assert account["device"]["installment_usd"] == 29.13
    assert account["monthly_bill_usd"] == round(
        account["current_plan"]["price_per_month"] + account["device"]["installment_usd"], 2
    )
    start = date.fromisoformat(account["contract"]["started"])
    assert account["contract"]["early_upgrade_on"] == _add_months(start, 22).isoformat()


async def test_account_context_before_and_after_window(backend, session):
    start = date.fromisoformat((await backend.get_account_context(session))["contract"]["started"])
    early = await backend.get_account_context(session, on=_add_months(start, 12))
    assert early["upgrade_eligibility"]["eligible"] is False
    assert early["device"]["installments_remaining"] == 12
    done = await backend.get_account_context(session, on=_add_months(start, 25))
    assert done["upgrade_eligibility"]["kind"] == "outright"
    assert done["device"]["installments_remaining"] == 0


async def test_account_context_none_for_prospects(backend):
    casey = ShoppingSessionContext(session_id="s2", user_id="demo-user-2")
    assert await backend.get_account_context(casey) is None
    stranger = ShoppingSessionContext(session_id="s3", user_id="nobody")
    assert await backend.get_account_context(stranger) is None


async def test_orders_scoped_per_user_and_tell_the_topup_story(backend, session):
    orders = await backend.get_orders(session, limit=10)
    assert all(o.order_id.startswith("AM-9") for o in orders)
    topups = [o for o in orders if any(i.product_id == "AM-ADD-401" for i in o.items)]
    assert len(topups) == 3  # March, April, May


async def test_policy_search_finds_upgrade_terms(backend, session):
    policies = await backend.search_policies(session, "trade in upgrade eligibility")
    ids = [p.policy_id for p in policies]
    assert "upgrade-eligibility" in ids or "trade-in-program" in ids
    fees = await backend.search_policies(session, "early termination fee")
    assert any(p.policy_id == "early-termination" for p in fees)


async def test_fulfillment_options_by_category(backend, session):
    plan_opts = await backend.get_fulfillment_options(session, ["AM-PLAN-103"])
    assert any("eSIM" in o.eta for o in plan_opts)
    device_opts = await backend.get_fulfillment_options(session, ["AM-DEV-202"])
    assert any(o.method == "pickup" for o in device_opts)
    fiber_opts = await backend.get_fulfillment_options(session, ["AM-NET-301"])
    assert any("install" in o.eta for o in fiber_opts)
