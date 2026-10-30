# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""POST /api/cart/add takes seen devices and add-ons and refuses plans and home internet."""

import pytest

from demo_common.tests.fixtures import session_record
from telecom.api import main


@pytest.fixture
def add(client, shopper):
    """Returns ``add(product_id, *seen, quantity=1) -> (response, session record)``."""

    def _add(product_id: str, *seen: str, quantity: int = 1):
        headers = shopper(*seen)
        body = {"product_id": product_id, "quantity": quantity}
        return client.post("/api/cart/add", json=body, headers=headers), session_record(
            main, headers
        )

    return _add


def test_seen_device_lands_in_the_cart_and_in_the_next_turns_note(add):
    response, record = add("AM-DEV-202", "AM-DEV-202")
    assert response.status_code == 200
    assert [item["product_id"] for item in response.json()["cart"]["items"]] == ["AM-DEV-202"]
    assert "AM-DEV-202" in record.pending_app_events[0]


def test_add_on_quantity_is_kept(add):
    response, _ = add("AM-ADD-401", "AM-ADD-401", quantity=2)
    assert response.json()["cart"]["items"][0]["quantity"] == 2


@pytest.mark.parametrize("product_id", ["AM-PLAN-103", "AM-NET-302"])
def test_contract_categories_are_refused_before_anything_is_queued(add, product_id):
    response, record = add(product_id, product_id)
    assert response.status_code == 400 and "through the ACME Assistant" in response.json()["detail"]
    assert record.pending_app_events == []


@pytest.mark.parametrize("product_id", ["AM-DEV-202", "AM-XXX-999"])
def test_unseen_or_unknown_products_are_refused(add, product_id):
    response, _ = add(product_id)
    assert response.status_code == 400


def test_a_device_with_options_is_held_and_its_variant_goes_in(add):
    response, record = add("AM-DEV-203", "AM-DEV-203")
    assert response.status_code == 400 and "options" in response.json()["detail"]
    assert record.pending_app_events == []
    response, _ = add("AM-DEV-203-512-GRAPHITE", "AM-DEV-203", "AM-DEV-203-512-GRAPHITE")
    [line] = response.json()["cart"]["items"]
    assert (line["product_id"], line["price"]) == ("AM-DEV-203-512-GRAPHITE", 1249.0)
    assert line["option_values"] == {"storage": "512 GB", "color": "graphite"}
