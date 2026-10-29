import json
from contextlib import contextmanager
from datetime import timedelta
from decimal import Decimal

import pytest

from commerce_common.testing import FakeClient, text_message, tool_use_message

from app.api.v1.auth import get_current_active_user
from app.api.v1.commerce import optional_staff_user
from app.commerce.runtime import CommerceRuntime, ModelChoice, get_commerce_runtime, resolve_model
from app.commerce.seed import seed_demo_catalog
from app.main import app
from app.models.database import (
    CatalogProduct,
    CommerceCartLine,
    CommerceStagedChange,
    Customer,
    SalesOpportunity,
    SalesQuotation,
    User,
)


BASE = "/api/v1/commerce"


@pytest.fixture
def commerce(api_context):
    client, db, user = api_context
    seed_demo_catalog(db)
    customer = Customer(
        username="harbor-buyer",
        platform="email",
        email="buyer@harbor.example",
        company_name="Harbor Goods GmbH",
        country="DE",
        status="contacted",
        custom_fields={"preferred_incoterm": "FOB"},
    )
    db.add(customer)
    db.commit()
    db.refresh(customer)

    @contextmanager
    def scope():
        yield db

    state = {"runtime": None}

    def install(*responses):
        choice = ModelChoice("test", FakeClient(list(responses)), "test-model", "test-fast", True)
        state["runtime"] = CommerceRuntime(scope=scope, choice=choice)
        return state["runtime"]

    install()
    app.dependency_overrides[get_commerce_runtime] = lambda: state["runtime"]
    app.dependency_overrides[optional_staff_user] = lambda: app.dependency_overrides[get_current_active_user]()
    yield client, db, user, customer, install
    app.dependency_overrides.pop(get_commerce_runtime, None)
    app.dependency_overrides.pop(optional_staff_user, None)


def sse_events(text):
    events = []
    for frame in text.strip().split("\n\n"):
        lines = dict(line.split(": ", 1) for line in frame.splitlines() if ": " in line)
        if "event" in lines:
            events.append((lines["event"], json.loads(lines.get("data", "{}"))))
    return events


def buyer_session(client, customer):
    response = client.post(f"{BASE}/buyer/session", json={"customer_id": customer.id})
    assert response.status_code == 201, response.text
    return {"X-Commerce-Session": response.json()["session_id"]}


def operations_session(client):
    response = client.post(f"{BASE}/operations/session")
    assert response.status_code == 201, response.text
    return {"X-Commerce-Session": response.json()["session_id"]}


def test_buyer_assistant_fills_rfq_basket_and_submits_it_to_the_pipeline(commerce):
    client, db, user, customer, install = commerce
    install(
        tool_use_message("search_products", {"query": "vacuum bottle"}),
        tool_use_message("get_product_details", {"product_id": "BTL-5001"}),
        tool_use_message("add_to_cart", {"product_id": "BTL-5001-BLK", "quantity": 600}),
        text_message("600 black bottles are in your RFQ basket."),
    )
    headers = buyer_session(client, customer)

    response = client.post(
        f"{BASE}/buyer/chat",
        headers=headers,
        json={"message": "I need 600 black vacuum bottles", "locale": "en"},
    )
    assert response.status_code == 200
    events = sse_events(response.text)
    kinds = [kind for kind, _ in events]
    assert "cart_update" in kinds
    assert "turn_complete" in kinds
    turn_id = next(data["turn_id"] for kind, data in events if kind == "turn_complete")

    cart = client.get(f"{BASE}/buyer/cart", headers=headers).json()
    assert [(item["product_id"], item["quantity"]) for item in cart["items"]] == [("BTL-5001-BLK", 600)]

    assert client.post(f"{BASE}/buyer/feedback", headers=headers, json={"turn_id": turn_id, "helpful": True}).json() == {"ok": True}

    response = client.post(f"{BASE}/buyer/rfq", headers=headers, json={"note": "Logo on one side"})
    assert response.status_code == 201, response.text
    rfq = response.json()
    assert rfq["below_moq"] == []
    opportunity = db.query(SalesOpportunity).one()
    assert opportunity.source == "buyer_assistant"
    assert opportunity.stage == "quoting"
    assert opportunity.user_id == user.id
    assert "Logo on one side" in opportunity.inquiry_summary
    quotation = db.query(SalesQuotation).one()
    assert quotation.status == "draft"
    assert quotation.line_items_json[0]["sku"] == "BTL-5001-BLK"
    assert quotation.total == Decimal("2880.00")
    assert db.query(CommerceCartLine).count() == 0

    metrics = client.get(f"{BASE}/metrics").json()
    buyer = metrics["roles"]["buyer"]
    assert buyer["effective_sessions"] == 1
    assert buyer["resolution_rate"]["value"] == 1.0


def test_basket_refuses_products_the_session_never_saw(commerce):
    client, _, _, customer, _ = commerce
    headers = buyer_session(client, customer)

    response = client.post(f"{BASE}/buyer/cart/add", headers=headers, json={"product_id": "MUG-2204", "quantity": 1000})
    assert response.status_code == 400

    client.get(f"{BASE}/buyer/products", headers=headers, params={"query": "mug"})
    response = client.post(f"{BASE}/buyer/cart/add", headers=headers, json={"product_id": "MUG-2204", "quantity": 400})
    assert response.status_code == 200
    assert response.json()["items"][0]["quantity"] == 400

    response = client.post(f"{BASE}/buyer/rfq", headers=headers, json={})
    assert response.json()["below_moq"] == ["MUG-2204"]


def test_buyer_portal_invite_scopes_sessions_and_can_be_revoked(commerce):
    client, _, user, customer, _ = commerce
    invite = client.post(f"{BASE}/buyer/invites", json={"customer_id": customer.id}).json()
    portal = {"X-Buyer-Token": invite["token"]}

    response = client.post(f"{BASE}/buyer/session", headers=portal, json={"customer_id": 999})
    assert response.status_code == 201
    body = response.json()
    assert body["mode"] == "portal"
    assert body["customer_id"] == customer.id
    session = {"X-Commerce-Session": body["session_id"], **portal}
    assert client.get(f"{BASE}/buyer/orders", headers=session).status_code == 200

    staff_headers = buyer_session(client, customer)
    assert client.get(f"{BASE}/buyer/cart", headers={**staff_headers, **portal}).status_code == 401

    assert client.post(f"{BASE}/buyer/invites/{invite['id']}/revoke").status_code == 200
    assert client.get(f"{BASE}/buyer/orders", headers=session).status_code == 401
    assert user.id


def test_operations_assistant_stages_and_console_approves_price_change(commerce):
    client, db, user, _, install = commerce
    install(
        tool_use_message("search_listings", {"query": "LED-3108"}),
        tool_use_message("stage_price_update", {"items": [{"listing_id": "LED-3108", "new_price": 10.9}]}),
        text_message("Staged LED-3108 at 10.90 for your approval."),
    )
    headers = operations_session(client)
    response = client.post(f"{BASE}/operations/chat", headers=headers, json={"message": "Drop LED-3108 to 10.90"})
    events = sse_events(response.text)
    assert any(kind == "change_update" for kind, _ in events)
    assert db.get(CatalogProduct, "LED-3108").price == Decimal("11.4000")

    pending = client.get(f"{BASE}/operations/changes", headers=headers).json()["pending"]
    assert len(pending) == 1
    change_id = pending[0]["change_id"]
    assert pending[0]["margin_before_pct"] == 24.6

    response = client.post(f"{BASE}/operations/changes/{change_id}/apply", headers=headers)
    assert response.status_code == 403

    user.role = "operator"
    db.commit()
    response = client.post(f"{BASE}/operations/changes/{change_id}/apply", headers=headers)
    assert response.status_code == 200, response.text
    assert response.json()["ok"] is True
    db.expire_all()
    assert db.get(CatalogProduct, "LED-3108").price == Decimal("10.9000")
    assert db.get(CommerceStagedChange, change_id).status == "applied"

    overview = client.get(f"{BASE}/operations/overview", headers=headers).json()
    assert overview["recent_changes"][0]["change_id"] == change_id
    assert overview["snapshot"]["alerts"]["pending_changes"] == 0


def test_console_refuses_drifted_and_expired_changes(commerce):
    client, db, user, _, install = commerce
    user.role = "operator"
    db.commit()
    install(
        tool_use_message("search_listings", {"query": "MUG-2204 KIT-4410"}),
        tool_use_message("stage_price_update", {"items": [{"listing_id": "MUG-2204", "new_price": 2.05}]}),
        tool_use_message("stage_inventory_action", {"items": [{"listing_id": "KIT-4410", "action": "pause"}]}),
        text_message("Both changes are staged."),
    )
    headers = operations_session(client)
    client.post(f"{BASE}/operations/chat", headers=headers, json={"message": "Raise MUG-2204 and pause KIT-4410"})
    pending = {change["kind"]: change["change_id"] for change in client.get(f"{BASE}/operations/changes", headers=headers).json()["pending"]}

    db.get(CatalogProduct, "MUG-2204").price = Decimal("1.99")
    db.commit()
    response = client.post(f"{BASE}/operations/changes/{pending['price_update']}/apply", headers=headers).json()
    assert response["ok"] is False
    assert "was 1.95 when staged" in response["reason"]

    row = db.get(CommerceStagedChange, pending["inventory_action"])
    document = dict(row.document_json)
    created = document["created_at"].replace("Z", "+00:00")
    from datetime import datetime

    document["created_at"] = (datetime.fromisoformat(created) - timedelta(days=2)).isoformat()
    row.document_json = document
    db.commit()
    response = client.post(f"{BASE}/operations/changes/{pending['inventory_action']}/apply", headers=headers).json()
    assert response["ok"] is False
    assert response["change"]["status"] == "expired"
    db.expire_all()
    assert db.get(CatalogProduct, "KIT-4410").status == "active"


def test_guardrails_hold_oversized_price_moves(commerce):
    client, db, _, _, install = commerce
    install(
        tool_use_message("search_listings", {"query": "LED-3108"}),
        tool_use_message("stage_price_update", {"items": [{"listing_id": "LED-3108", "new_price": 15.0}]}),
        text_message("That move is above the limit."),
    )
    headers = operations_session(client)
    response = client.post(f"{BASE}/operations/chat", headers=headers, json={"message": "Raise LED-3108 to 15"})
    results = [data for kind, data in sse_events(response.text) if kind == "tool_result" and data.get("tool") == "stage_price_update"]
    assert results and (results[0].get("is_error") or results[0].get("status") in ("blocked", "error"))
    assert db.query(CommerceStagedChange).count() == 0


def test_handoff_opens_a_ticket_with_a_brief(commerce):
    client, _, _, customer, install = commerce
    install(
        tool_use_message("search_policies", {"query": "payment terms deposit"}),
        text_message("Our payment terms are 30% deposit, 70% before shipment."),
    )
    headers = buyer_session(client, customer)
    response = client.post(f"{BASE}/buyer/chat", headers=headers, json={"message": "What are your payment terms? Call me on +49 170 1234567"})
    evidence = [data for kind, data in sse_events(response.text) if kind == "tool_result"]
    versions = {(item["source_id"], item["version"], item["status"]) for data in evidence for item in data.get("evidence") or []}
    assert ("terms/payment", "2", "current") in versions

    response = client.post(f"{BASE}/buyer/handoff", headers=headers, json={"reason": "user_requested"})
    ticket = response.json()
    assert ticket["ticket"].startswith("H-")
    assert "[removed]" in ticket["brief"]["request"]
    assert "1234567" not in ticket["brief"]["request"]

    queue = client.get(f"{BASE}/handoffs").json()
    assert [item["ticket"] for item in queue] == [ticket["ticket"]]
    assert client.post(f"{BASE}/handoffs/{ticket['ticket']}/resolve").status_code == 200
    assert client.get(f"{BASE}/handoffs").json() == []


def test_unconfigured_model_reports_a_readable_error(commerce):
    client, db, _, customer, _ = commerce

    @contextmanager
    def scope():
        yield db

    class Empty:
        COMMERCE_MODEL_PROVIDER = "openai-compatible"
        COMMERCE_MODEL_BASE_URL = "http://127.0.0.1:9/v1"
        COMMERCE_MODEL_NAME = "unset"
        COMMERCE_MODEL_FAST_NAME = ""
        COMMERCE_MODEL_API_KEY = ""
        OPENAI_API_BASE = ""
        LLM_BACKEND = "direct"
        OMNIROUTE_BASE_URL = ""
        OMNIROUTE_TIMEOUT_SECONDS = 5.0

        @staticmethod
        def omniroute_model_aliases():
            return {}

    choice = resolve_model(Empty())
    assert choice.configured is False
    runtime = CommerceRuntime(scope=scope, choice=choice)
    app.dependency_overrides[get_commerce_runtime] = lambda: runtime
    headers = buyer_session(client, customer)
    response = client.post(f"{BASE}/buyer/chat", headers=headers, json={"message": "hello", "locale": "zh"})
    errors = [data for kind, data in sse_events(response.text) if kind == "error"]
    assert errors and "尚未配置 AI 模型" in json.dumps(errors, ensure_ascii=False)


def test_catalog_admin_requires_superuser_and_validates_terms(commerce):
    client, db, user, _, _ = commerce
    payload = {"id": "PKG-9001", "title": "Kraft mailer box", "price": "0.42", "moq": 2000}
    assert client.put(f"{BASE}/catalog/products/PKG-9001", json=payload).status_code == 403

    user.is_superuser = True
    db.commit()
    response = client.put(f"{BASE}/catalog/products/PKG-9001", json=payload)
    assert response.status_code == 200
    assert response.json()["listing_id"] == "PKG-9001"
    assert any(item["listing_id"] == "PKG-9001" for item in client.get(f"{BASE}/catalog/products").json())

    term = {
        "source_id": "terms/payment",
        "version": "2",
        "title": "Payment terms",
        "content": "A duplicate version must be refused by the API.",
        "effective_at": "2026-02-01T00:00:00Z",
    }
    assert client.post(f"{BASE}/catalog/terms", json=term).status_code == 409
    in_force = {row["id"]: row["in_force"] for row in client.get(f"{BASE}/catalog/terms").json()}
    assert in_force["terms/payment@2"] is True
    assert in_force["terms/payment@1"] is False


def test_operations_sessions_are_private_to_their_operator(commerce):
    client, db, user, _, _ = commerce
    headers = operations_session(client)
    other = User(username="other-op", email="other-op@example.com", hashed_password="x", is_active=True)
    db.add(other)
    db.commit()
    app.dependency_overrides[get_current_active_user] = lambda: other
    try:
        assert client.get(f"{BASE}/operations/changes", headers=headers).status_code == 401
    finally:
        app.dependency_overrides[get_current_active_user] = lambda: user
