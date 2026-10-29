# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The overview and listing reads specific to the retail portal."""

from demo_common.tests.fixtures import start_operator


def test_overview_carries_the_home_page_trends_and_insights(client):
    headers = start_operator(client)
    data = client.get("/api/merchant/overview", headers=headers).json()
    assert set(data["trends"]) == {"sales", "orders", "conversion", "average_order_value"}
    assert all(len(points) == 7 for points in data["trends"].values())
    # The comparison window is the seven days before, ending where the current window starts.
    assert set(data["trends_prior"]) == set(data["trends"])
    assert all(len(points) == 7 for points in data["trends_prior"].values())
    assert data["trends_prior"]["sales"][-1]["date"] < data["trends"]["sales"][0]["date"]
    assert data["insights"] and all(
        entry["headline"] and entry["prompt"] for entry in data["insights"]
    )


def test_listings_hide_the_storefront_delivery_promise(client):
    headers = start_operator(client)
    listings = client.get("/api/merchant/listings", headers=headers).json()["listings"]
    assert listings and all("delivery" not in (entry.get("attributes") or {}) for entry in listings)


def test_product_images_are_served_for_the_portal(client):
    assert client.get("/products/AR-1002.webp").status_code == 200
    assert client.get("/products/missing.webp").status_code == 404
