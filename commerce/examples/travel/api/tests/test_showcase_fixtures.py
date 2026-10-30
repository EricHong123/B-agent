# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The travel showcase's date stamps match what the backend computes for its check-in date."""

from datetime import date
from pathlib import Path

import pytest

from demo_common.tests.fixtures import showcase_products

CHECK_IN = date(2026, 10, 15)


@pytest.fixture(scope="module")
def showcase() -> list[dict]:
    return showcase_products(Path(__file__).resolve().parents[2])


def test_free_cancellation_is_stamped_only_on_refundable_items(showcase):
    for product in showcase:
        attributes = product.get("attributes", {})
        if "free_cancellation_until" in attributes:
            assert attributes.get("refundable") == "yes", product["product_id"]


def test_date_flex_and_scarcity_stamps_match_the_backend_for_the_check_in_date(showcase, backend):
    for product in showcase:
        attributes = product.get("attributes", {})
        product_id = product["product_id"]
        if "date_flex" in attributes:
            assert attributes["date_flex"] == backend.date_flex_strip(product_id, CHECK_IN), (
                product_id
            )
        if "units_left_for_dates" in attributes:
            assert attributes["units_left_for_dates"] == str(
                backend.units_left_on(product_id, CHECK_IN)
            ), product_id
