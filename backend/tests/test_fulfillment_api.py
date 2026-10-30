from datetime import datetime, timedelta, timezone
from uuid import UUID

import pytest

from app.api.v1.auth import get_current_active_user
from app.main import app
from app.models.database import (
    Conversation,
    ConversationStatus,
    Customer,
    FulfillmentEvent,
    Message,
    SalesQuotation,
    User,
)


BASE = "/api/v1/fulfillment"


def utc_today():
    return datetime.now(timezone.utc).date()


def seed_customer(db, **overrides):
    values = {
        "username": "acme-buyer",
        "platform": "email",
        "email": "buyer@acme.example",
        "company_name": "Acme Imports",
        "status": "contacted",
        "custom_fields": {},
    }
    values.update(overrides)
    customer = Customer(**values)
    db.add(customer)
    db.commit()
    db.refresh(customer)
    return customer


def seed_inquiry(db, customer):
    conversation = Conversation(
        customer_id=customer.id,
        platform="email",
        status=ConversationStatus.ACTIVE,
        current_intent="price_inquiry",
        intent_confidence=0.82,
    )
    db.add(conversation)
    db.flush()
    db.add(
        Message(
            conversation_id=conversation.id,
            role="user",
            content="Please quote 2,000 pcs stainless bottles, FOB Ningbo.",
        )
    )
    db.commit()
    db.refresh(conversation)
    return conversation


def qualified_opportunity(client, customer_id):
    response = client.post(
        f"{BASE}/opportunities",
        json={
            "customer_id": customer_id,
            "title": "Stainless bottles for Q1 retail",
            "requirements": {"product": "Stainless bottle 500ml", "quantity": "2000"},
        },
    )
    assert response.status_code == 201, response.text
    opportunity = response.json()
    response = client.post(
        f"{BASE}/opportunities/{opportunity['id']}/transition",
        json={"stage": "qualified"},
    )
    assert response.status_code == 200, response.text
    return response.json()


def quotation_payload(**overrides):
    payload = {
        "currency": "USD",
        "incoterm": "FOB",
        "deposit_percent": 30,
        "lead_time_days": 25,
        "valid_days": 10,
        "line_items": [
            {
                "product": "Stainless bottle 500ml",
                "quantity": "2000",
                "unit": "pcs",
                "unit_price": "4.50",
                "unit_cost": "3.20",
            }
        ],
        "freight_amount": "0",
        "discount_amount": "0",
    }
    payload.update(overrides)
    return payload


def sent_quotation(client, opportunity_id, **overrides):
    response = client.post(
        f"{BASE}/opportunities/{opportunity_id}/quotations",
        json=quotation_payload(**overrides),
    )
    assert response.status_code == 201, response.text
    quote = response.json()
    assert client.post(f"{BASE}/quotations/{quote['id']}/submit").status_code == 200
    response = client.post(
        f"{BASE}/quotations/{quote['id']}/review",
        json={"decision": "approve", "reason": "Margin and terms ok"},
    )
    assert response.status_code == 200, response.text
    response = client.post(f"{BASE}/quotations/{quote['id']}/send", json={"channel": "email"})
    assert response.status_code == 200, response.text
    return response.json()


def accepted_order(client, db, **accept):
    customer = seed_customer(db)
    opportunity = qualified_opportunity(client, customer.id)
    quote = sent_quotation(client, opportunity["id"])
    response = client.post(
        f"{BASE}/quotations/{quote['id']}/accept",
        json={"fulfillment_mode": "in_house", **accept},
    )
    assert response.status_code == 201, response.text
    return response.json()


def transition(client, order_id, status, **extra):
    return client.post(
        f"{BASE}/orders/{order_id}/transition",
        json={"status": status, **extra},
    )


def pay(client, order_id, key, amount, kind="deposit"):
    return client.post(
        f"{BASE}/orders/{order_id}/payments",
        json={
            "idempotency_key": key,
            "kind": kind,
            "amount": amount,
            "currency": "USD",
            "method": "tt",
            "reference": "SWIFT-REF",
        },
    )


def test_lead_to_delivery_closes_the_loop(api_context):
    client, db, _ = api_context
    customer = seed_customer(db)
    conversation = seed_inquiry(db, customer)

    response = client.post(
        f"{BASE}/opportunities/from-conversation/{conversation.id}",
        json={"requirements": {"product": "Stainless bottle 500ml", "quantity": "2000"}},
    )
    assert response.status_code == 201, response.text
    opportunity = response.json()
    assert opportunity["source"] == "conversation"
    assert "2,000 pcs" in opportunity["inquiry_summary"]
    db.refresh(customer)
    assert customer.status == "engaged"

    replay = client.post(
        f"{BASE}/opportunities/from-conversation/{conversation.id}",
        json={},
    )
    assert replay.status_code == 200
    assert replay.json()["id"] == opportunity["id"]

    response = client.post(
        f"{BASE}/opportunities/{opportunity['id']}/transition",
        json={"stage": "qualified"},
    )
    assert response.status_code == 200
    quote = sent_quotation(client, opportunity["id"])
    assert quote["total"] == "9000.00"
    assert quote["margin_percent"] == "28.89"
    assert client.get(f"{BASE}/opportunities/{opportunity['id']}").json()["stage"] == "negotiation"

    response = client.post(
        f"{BASE}/quotations/{quote['id']}/accept",
        json={"fulfillment_mode": "in_house", "customer_po_number": "PO-7781"},
    )
    assert response.status_code == 201, response.text
    order = response.json()
    order_id = order["id"]
    assert order["status"] == "confirmed"
    assert order["deposit_required"] == "2700.00"
    assert order["required_ship_date"] == (utc_today() + timedelta(days=25)).isoformat()
    won = client.get(f"{BASE}/opportunities/{opportunity['id']}").json()
    assert won["stage"] == "won"
    assert won["order_id"] == order_id
    db.refresh(customer)
    assert customer.status == "converted"

    blocked = transition(client, order_id, "in_production")
    assert blocked.status_code == 409
    blockers = blocked.json()["detail"]["blockers"]
    assert any("Deposit" in item for item in blockers)
    assert any("work order" in item for item in blockers)

    assert pay(client, order_id, "deposit-0001", "2700.00").status_code == 201
    response = client.post(
        f"{BASE}/orders/{order_id}/production-tasks",
        json={
            "kind": "work_order",
            "description": "Deep-draw and polish bottles",
            "quantity": "2000",
            "production_line": "Line 2",
            "planned_finish": (utc_today() + timedelta(days=20)).isoformat(),
        },
    )
    assert response.status_code == 201, response.text
    task_id = response.json()["production_tasks"][0]["id"]
    assert transition(client, order_id, "in_production").status_code == 200

    response = client.patch(
        f"{BASE}/orders/{order_id}/production-tasks/{task_id}",
        json={"status": "in_progress"},
    )
    assert response.status_code == 200
    response = client.patch(
        f"{BASE}/orders/{order_id}/production-tasks/{task_id}",
        json={"progress_percent": 60},
    )
    assert response.json()["production_progress_percent"] == 60
    assert transition(client, order_id, "quality_check").status_code == 409
    client.patch(
        f"{BASE}/orders/{order_id}/production-tasks/{task_id}",
        json={"status": "completed"},
    )
    assert transition(client, order_id, "quality_check").status_code == 200

    failed = client.post(
        f"{BASE}/orders/{order_id}/inspections",
        json={
            "stage": "pre_shipment",
            "result": "failed",
            "inspector": "SGS Ningbo",
            "defects": [{"description": "Scratched surface", "severity": "major", "count": 14}],
        },
    )
    assert failed.status_code == 201
    blocked = transition(client, order_id, "ready_to_ship")
    assert "failed" in blocked.json()["detail"]["blockers"][0]
    client.post(
        f"{BASE}/orders/{order_id}/inspections",
        json={"stage": "pre_shipment", "result": "passed", "inspector": "SGS Ningbo"},
    )
    assert transition(client, order_id, "ready_to_ship").status_code == 200

    response = client.post(
        f"{BASE}/orders/{order_id}/shipments",
        json={"transport_mode": "sea", "carrier": "COSCO", "port_of_loading": "Ningbo"},
    )
    shipment_id = response.json()["shipments"][0]["id"]
    no_tracking = client.patch(
        f"{BASE}/orders/{order_id}/shipments/{shipment_id}",
        json={"status": "departed"},
    )
    assert no_tracking.status_code == 409
    client.patch(
        f"{BASE}/orders/{order_id}/shipments/{shipment_id}",
        json={"status": "departed", "bill_of_lading": "COSU1234567"},
    )
    blocked = transition(client, order_id, "shipped")
    assert "Balance" in blocked.json()["detail"]["blockers"][0]
    assert pay(client, order_id, "balance-0001", "6300.00", kind="balance").status_code == 201
    assert transition(client, order_id, "shipped").status_code == 200

    assert transition(client, order_id, "delivered").status_code == 409
    client.patch(
        f"{BASE}/orders/{order_id}/shipments/{shipment_id}",
        json={"status": "delivered"},
    )
    assert transition(client, order_id, "delivered").status_code == 200
    response = transition(client, order_id, "completed")
    assert response.status_code == 200
    final = response.json()
    assert final["status"] == "completed"
    assert final["balance_due"] == "0.00"
    assert final["next_transitions"] == []

    events = client.get(f"{BASE}/events", params={"order_id": order_id}).json()
    event_types = [event["event_type"] for event in events]
    assert event_types[0] == "opportunity.created"
    for expected in (
        "quotation.sent",
        "order.created",
        "payment.received",
        "production.planned",
        "quality.inspected",
        "shipment.booked",
    ):
        assert expected in event_types
    assert [event["to_status"] for event in events if event["event_type"] == "order.status_changed"] == [
        "in_production",
        "quality_check",
        "ready_to_ship",
        "shipped",
        "delivered",
        "completed",
    ]

    overview = client.get(f"{BASE}/pipeline").json()
    stages = {stage["key"]: stage for stage in overview["opportunities"]}
    assert stages["won"]["count"] == 1
    assert overview["win_rate_percent"] == "100.00"
    assert overview["booked_value"] == "9000.00"
    assert overview["collected_value"] == "9000.00"
    assert overview["unconverted_inquiries"] == []


def test_qualification_requires_captured_requirements(api_context):
    client, db, _ = api_context
    customer = seed_customer(db)
    response = client.post(
        f"{BASE}/opportunities",
        json={"customer_id": customer.id, "title": "Vague inquiry"},
    )
    opportunity_id = response.json()["id"]

    response = client.post(
        f"{BASE}/opportunities/{opportunity_id}/transition",
        json={"stage": "qualified"},
    )
    assert response.status_code == 409
    assert "product" in response.json()["detail"]

    response = client.post(
        f"{BASE}/opportunities/{opportunity_id}/quotations",
        json=quotation_payload(),
    )
    assert response.status_code == 409

    response = client.post(
        f"{BASE}/opportunities/{opportunity_id}/transition",
        json={"stage": "lost"},
    )
    assert response.status_code == 422


def test_new_revision_supersedes_live_quotation(api_context):
    client, db, _ = api_context
    customer = seed_customer(db)
    opportunity = qualified_opportunity(client, customer.id)
    first = sent_quotation(client, opportunity["id"])

    response = client.post(
        f"{BASE}/opportunities/{opportunity['id']}/quotations",
        json=quotation_payload(discount_amount="200"),
    )
    assert response.status_code == 201
    second = response.json()
    assert second["revision"] == 2
    assert second["total"] == "8800.00"

    quotes = {
        quote["revision"]: quote
        for quote in client.get(f"{BASE}/opportunities/{opportunity['id']}/quotations").json()
    }
    assert quotes[1]["status"] == "superseded"
    response = client.post(f"{BASE}/quotations/{first['id']}/accept", json={})
    assert response.status_code == 409


def test_expired_quotation_cannot_be_accepted(api_context):
    client, db, _ = api_context
    customer = seed_customer(db)
    opportunity = qualified_opportunity(client, customer.id)
    quote = sent_quotation(client, opportunity["id"])
    row = db.get(SalesQuotation, UUID(quote["id"]))
    row.valid_until = utc_today() - timedelta(days=1)
    db.commit()

    response = client.post(f"{BASE}/quotations/{quote['id']}/accept", json={})
    assert response.status_code == 409
    assert "expired" in response.json()["detail"]
    alerts = client.get(f"{BASE}/pipeline").json()["alerts"]
    assert any(alert["kind"] == "quotation_expired" for alert in alerts)


def test_large_or_thin_margin_quote_needs_a_second_admin(api_context):
    client, db, user = api_context
    customer = seed_customer(db)
    opportunity = qualified_opportunity(client, customer.id)
    response = client.post(
        f"{BASE}/opportunities/{opportunity['id']}/quotations",
        json=quotation_payload(
            line_items=[
                {
                    "product": "Stainless bottle 500ml",
                    "quantity": "2000",
                    "unit_price": "4.50",
                    "unit_cost": "4.20",
                }
            ]
        ),
    )
    quote = response.json()
    assert quote["requires_escalated_approval"] is True
    client.post(f"{BASE}/quotations/{quote['id']}/submit")

    response = client.post(
        f"{BASE}/quotations/{quote['id']}/review",
        json={"decision": "approve", "reason": "Self approval"},
    )
    assert response.status_code == 403

    admin = User(
        username="sales-director",
        email="director@example.com",
        hashed_password="unused",
        is_active=True,
        is_superuser=True,
    )
    db.add(admin)
    db.commit()
    app.dependency_overrides[get_current_active_user] = lambda: admin
    try:
        response = client.post(
            f"{BASE}/quotations/{quote['id']}/review",
            json={"decision": "approve", "reason": "Strategic account"},
        )
    finally:
        app.dependency_overrides[get_current_active_user] = lambda: user
    assert response.status_code == 200
    assert response.json()["status"] == "approved"
    assert response.json()["reviewed_by_user_id"] == admin.id


def test_payments_are_idempotent_currency_checked_and_bounded(api_context):
    client, db, _ = api_context
    order = accepted_order(client, db)

    assert pay(client, order["id"], "deposit-0001", "2700.00").status_code == 201
    replay = pay(client, order["id"], "deposit-0001", "2700.00")
    assert replay.status_code == 200
    assert replay.json()["amount_paid"] == "2700.00"
    assert pay(client, order["id"], "deposit-0001", "100.00").status_code == 409
    assert pay(client, order["id"], "too-much-0001", "9000.00").status_code == 409

    response = client.post(
        f"{BASE}/orders/{order['id']}/payments",
        json={
            "idempotency_key": "wrong-currency",
            "kind": "balance",
            "amount": "10",
            "currency": "EUR",
        },
    )
    assert response.status_code == 409


def test_fulfillment_mode_controls_production_task_kind(api_context):
    client, db, _ = api_context
    order = accepted_order(client, db, fulfillment_mode="outsourced")

    response = client.post(
        f"{BASE}/orders/{order['id']}/production-tasks",
        json={"kind": "work_order", "description": "Internal line", "quantity": "10"},
    )
    assert response.status_code == 409
    response = client.post(
        f"{BASE}/orders/{order['id']}/production-tasks",
        json={"kind": "purchase_order", "description": "Bottle blanks", "quantity": "10"},
    )
    assert response.status_code == 422
    response = client.post(
        f"{BASE}/orders/{order['id']}/production-tasks",
        json={
            "kind": "purchase_order",
            "description": "Bottle blanks",
            "quantity": "2000",
            "supplier_name": "Yongkang Metalworks",
        },
    )
    assert response.status_code == 201
    task = response.json()["production_tasks"][0]
    assert task["reference_number"].startswith("PO-")
    assert task["supplier_name"] == "Yongkang Metalworks"


def test_cancel_requires_reason_and_closes_open_production(api_context):
    client, db, _ = api_context
    order = accepted_order(client, db)
    client.post(
        f"{BASE}/orders/{order['id']}/production-tasks",
        json={"kind": "work_order", "description": "Polish", "quantity": "2000"},
    )

    assert transition(client, order["id"], "cancelled").status_code == 422
    response = transition(client, order["id"], "cancelled", reason="Buyer withdrew")
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "cancelled"
    assert body["production_tasks"][0]["status"] == "cancelled"
    assert pay(client, order["id"], "late-deposit", "10").status_code == 409


def test_overdue_production_flags_ship_date_risk(api_context):
    client, db, _ = api_context
    order = accepted_order(
        client,
        db,
        required_ship_date=(utc_today() + timedelta(days=5)).isoformat(),
    )
    client.post(
        f"{BASE}/orders/{order['id']}/production-tasks",
        json={
            "kind": "work_order",
            "description": "Polish",
            "quantity": "2000",
            "planned_finish": (utc_today() + timedelta(days=9)).isoformat(),
        },
    )

    detail = client.get(f"{BASE}/orders/{order['id']}").json()
    assert detail["ship_date_at_risk"] is True
    kinds = {alert["kind"] for alert in client.get(f"{BASE}/pipeline").json()["alerts"]}
    assert {"ship_date_at_risk", "deposit_outstanding"} <= kinds


def test_unconverted_buying_inquiries_surface_in_pipeline(api_context):
    client, db, _ = api_context
    customer = seed_customer(db)
    conversation = seed_inquiry(db, customer)

    overview = client.get(f"{BASE}/pipeline").json()
    assert [item["conversation_id"] for item in overview["unconverted_inquiries"]] == [
        str(conversation.id)
    ]
    assert overview["leads"]["contacted"] == 1


def test_records_are_isolated_between_sales_users(api_context):
    client, db, user = api_context
    order = accepted_order(client, db)

    other = User(
        username="other-rep",
        email="other@example.com",
        hashed_password="unused",
        is_active=True,
    )
    db.add(other)
    db.commit()
    app.dependency_overrides[get_current_active_user] = lambda: other
    try:
        assert client.get(f"{BASE}/orders/{order['id']}").status_code == 404
        assert client.get(f"{BASE}/orders").json() == []
        assert client.get(f"{BASE}/opportunities").json() == []
        assert pay(client, order["id"], "foreign-0001", "10").status_code == 404
        assert client.get(f"{BASE}/pipeline").json()["booked_value"] == "0"
    finally:
        app.dependency_overrides[get_current_active_user] = lambda: user
    assert db.query(FulfillmentEvent).count() > 0


def test_passed_inspection_rejects_critical_defects(api_context):
    client, db, _ = api_context
    order = accepted_order(client, db)
    response = client.post(
        f"{BASE}/orders/{order['id']}/inspections",
        json={
            "stage": "pre_shipment",
            "result": "passed",
            "inspector": "QC team",
            "defects": [{"description": "Leak", "severity": "critical"}],
        },
    )
    assert response.status_code == 422


@pytest.mark.parametrize("stage", ["won", "inquiry"])
def test_manual_won_or_backwards_stage_is_rejected(api_context, stage):
    client, db, _ = api_context
    customer = seed_customer(db)
    opportunity = qualified_opportunity(client, customer.id)
    response = client.post(
        f"{BASE}/opportunities/{opportunity['id']}/transition",
        json={"stage": stage},
    )
    assert response.status_code == 422
