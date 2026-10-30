# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The comparison price delta and the product pick shape."""

from shopping_agent.enrichment import comparison_price_delta
from shopping_agent.tools.presentation import PresentProductsPayload


def _entry(product_id: str, price: float | None) -> dict:
    product: dict = {"product_id": product_id, "title": product_id}
    if price is not None:
        product["price"] = price
    return {"product_id": product_id, "product": product}


def test_product_picks_carry_no_model_authored_label():
    payload = PresentProductsPayload.model_validate(
        {"picks": [{"product_id": "a", "reason": "fits the budget", "highlight": "Best"}]}
    )
    assert payload.picks[0].model_dump(exclude_none=True) == {
        "product_id": "a",
        "reason": "fits the budget",
    }


def test_price_delta_spans_cheapest_to_priciest():
    delta = comparison_price_delta([_entry("a", 27.0), _entry("b", 34.0), _entry("c", 29.5)])
    assert delta == {
        "amount": 7.0,
        "low_product_id": "a",
        "low_price": 27.0,
        "high_product_id": "b",
        "high_price": 34.0,
    }


def test_price_delta_none_when_prices_equal():
    assert comparison_price_delta([_entry("a", 30.0), _entry("b", 30.0)]) is None


def test_price_delta_needs_two_priced_entries():
    assert comparison_price_delta([_entry("a", 30.0)]) is None
    assert comparison_price_delta([_entry("a", 30.0), _entry("b", None)]) is None


def test_price_delta_none_across_currencies():
    eur = _entry("b", 30.0)
    eur["product"]["currency"] = "EUR"
    assert comparison_price_delta([_entry("a", 34.0), eur]) is None
