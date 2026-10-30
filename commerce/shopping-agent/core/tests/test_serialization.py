# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The compact product shape inside search results, and the option fields on the
records, cart lines, and order lines the model reads."""

from __future__ import annotations

from datetime import UTC, datetime

from shopping_agent import Cart, CartItem, Order, OrderItem, OrderStatus, Product, ProductDetails
from shopping_agent.serialization import (
    cart_payload,
    compact_product,
    order_payload,
    product_details_payload,
)


def test_compact_product_carries_attributes():
    product = Product(
        product_id="AR-0001",
        title="Trailhead Anorak",
        price=89.0,
        attributes={"color": "moss green", "fabric": "recycled ripstop"},
    )
    compact = compact_product(product)
    assert compact["attributes"] == {"color": "moss green", "fabric": "recycled ripstop"}


def test_compact_product_omits_empty_optionals():
    compact = compact_product(Product(product_id="AR-0002", title="Camp Mug", price=9.0))
    for absent in (
        "attributes",
        "labels",
        "brand",
        "rating",
        "options",
        "option_values",
        "variant_of",
    ):
        assert absent not in compact


def test_a_family_record_carries_its_options_and_its_variants_their_option_values():
    family = ProductDetails(
        product_id="AR-0003",
        title="Trail Pad",
        price=59.0,
        options={"length": ["regular", "long"]},
        variants=[
            Product(
                product_id="AR-0003-L",
                title="Trail Pad",
                price=69.0,
                option_values={"length": "long"},
                variant_of="AR-0003",
            )
        ],
    )
    payload = product_details_payload(family)
    assert payload["options"] == {"length": ["regular", "long"]}
    [variant] = payload["variants"]
    # Inside its family a variant is a row: id, option values, price, stock, and only what differs.
    assert variant == {
        "product_id": "AR-0003-L",
        "option_values": {"length": "long"},
        "price": 69.0,
        "in_stock": True,
    }
    # Read on its own (compact_product), the variant is a whole record naming its family.
    alone = compact_product(family.variants[0])
    assert alone["title"] == "Trail Pad" and alone["variant_of"] == "AR-0003"


def test_cart_and_order_lines_carry_option_keys_only_for_variants():
    plain = CartItem(product_id="AR-0002", title="Camp Mug", price=9.0, quantity=1)
    chosen = CartItem(
        product_id="AR-0003-L",
        title="Trail Pad",
        price=69.0,
        quantity=1,
        option_values={"length": "long"},
        variant_of="AR-0003",
    )
    lines = cart_payload(Cart(items=[plain, chosen]))["items"]
    assert "option_values" not in lines[0] and "variant_of" not in lines[0]
    assert lines[1]["option_values"] == {"length": "long"}
    assert lines[1]["variant_of"] == "AR-0003"

    order = Order(
        order_id="o-1",
        status=OrderStatus.DELIVERED,
        placed_at=datetime(2026, 6, 1, tzinfo=UTC),
        items=[
            OrderItem(product_id="AR-0002", title="Camp Mug", quantity=1, price=9.0),
            OrderItem(
                product_id="AR-0003-L",
                title="Trail Pad",
                quantity=1,
                price=69.0,
                option_values={"length": "long"},
                variant_of="AR-0003",
            ),
        ],
        total=78.0,
    )
    items = order_payload(order)["items"]
    assert "option_values" not in items[0]
    assert items[1]["option_values"] == {"length": "long"}
    assert items[1]["variant_of"] == "AR-0003"
