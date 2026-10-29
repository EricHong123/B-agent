# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Fees come from the catalog and sum to the price; resale rows carry the box-office comparison."""


async def test_fee_rows_sum_to_the_all_in_price(backend, session):
    for product_id, product in backend.products.items():
        if product.category != "tickets":
            continue
        disclosure = await backend.get_disclosure(session, product_id)
        rows = {row.label: row.value for row in disclosure.rows}
        parts = (
            float(rows["Face value"].lstrip("$"))
            + float(rows["Service fee"].lstrip("$"))
            + float(rows["Facility fee"].lstrip("$"))
            + float(rows["Order processing"].lstrip("$"))
        )
        assert abs(parts - product.price) < 0.005, product_id
        assert rows["All-in price"] == f"${product.price:.2f}"


async def test_resale_fee_rows_are_itemized_and_sum_to_the_all_in_price(backend, session):
    for product_id, product in backend.products.items():
        if product.category != "resale":
            continue
        disclosure = await backend.get_disclosure(session, product_id)
        rows = {row.label: row.value for row in disclosure.rows}
        parts = (
            float(rows["Seller price"].lstrip("$"))
            + float(rows["Service fee"].lstrip("$"))
            + float(rows["Facility fee"].lstrip("$"))
            + float(rows["Order processing"].lstrip("$"))
        )
        assert abs(parts - product.price) < 0.005, product_id
        assert rows["All-in price"] == f"${product.price:.2f}"


async def test_resale_disclosure_carries_the_box_office_comparison(backend, session):
    disclosure = await backend.get_disclosure(session, "AT-RSL-201")
    rows = {row.label: row for row in disclosure.rows}
    assert rows["Box-office all-in price"].value == "$123.50"
    assert "sold out" in rows["Box-office all-in price"].note
    assert rows["Value score"].value == "4/10 (red)"
    assert "resale-value-scores" in disclosure.sources


async def test_non_catalog_products_have_no_disclosure(backend, session):
    assert await backend.get_disclosure(session, "AT-XXX-000") is None


async def test_disclosure_cites_the_policy_book(backend, session):
    disclosure = await backend.get_disclosure(session, "AT-TIX-104-GAF")
    assert "all-in-pricing" in disclosure.sources
    assert "ticket-holds" in disclosure.sources
