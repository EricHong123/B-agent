# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

import json
import logging
from types import SimpleNamespace

from anthropic.types import Message, TextBlock, Usage

from commerce_common.streaming import AgentEvent, ToolOutcome
from commerce_common.turn import (
    CLEARED_RESULT,
    StreamedRound,
    accumulate_usage,
    compact_history,
    fetched,
    latest_exchange,
    latest_user_text,
    log_model_call,
    outcome_events,
    prompt_tokens,
    round_closes_turn,
    session_tag,
    tool_result_block,
    transcript_text,
    usage_totals,
)

REMINDER = "Host check: stage it."
CONVERSATION = [
    {"role": "user", "content": "first ask"},
    {"role": "assistant", "content": [{"type": "text", "text": "first reply"}]},
    {"role": "user", "content": [{"type": "text", "text": "drop the price"}]},
    {"role": "assistant", "content": [{"type": "tool_use", "id": "t1", "name": "x", "input": {}}]},
    {"role": "user", "content": [{"type": "tool_result", "tool_use_id": "t1", "content": "ok"}]},
    {"role": "assistant", "content": [{"type": "text", "text": "want me to?"}]},
    {"role": "user", "content": [{"type": "text", "text": REMINDER}]},
    {"role": "assistant", "content": [{"type": "text", "text": "staged"}]},
]


def test_latest_user_text_skips_tool_results_and_host_messages():
    assert latest_user_text(CONVERSATION[:1]) == "first ask"
    assert latest_user_text(CONVERSATION[:5]) == "drop the price"
    assert latest_user_text(CONVERSATION, {REMINDER}) == "drop the price"
    assert latest_user_text([{"role": "user", "content": [{"type": "image"}]}]) == ""
    assert latest_user_text([]) == ""


def test_latest_exchange_starts_at_the_users_own_message_on_a_reminded_turn():
    assert latest_exchange(CONVERSATION, {REMINDER}) == CONVERSATION[2:]
    assert latest_exchange(CONVERSATION) == CONVERSATION[6:]


def test_transcript_text_keeps_user_and_assistant_lines_only():
    lines = transcript_text(latest_exchange(CONVERSATION, {REMINDER}), {REMINDER}).splitlines()
    assert lines == ["user: drop the price", "assistant: want me to?", "assistant: staged"]


DISPLAYED = "Displayed."
PRESENTS = {"present_products", "present_suggestions"}
CHIPS = (
    "present_suggestions",
    ToolOutcome(DISPLAYED, [AgentEvent.ui("suggestions", {"suggestions": ["Compare them"]})]),
)


def _clean(name: str, outcome: ToolOutcome) -> bool:
    """The executor's rule: a presentation call, not refused, nothing appended."""
    return name in PRESENTS and not outcome.refused and outcome.result_text == DISPLAYED


def _shown(text: str = DISPLAYED) -> ToolOutcome:
    return ToolOutcome(text, [AgentEvent.ui("products", {"items": []})])


def test_only_a_clean_round_with_the_chips_call_closes_the_turn():
    def closes(*calls: tuple[str, ToolOutcome]) -> bool:
        return round_closes_turn(list(calls), _clean)

    card = ("present_products", _shown())
    assert closes(card, CHIPS) and closes(CHIPS) and closes(card, card, CHIPS)
    assert not closes() and not closes(card)
    # A stage call, a note, a read, a refusal, or failed chips leaves the close to the model.
    assert not closes(("stage_price_update", ToolOutcome("<data>staged</data>")), CHIPS)
    assert not closes(("present_products", _shown(f"{DISPLAYED} Not shown: p-9.")), CHIPS)
    assert not closes(CHIPS, ("search_products", ToolOutcome("<data>[]</data>")))
    assert not closes(CHIPS, ("present_products", ToolOutcome.error("Invalid payload")))
    assert not closes(CHIPS, ("present_products", ToolOutcome.held("provenance", "Held.")))
    assert not closes(card, ("present_suggestions", ToolOutcome.error("Invalid payload")))


def _event(kind: str, index: int, **fields) -> SimpleNamespace:
    return SimpleNamespace(type=kind, index=index, **fields)


def _start(index: int, **block) -> SimpleNamespace:
    content = SimpleNamespace(**block, model_dump=lambda **_: dict(block))
    return _event("content_block_start", index, content_block=content)


def _delta(index: int, **delta) -> SimpleNamespace:
    return _event("content_block_delta", index, delta=SimpleNamespace(**delta))


def test_a_streamed_round_rebuilds_what_arrived_and_marks_the_call_that_never_parsed():
    streamed = StreamedRound()
    events = [
        _start(0, type="thinking", thinking="", signature=""),
        _delta(0, type="thinking_delta", thinking="Two picks fit."),
        _delta(0, type="signature_delta", signature="sig-1"),
        _event("content_block_stop", 0),
        _start(1, type="text", text=""),
        _delta(1, type="text_delta", text="Here they are."),
        _event("content_block_stop", 1),
        _start(2, type="tool_use", id="tu-1", name="search_products", input={}),
        _delta(2, type="input_json_delta", partial_json='{"query": "tent"}'),
        _event("content_block_stop", 2),
        _start(3, type="tool_use", id="tu-2", name="present_products", input={}),
        _delta(3, type="input_json_delta", partial_json='{"picks": [Not JSON'),
    ]
    touched = [streamed.feed(event) for event in events]
    assert [t.id if t else None for t in touched][7:] == ["tu-1", "tu-1", "tu-1", "tu-2", "tu-2"]
    assert streamed.tool_open()
    message, tool_uses, unreadable = streamed.salvaged()
    assert message["role"] == "assistant"
    assert message["content"] == [
        {"type": "thinking", "thinking": "Two picks fit.", "signature": "sig-1"},
        {"type": "text", "text": "Here they are."},
        {"type": "tool_use", "id": "tu-1", "name": "search_products", "input": {"query": "tent"}},
        {"type": "tool_use", "id": "tu-2", "name": "present_products", "input": {}},
    ]
    assert [(t.name, t.input) for t in tool_uses] == [
        ("search_products", {"query": "tent"}),
        ("present_products", {}),
    ]
    assert unreadable == {"tu-2"}
    # Once every tool block has closed, nothing is open and an empty text block is dropped.
    closed = StreamedRound()
    for event in [_start(0, type="text", text=""), *events[7:10]]:
        closed.feed(event)
    assert not closed.tool_open()
    message, _, unreadable = closed.salvaged()
    assert [block["type"] for block in message["content"]] == ["tool_use"] and not unreadable


def test_a_streamed_round_keeps_server_tool_blocks_and_counts_the_streams_usage():
    """A web search round that is abandoned replays with its server blocks (never
    dispatched, citations left out as on a finished round) and its tokens counted."""
    streamed = StreamedRound()
    started = SimpleNamespace(input_tokens=90, cache_read_input_tokens=30, output_tokens=1)
    result = {"type": "web_search_tool_result", "tool_use_id": "ws", "content": []}
    events = [
        SimpleNamespace(type="message_start", message=SimpleNamespace(usage=started)),
        _start(0, type="server_tool_use", id="ws", name="web_search", input={}),
        _delta(0, type="input_json_delta", partial_json='{"query": "shoes"}'),
        _event("content_block_stop", 0),
        _start(1, **result),
        _event("content_block_stop", 1),
        _start(2, type="text", text=""),
        _delta(2, type="citations_delta", citation=SimpleNamespace(title="t")),
        _delta(2, type="text_delta", text="Two fit."),
        _event("content_block_stop", 2),
        _start(3, type="tool_use", id="tu-1", name="present_products", input={}),
        _delta(3, type="input_json_delta", partial_json='{"picks": ['),
        SimpleNamespace(type="message_delta", usage=SimpleNamespace(output_tokens=40)),
    ]
    for event in events:
        streamed.feed(event)
    message, tool_uses, unreadable = streamed.salvaged()
    assert message["content"][:3] == [
        {"type": "server_tool_use", "id": "ws", "name": "web_search", "input": {"query": "shoes"}},
        result,
        {"type": "text", "text": "Two fit."},
    ]
    assert [t.name for t in tool_uses] == ["present_products"] and unreadable == {"tu-1"}
    totals = usage_totals()
    accumulate_usage(totals, streamed)
    counted = {"input_tokens": 90, "output_tokens": 40, "cache_read_input_tokens": 30}
    assert totals == usage_totals() | counted and prompt_tokens(streamed) == 120


class _Backend:
    async def get_cart(self):
        return "cart"

    async def get_preferences(self):
        raise ConnectionError("profile service down")


async def test_fetched_returns_none_for_a_failed_prefetch_and_logs_it(caplog):
    with caplog.at_level(logging.WARNING, logger="commerce_common.turn"):
        assert await fetched(_Backend().get_cart()) == "cart"
        assert await fetched(_Backend().get_preferences()) is None
    (record,) = [r for r in caplog.records if r.name == "commerce_common.turn"]
    assert record.levelno == logging.WARNING
    assert "_Backend.get_preferences" in record.getMessage()
    assert record.exc_info is not None and isinstance(record.exc_info[1], ConnectionError)


def test_outcome_events_stamp_ui_events_and_summarize_long_results():
    outcome = ToolOutcome("x" * 500, [AgentEvent.ui("card", {"a": 1}), AgentEvent.cart_update({})])
    ui, cart, result = outcome_events("tool", "t1", outcome)
    assert ui.data["stream_id"] == "t1" and "stream_id" not in cart.data
    assert result.data["summary"] == "ok" and result.data["excerpt"] == "x" * 500
    assert result.data["status"] == "ok" and "evidence" not in result.data


def test_a_reads_evidence_reaches_its_tool_result():
    evidence = [{"source_id": "shop/returns", "version": "2", "status": "current"}]
    (result,) = outcome_events("tool", "t1", ToolOutcome("ok", evidence=evidence))
    assert result.data["evidence"] == evidence
    assert "no_match" not in result.data
    (empty,) = outcome_events("tool", "t2", ToolOutcome("none", no_match=True))
    assert empty.data["no_match"] is True


def test_held_and_failed_results_keep_their_text():
    (held,) = outcome_events("tool", "t1", ToolOutcome.held("provenance", "h" * 300))
    assert held.data == {
        "tool": "tool",
        "id": "t1",
        "summary": "h" * 300,
        "is_error": False,
        "status": "blocked",
        "reason": "provenance",
    }
    (failed,) = outcome_events("tool", "t2", ToolOutcome.error("no"))
    assert failed.data["status"] == "error" and failed.data["is_error"] is True
    assert tool_result_block("t2", ToolOutcome.error("no")) == {
        "type": "tool_result",
        "tool_use_id": "t2",
        "content": "no",
        "is_error": True,
    }


# -- compaction --------------------------------------------------------------------------


def _long_conversation(rounds: int) -> list[dict]:
    messages: list[dict] = [{"role": "user", "content": "find tents"}]
    for index in range(rounds):
        call_id = f"t{index}"
        messages += [
            {
                "role": "assistant",
                "content": [{"type": "tool_use", "id": call_id, "name": "x", "input": {}}],
            },
            {
                "role": "user",
                "content": [{"type": "tool_result", "tool_use_id": call_id, "content": "x" * 1000}],
            },
        ]
    messages.append({"role": "user", "content": "and a stove"})
    return messages


def _result_bodies(messages: list[dict]) -> list[str]:
    return [
        block["content"]
        for message in messages
        if isinstance(message["content"], list)
        for block in message["content"]
        if block["type"] == "tool_result"
    ]


def test_compaction_waits_for_the_prompt_to_reach_the_limit():
    messages = _long_conversation(4)
    before = [dict(message) for message in messages]
    assert compact_history(messages, 99_000, 100_000, "s-1") == 0
    assert compact_history(messages, 500_000, 0, "s-1") == 0
    assert messages == before


def test_compaction_clears_the_oldest_results_until_the_conversation_is_half_its_size(caplog):
    messages = _long_conversation(6)
    size = len(json.dumps(messages))
    with caplog.at_level(logging.INFO, logger="commerce_common.turn"):
        cleared = compact_history(messages, 100_000, 100_000, "s-1")
    bodies = _result_bodies(messages)
    assert cleared == 4 and bodies == [CLEARED_RESULT] * 4 + ["x" * 1000] * 2
    assert len(json.dumps(messages)) <= size // 2
    assert messages[0]["content"] == "find tents" and messages[-1]["content"] == "and a stove"
    (record,) = caplog.records
    assert (
        f"session={session_tag('s-1')} prompt_tokens=100000 results_cleared=4"
        in record.getMessage()
    )


def test_prompt_tokens_counts_everything_the_model_was_given():
    assert prompt_tokens(_message()) == 240


# -- usage and the model-call record ------------------------------------------------------


def _message() -> Message:
    return Message(
        id="msg_1",
        type="message",
        role="assistant",
        model="claude-test",
        content=[TextBlock(type="text", text="Here you go.")],
        stop_reason="end_turn",
        stop_sequence=None,
        usage=Usage(
            input_tokens=120,
            output_tokens=8,
            cache_read_input_tokens=100,
            cache_creation_input_tokens=20,
        ),
    )


def test_usage_accumulates_all_four_counters():
    totals = usage_totals()
    accumulate_usage(totals, _message())
    accumulate_usage(totals, _message())
    assert totals == {
        "input_tokens": 240,
        "output_tokens": 16,
        "cache_read_input_tokens": 200,
        "cache_creation_input_tokens": 40,
    }


def test_the_model_call_record_lands_on_the_callers_logger_with_bodies_at_debug(caplog):
    caller = logging.getLogger("shopping_agent_runtime.orchestrator")
    request = {"model": "claude-test", "messages": [{"role": "user", "content": "tents"}]}
    with caplog.at_level(logging.INFO, logger=caller.name):
        log_model_call(caller, request, _message(), 0.0, "s-1", round=0)
    (info,) = caplog.records
    assert info.name == caller.name
    line = info.getMessage()
    assert f"session={session_tag('s-1')} round=0 model=claude-test stop=end_turn" in line
    assert "s-1" not in line
    assert "input=120 cache_read=100 cache_write=20 output=8 elapsed_ms=" in line
    caplog.clear()
    with caplog.at_level(logging.DEBUG, logger=caller.name):
        log_model_call(caller, request, _message(), 0.0, "s-1", round=0)
    _, sent, received = caplog.records
    assert '"content": "tents"' in sent.getMessage() and "Here you go." in received.getMessage()


def test_session_tag_is_stable_short_and_not_the_id():
    tag = session_tag("sess-credential-1")
    assert tag == session_tag("sess-credential-1") and len(tag) == 12
    assert tag not in "sess-credential-1" and session_tag(None) == "-"
