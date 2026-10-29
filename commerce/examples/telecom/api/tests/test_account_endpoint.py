# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""GET /api/account returns the token's own account, whatever the request says."""

from demo_common.tests.fixtures import start_shopper


def test_subscriber_gets_the_server_computed_account(client):
    account = client.get("/api/account", headers=start_shopper(client)).json()["account"]
    assert account["current_plan"]["product_id"] == "AM-PLAN-101"
    assert account["contract"]["of_months"] == 24
    assert account["recent_usage"]["top_up_spend_usd_last_3_months"] == 40.0
    assert account["trade_in_estimate"]["estimated_credit_usd"] == 200


def test_prospect_gets_null_even_when_naming_a_subscriber(client):
    prospect = start_shopper(client, "demo-user-2")
    spoofed = client.get("/api/account", params={"user_id": "demo-user"}, headers=prospect)
    assert spoofed.status_code == 200 and spoofed.json()["account"] is None
