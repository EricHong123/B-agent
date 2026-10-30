# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

import copy
from datetime import datetime, timedelta, timezone

from commerce_common.prompt_assembly import (
    build_request_messages,
    build_system_blocks,
    context_clock,
    with_eager_input,
    with_tool_cache_control,
)

CONTEXT = "# Session context\n<data>{}</data>"


def test_system_is_the_marked_static_block_then_the_context():
    static, context = build_system_blocks("# Static identity and rules", CONTEXT)
    assert static == {
        "type": "text",
        "text": "# Static identity and rules",
        "cache_control": {"type": "ephemeral"},
    }
    assert context == {"type": "text", "text": CONTEXT}


def test_the_context_clock_is_the_hour_in_the_sessions_offset():
    lisbon_summer = timezone(timedelta(hours=1))
    assert context_clock(datetime(2026, 5, 30, 10, 37, 12, tzinfo=lisbon_summer)) == (
        "2026-05-30T10:00+01:00"
    )
    # Two turns in the same hour render the same bytes, so the block stays cached.
    assert context_clock(datetime(2026, 5, 30, 10, 2)) == context_clock(
        datetime(2026, 5, 30, 10, 58)
    )


def test_tool_cache_control_marks_only_the_last_tool_and_copies():
    tools = [
        {"name": "search_products", "input_schema": {"type": "object"}},
        {"name": "get_cart", "input_schema": {"type": "object"}},
    ]
    marked = with_tool_cache_control(tools)
    assert "cache_control" in marked[-1]
    assert all("cache_control" not in t for t in marked[:-1])
    assert "cache_control" not in tools[-1]


def test_eager_input_marks_the_named_tools_on_a_copy():
    tools = [
        {"name": "search_products", "input_schema": {"type": "object"}},
        {"name": "present_products", "input_schema": {"type": "object"}},
        {"type": "web_search_20250305", "name": "web_search"},
    ]
    marked = with_tool_cache_control(with_eager_input(tools, {"present_products"}))
    assert [t.get("eager_input_streaming") for t in marked] == [None, True, None]
    assert "cache_control" in marked[-1]
    assert all("eager_input_streaming" not in t for t in tools)


def test_tool_cache_control_empty_list_is_a_noop():
    assert with_tool_cache_control([]) == []


# -- the rolling conversation breakpoint --------------------------------------------------


def grown_conversation() -> list[dict]:
    return [
        {"role": "user", "content": "show me tents"},
        {"role": "assistant", "content": [{"type": "text", "text": "Here are two."}]},
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "tu-1", "content": "ok"},
                {"type": "tool_result", "tool_use_id": "tu-2", "content": "ok"},
            ],
        },
    ]


def test_marker_on_the_newest_persisted_block_only():
    request = build_request_messages(grown_conversation())
    results = request[-1]["content"]
    assert results[-1]["cache_control"] == {"type": "ephemeral"}
    assert results[-1]["tool_use_id"] == "tu-2"
    assert "cache_control" not in results[0]
    assert "cache_control" not in request[1]["content"][0]
    assert request[0] == {"role": "user", "content": "show me tents"}
    assert len(request) == 3


def test_string_content_is_lifted_without_mutating_history():
    messages = grown_conversation()[:2] + [{"role": "user", "content": "cheaper?"}]
    request = build_request_messages(messages)
    assert request[-1]["content"] == [
        {"type": "text", "text": "cheaper?", "cache_control": {"type": "ephemeral"}}
    ]
    # The host's persisted history is untouched — markers exist per request.
    assert messages[-1]["content"] == "cheaper?"
    assert all(
        "cache_control" not in block
        for message in messages
        for block in (message["content"] if isinstance(message["content"], list) else [])
    )


def _marked(request: list[dict]) -> list[dict]:
    return [
        block
        for message in request
        for block in (message["content"] if isinstance(message["content"], list) else [])
        if isinstance(block, dict) and "cache_control" in block
    ]


def test_the_marker_rolls_forward_stripping_the_previous_one():
    earlier = build_request_messages(grown_conversation())
    # As if the host had persisted a marked request by mistake: the next call strips it.
    later = build_request_messages(
        earlier
        + [
            {"role": "assistant", "content": [{"type": "text", "text": "The first is lighter."}]},
            {"role": "user", "content": "the cheaper one"},
        ]
    )
    assert _marked(later) == [later[-1]["content"][0]]
    assert later[-1]["content"][0]["text"] == "the cheaper one"


def test_a_user_message_after_tool_results_goes_out_as_one_message():
    """A turn that closed on a presentation round leaves tool results, then the user's
    next message (a string, or the app's events plus the text): one request message, tool
    results first, the marker on its last block, the persisted history untouched."""
    texts = [{"type": "text", "text": "[app] cart: 1 item"}, {"type": "text", "text": "check out"}]
    for follow_up in ("the cheaper one", texts):
        messages = grown_conversation() + [{"role": "user", "content": follow_up}]
        snapshot = copy.deepcopy(messages)
        request = build_request_messages(messages)
        assert len(request) == 3 and messages == snapshot
        content = request[-1]["content"]
        last = texts[-1] if follow_up is texts else {"type": "text", "text": follow_up}
        assert [block["type"] for block in content[:3]] == ["tool_result", "tool_result", "text"]
        assert content[-1] == last | {"cache_control": {"type": "ephemeral"}}
        assert _marked(request) == [content[-1]]
    unmarked = build_request_messages(messages, rolling_breakpoint=False)
    assert len(unmarked) == 3 and unmarked[-1]["content"][2:] == texts


def test_a_bare_first_call_is_sent_unmarked_and_unchanged():
    messages = [{"role": "user", "content": "hello"}]
    assert build_request_messages(messages) == messages


def test_rolling_breakpoint_off_sends_the_messages_unmarked():
    request = build_request_messages(grown_conversation(), rolling_breakpoint=False)
    assert request == grown_conversation()


def test_empty_messages_are_a_noop():
    assert build_request_messages([]) == []
