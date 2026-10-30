# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The payloads read tools hand the model, built once so every path returns the same
bytes. The search header is the one runtime-authored line outside the fence: the result
count and a fixed sentence on how to read the results as text matches (the zero-result
form adds that ids resolve through get_product_details). Only the count varies."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from commerce_common.fencing import MAX_FENCED_CHARS

from .fencing import STOREFRONT_FENCE
from .types import Cart, CartItem, FulfillmentOption, Order, Policy, Product, ProductDetails


def compact_product(product: Product) -> dict[str, Any]:
    data = {
        "product_id": product.product_id,
        "title": product.title,
        "brand": product.brand,
        "price": product.price,
        "currency": product.currency,
        "rating": product.rating,
        "review_count": product.review_count,
        "in_stock": product.in_stock,
        "labels": product.labels or None,
        "attributes": product.attributes or None,
        "options": product.options or None,
        "option_values": product.option_values or None,
        "variant_of": product.variant_of,
        "short_description": product.short_description,
    }
    return {k: v for k, v in data.items() if v is not None}


_VARIANT_ALWAYS = ("product_id", "option_values", "price", "in_stock")


def variant_row(variant: Product, family: dict[str, Any]) -> dict[str, Any]:
    """A variant inside its family's record: its id, option values, price, stock, and
    only the fields and attributes where it differs from the family, so a long size run
    stays short."""
    row = compact_product(variant)
    row.pop("variant_of", None)
    attributes = {
        k: v for k, v in variant.attributes.items() if (family.get("attributes") or {}).get(k) != v
    }
    kept = {
        k: v
        for k, v in row.items()
        if k in _VARIANT_ALWAYS or (k != "attributes" and family.get(k) != v)
    }
    # A row leads with its id and option values; that is what the model scans for.
    lead = {"product_id": kept.pop("product_id"), "option_values": kept.pop("option_values", {})}
    return lead | kept | ({"attributes": attributes} if attributes else {})


def product_details_payload(details: ProductDetails) -> dict[str, Any]:
    family = compact_product(details)
    payload = family | {
        "long_description": details.long_description,
        "specs": details.specs or None,
        "review_highlights": details.review_highlights or None,
        "variants": [variant_row(v, family) for v in details.variants] or None,
    }
    return {k: v for k, v in payload.items() if v is not None}


SEARCH_EMPTY_HEADER = (
    "Search returned 0 results: nothing in the catalog matched this query. Run the "
    "broader retry before telling the customer it is not carried, and do not present a "
    "different product as the requested one. Search matches product text, not ids; "
    "resolve a product id with get_product_details."
)


def search_result_header(count: int) -> str:
    if count == 0:
        return SEARCH_EMPTY_HEADER
    return (
        f"Search returned {count} result(s): the catalog's closest text matches, "
        "which can include related items rather than the exact thing searched for. "
        "Treat a result as the requested item only if its title and attributes match; "
        "if none do, the item was not found, and anything you offer instead is named "
        "as a stand-in."
    )


def search_result_text(
    query: str, products: Sequence[Product], max_chars: int = MAX_FENCED_CHARS
) -> str:
    """The whole search_products result: the header line, then the fenced payload."""
    payload = {
        "query": query,
        "result_count": len(products),
        "results": [compact_product(p) for p in products],
    }
    fenced = STOREFRONT_FENCE.fence_payload(payload, max_chars)
    return search_result_header(len(products)) + "\n" + fenced


def cart_summary(cart: Cart) -> str:
    return f"{cart.item_count} item(s), subtotal {cart.subtotal:.2f} {cart.currency}"


def cart_line_payload(item: CartItem) -> dict[str, Any]:
    line = item.model_dump() | {"line_total": item.line_total}
    for key in ("option_values", "variant_of"):
        if not line[key]:
            del line[key]
    return line


def cart_payload(cart: Cart) -> dict[str, Any]:
    return {
        "items": [cart_line_payload(item) for item in cart.items],
        "item_count": cart.item_count,
        "subtotal": cart.subtotal,
        "currency": cart.currency,
    }


def order_payload(order: Order) -> dict[str, Any]:
    payload = order.model_dump(mode="json", exclude_none=True)
    for item in payload["items"]:
        if not item["option_values"]:
            del item["option_values"]
    return payload


def orders_payload(orders: Sequence[Order]) -> Any:
    return [order_payload(order) for order in orders] or {"note": "No orders found."}


def policies_payload(policies: Sequence[Policy]) -> Any:
    return [p.model_dump(mode="json", exclude_none=True) for p in policies] or {
        "note": "No matching policy content."
    }


def fulfillment_payload(options: Sequence[FulfillmentOption]) -> Any:
    return [o.model_dump(exclude_none=True) for o in options] or {
        "note": "No fulfillment options available."
    }
