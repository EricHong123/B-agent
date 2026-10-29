# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Both roles' search results: a count header outside the fence, the payload inside it."""

from __future__ import annotations

import json

import pytest

from merchant_agent import Listing
from merchant_agent import serialization as merchant_serialization
from merchant_agent.fencing import MERCHANT_FENCE
from shopping_agent import Product
from shopping_agent import serialization as shopping_serialization
from shopping_agent.fencing import STOREFRONT_FENCE

ROLES = {
    "shopping": (
        shopping_serialization,
        STOREFRONT_FENCE,
        lambda i: Product(product_id=f"P-{i}", title=f"Fixture Product {i}", price=10.0 + i),
    ),
    "merchant": (
        merchant_serialization,
        MERCHANT_FENCE,
        lambda i: Listing(
            listing_id=f"L-{i}", title=f"Fixture Listing {i}", price=10.0 + i, stock=5
        ),
    ),
}


@pytest.fixture(params=list(ROLES))
def envelope(request):
    return ROLES[request.param]


QUERY = "canvas tote bag"


def test_header_is_the_constant_for_the_count_and_the_payload_is_fenced(envelope):
    serialization, fence, item = envelope
    for count in (0, 3):
        text = serialization.search_result_text(QUERY, [item(i) for i in range(count)])
        header, _, fenced = text.partition("\n")
        assert header == serialization.search_result_header(count)
        assert fenced.startswith(fence.open) and fenced.endswith(fence.close)
        assert QUERY not in header and fence.open not in header and fence.close not in header
        payload = json.loads(fenced.strip().removeprefix(fence.open).removesuffix(fence.close))
        assert payload["result_count"] == count and len(payload["results"]) == count
        assert payload["query"] == QUERY


def test_headers_carry_only_the_count(envelope):
    serialization, _, _ = envelope
    assert serialization.search_result_header(0) is serialization.SEARCH_EMPTY_HEADER
    assert "3 result(s)" in serialization.search_result_header(3)
    assert serialization.search_result_header(2).replace(
        "2", "9", 1
    ) == serialization.search_result_header(9)
