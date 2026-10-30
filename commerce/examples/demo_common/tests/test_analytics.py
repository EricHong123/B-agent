# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

import json

from fastapi import FastAPI
from fastapi.testclient import TestClient

from commerce_common.streaming import AgentEvent
from demo_common import SESSION_HEADER, SessionStore, session_dependency
from demo_common.analytics import (
    REQUEST_MAX_CHARS,
    OperationsLog,
    handoff_request,
    install_operations_routes,
)
from shopping_agent import ShoppingSessionState


def lines(log: OperationsLog) -> list[dict]:
    assert log.path is not None
    return [json.loads(line) for line in log.path.read_text().splitlines()]


def test_a_turn_record_holds_evidence_and_outcome_but_no_text(tmp_path):
    log = OperationsLog(tmp_path / "storefront.jsonl", vertical="retail", role="storefront")
    recorder = log.turn("session-1", "zh")
    events = [
        AgentEvent.text_delta("A private sentence."),
        AgentEvent.tool_call("get_product_details", "tu-1", {"product_id": "AR-1"}),
        AgentEvent.tool_result("get_product_details", "tu-1", "ok"),
        AgentEvent.tool_call("add_to_cart", "tu-2", {"product_id": "AR-9", "quantity": 1}),
        AgentEvent.tool_result(
            "add_to_cart", "tu-2", "held", status="blocked", reason="provenance"
        ),
        AgentEvent.cart_update({"items": []}),
        AgentEvent.turn_complete("end_turn", {"input_tokens": 9}, 1200, 0),
    ]
    sent = [recorder.observe(event) for event in events]
    recorder.write()
    assert sent[-1].data["turn_id"] == recorder.turn_id
    (record,) = lines(log)
    assert record["kind"] == "turn" and record["locale"] == "zh" and record["vertical"] == "retail"
    assert record["evidence_ids"] == ["AR-1", "AR-9"]
    assert [tool["status"] for tool in record["tools"]] == ["ok", "blocked"]
    assert record["blocked"] == [{"tool": "add_to_cart", "reason": "provenance"}]
    assert record["writes"] == ["cart"] and record["elapsed_ms"] == 1200
    assert record["fallback_reason"] == "gate_held:provenance"
    assert "private" not in json.dumps(record) and "session-1" not in json.dumps(record)


def test_a_terms_read_logs_the_version_of_each_source(tmp_path):
    log = OperationsLog(tmp_path / "storefront.jsonl", vertical="retail", role="storefront")
    recorder = log.turn("session-1", None)
    evidence = [
        {"source_id": "retail/returns", "version": "1", "status": "superseded"},
        {"source_id": "retail/returns", "version": "2", "status": "current"},
    ]
    recorder.observe(AgentEvent.tool_call("search_policies", "tu-1", {"query": "returns"}))
    recorder.observe(AgentEvent.tool_result("search_policies", "tu-1", "ok", evidence=evidence))
    recorder.write()
    (record,) = lines(log)
    assert record["evidence_versions"] == evidence
    assert record["fallback_reason"] is None


def fallback_of(log: OperationsLog, *events: AgentEvent) -> str | None:
    recorder = log.turn("session-1", None)
    for event in events:
        recorder.observe(event)
    return recorder.fallback_reason()


def test_the_fallback_reason_comes_from_the_turns_events(tmp_path):
    log = OperationsLog(None, vertical="retail", role="storefront")
    lapsed = {"source_id": "retail/promo", "version": "1", "status": "expired"}
    current = {"source_id": "retail/returns", "version": "2", "status": "current"}
    # A withheld source outranks the terms gate that held the call.
    held = AgentEvent.tool_result(
        "search_policies",
        "tu-1",
        "held",
        status="blocked",
        reason="terms_validity",
        evidence=[lapsed],
    )
    assert fallback_of(log, held) == "terms_withheld"
    partly = AgentEvent.tool_result("search_policies", "tu-1", "ok", evidence=[lapsed, current])
    assert fallback_of(log, partly) == "terms_withheld"
    empty = AgentEvent.tool_result("search_policies", "tu-1", "nothing", no_match=True)
    assert fallback_of(log, empty) == "no_terms_match"
    gate = AgentEvent.tool_result("checkout", "tu-2", "held", status="blocked", reason="cap")
    assert fallback_of(log, empty, gate) == "no_terms_match"
    assert fallback_of(log, gate) == "gate_held:cap"
    answered = AgentEvent.tool_result("search_policies", "tu-1", "ok", evidence=[current])
    assert fallback_of(log, answered, AgentEvent.text_delta("No matching policy content.")) is None


def test_votes_and_handoffs_are_accepted_only_for_the_sessions_own_turns(tmp_path):
    log = OperationsLog(tmp_path / "storefront.jsonl", vertical="retail", role="storefront")
    store: SessionStore[ShoppingSessionState] = SessionStore(ShoppingSessionState)
    current = session_dependency(store, "/api/session")
    app = FastAPI()
    install_operations_routes(
        app, "/api", current_session=current, log=log, handoff_note="ticket {ticket}"
    )
    client = TestClient(app)
    mine, other = store.start("u-1"), store.start("u-2")
    turn_id = log.turn(mine.session_id, None).turn_id
    headers = {SESSION_HEADER: mine.session_id}

    vote = client.post(
        "/api/feedback", json={"turn_id": turn_id, "helpful": False}, headers=headers
    )
    assert vote.status_code == 200
    stranger = {SESSION_HEADER: other.session_id}
    assert (
        client.post(
            "/api/feedback", json={"turn_id": turn_id, "helpful": True}, headers=stranger
        ).status_code
        == 404
    )
    assert (
        client.post("/api/feedback", json={"turn_id": turn_id, "helpful": True}).status_code == 401
    )

    handoff = client.post(
        "/api/handoff",
        json={"turn_id": turn_id, "reason": "after_negative_feedback"},
        headers=headers,
    )
    ticket = handoff.json()["ticket"]
    assert ticket.startswith("H-")
    assert store.require(mine.session_id).pending_app_events == [f"ticket {ticket}"]
    kinds = [(record["kind"], record.get("reason")) for record in lines(log)]
    assert kinds == [("feedback", None), ("handoff", "after_negative_feedback")]


def test_a_handoff_from_a_turn_that_fell_back_is_rule_triggered(tmp_path):
    log = OperationsLog(tmp_path / "storefront.jsonl", vertical="retail", role="storefront")
    store: SessionStore[ShoppingSessionState] = SessionStore(ShoppingSessionState)
    app = FastAPI()
    install_operations_routes(
        app,
        "/api",
        current_session=session_dependency(store, "/api/session"),
        log=log,
        handoff_note="ticket {ticket}",
    )
    client = TestClient(app)
    session = store.start("u-1")
    headers = {SESSION_HEADER: session.session_id}
    fell_back = log.turn(session.session_id, None)
    fell_back.observe(AgentEvent.tool_result("search_policies", "tu-1", "none", no_match=True))
    fell_back.write()
    answered = log.turn(session.session_id, None)
    answered.write()

    for turn_id, reason in [
        (fell_back.turn_id, "user_requested"),
        (fell_back.turn_id, "after_negative_feedback"),
        (fell_back.turn_id, "after_error"),
        (answered.turn_id, "user_requested"),
        (None, "user_requested"),
    ]:
        response = client.post(
            "/api/handoff", json={"turn_id": turn_id, "reason": reason}, headers=headers
        )
        assert response.status_code == 200
    recorded = [record["reason"] for record in lines(log) if record["kind"] == "handoff"]
    assert recorded == [
        "rule_triggered",
        "rule_triggered",
        "after_error",
        "user_requested",
        "user_requested",
    ]
    # The client cannot claim the server's reason.
    claimed = client.post("/api/handoff", json={"reason": "rule_triggered"}, headers=headers)
    assert claimed.status_code == 422


def test_a_handoff_carries_a_brief_built_from_the_sessions_turns(tmp_path):
    log = OperationsLog(tmp_path / "storefront.jsonl", vertical="retail", role="storefront")
    store: SessionStore[ShoppingSessionState] = SessionStore(ShoppingSessionState)
    app = FastAPI()
    install_operations_routes(
        app,
        "/api",
        current_session=session_dependency(store, "/api/session"),
        log=log,
        handoff_note="ticket {ticket}",
    )
    client = TestClient(app)
    session, other = store.start("u-1"), store.start("u-2")
    lapsed = {"source_id": "retail/promo", "version": "1", "status": "expired"}
    current = {"source_id": "retail/returns", "version": "2", "status": "current"}

    first = log.turn(session.session_id, None)
    for event in [
        AgentEvent.tool_call("get_order_status", "tu-1", {"order_id": "AO-1"}),
        AgentEvent.tool_result("get_order_status", "tu-1", "ok"),
        AgentEvent.tool_call("search_policies", "tu-2", {"query": "returns"}),
        AgentEvent.tool_result("search_policies", "tu-2", "ok", evidence=[current]),
        AgentEvent.tool_call("present_suggestions", "tu-3", {}),
    ]:
        first.observe(event)
    first.write()
    second = log.turn(session.session_id, None)
    for event in [
        AgentEvent.tool_call("search_policies", "tu-4", {"query": "promo"}),
        AgentEvent.tool_result("search_policies", "tu-4", "ok", evidence=[lapsed, current]),
        AgentEvent.tool_call("add_to_cart", "tu-5", {"product_id": "AR-9"}),
        AgentEvent.tool_result("add_to_cart", "tu-5", "held", status="blocked", reason="cap"),
    ]:
        second.observe(event)
    second.write()
    elsewhere = log.turn(other.session_id, None)
    elsewhere.observe(AgentEvent.tool_call("get_cart", "tu-9", {}))
    elsewhere.write()

    record = store.require(session.session_id)
    record.messages = [
        {"role": "user", "content": "Where is my order?"},
        {"role": "assistant", "content": "It shipped."},
        {
            "role": "user",
            "content": [
                {"type": "text", "text": "[App events since your last reply: cart cleared]"},
                {"type": "text", "text": "Card 4111 1111 1111 1111 was charged twice,  refund it."},
            ],
        },
        {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "tu-5"}]},
    ]
    store.save(record)

    response = client.post(
        "/api/handoff",
        json={"turn_id": second.turn_id},
        headers={SESSION_HEADER: session.session_id},
    )
    body = response.json()
    assert body["brief"] == {
        "request": "Card [removed] was charged twice, refund it.",
        "tried": {
            "tools": [
                {"name": "get_order_status", "status": "ok"},
                {"name": "search_policies", "status": "ok"},
                {"name": "add_to_cart", "status": "blocked"},
            ],
            "held": [{"tool": "add_to_cart", "reason": "cap"}],
            "fallbacks": ["terms_withheld"],
        },
        "evidence_versions": [current, lapsed],
        "reason": "rule_triggered",
    }
    (handoff,) = [line for line in lines(log) if line["kind"] == "handoff"]
    assert handoff["ticket"] == body["ticket"]
    assert {key: handoff[key] for key in body["brief"]} == body["brief"]
    assert session.session_id not in json.dumps(handoff) and "4111" not in json.dumps(handoff)


def test_the_brief_request_skips_host_texts_and_is_cut_short():
    reminder = "[a host reminder]"
    long = "word " * 100
    messages = [
        {"role": "user", "content": long},
        {"role": "user", "content": [{"type": "text", "text": reminder}]},
    ]
    request = handoff_request(messages, {reminder})
    assert len(request) == REQUEST_MAX_CHARS and request.endswith("…")
    assert handoff_request(messages[1:], {reminder}) == ""
    assert handoff_request([{"role": "user", "content": "mail me at a.b@example.com"}]) == (
        "mail me at [removed]"
    )


def test_logging_can_be_switched_off(tmp_path, monkeypatch):
    monkeypatch.setenv("DEMO_ANALYTICS", "0")
    log = OperationsLog.for_example(tmp_path / "retail", "storefront")
    log.feedback("s", "t", True)
    assert log.path is None and not (tmp_path / "retail").exists()


def test_a_turn_record_names_its_model_and_provider(tmp_path):
    log = OperationsLog(tmp_path / "storefront.jsonl", vertical="retail", role="storefront")
    log.turn("session-1", None, model="deepseek-chat", provider="deepseek").write()
    log.turn("session-1", None).write()
    named, unnamed = lines(log)
    assert (named["provider"], named["model"]) == ("deepseek", "deepseek-chat")
    assert (unnamed["provider"], unnamed["model"]) == (None, None)


def test_a_streamed_turn_logs_the_settings_model_but_no_key_or_endpoint(tmp_path, monkeypatch):
    from commerce_common.testing import FakeClient
    from demo_common.host import stream_turn
    from demo_common.model_provider import ModelSettings, save_settings
    from shopping_agent import ShoppingAgentConfig
    from shopping_agent_runtime import ShoppingAgent

    monkeypatch.setenv("DEMO_MODEL_SETTINGS_FILE", str(tmp_path / "model-settings.json"))
    save_settings(
        ModelSettings(
            provider="openai-compatible",
            api_key="sk-acme-secret",
            base_url="https://user:pass@llm.acme.test/v1",
            model="acme-chat",
        )
    )

    class Agent(ShoppingAgent):
        async def stream_turn(self, messages, session, state):
            yield AgentEvent.turn_complete("end_turn", {"input_tokens": 1}, 10, 0)

        async def update_memory(self, messages, session):
            return None

    agent = Agent(backend=None, config=ShoppingAgentConfig(), client=FakeClient([]))
    log = OperationsLog(tmp_path / "storefront.jsonl", vertical="retail", role="storefront")
    store: SessionStore[ShoppingSessionState] = SessionStore(ShoppingSessionState)
    record = store.start("u-1")
    app = FastAPI()

    @app.get("/chat")
    def chat():
        return stream_turn(agent, store, record, None, env_hint=".env", log=log)

    assert "turn_complete" in TestClient(app).get("/chat").text
    (logged,) = lines(log)
    assert (logged["provider"], logged["model"]) == ("openai-compatible", "acme-chat")
    text = json.dumps(logged)
    assert "sk-acme-secret" not in text and "acme.test" not in text and "pass" not in text
