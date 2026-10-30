# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

from commerce_common.openai_compat import (
    ModelAuthenticationError,
    ModelProviderError,
    OpenAICompatibleClient,
    chat_request,
)
from commerce_common.turn import StreamedRound


def sse(*chunks: dict[str, Any]) -> bytes:
    lines = [f"data: {json.dumps(chunk)}\n\n" for chunk in chunks]
    return ("".join(lines) + "data: [DONE]\n\n").encode()


def client_for(handler) -> tuple[OpenAICompatibleClient, list[dict[str, Any]]]:
    bodies: list[dict[str, Any]] = []

    def record(request: httpx.Request) -> httpx.Response:
        bodies.append(json.loads(request.content))
        return handler(request)

    transport = httpx.MockTransport(record)
    client = OpenAICompatibleClient(
        base_url="https://models.test/v1",
        api_key="test-key",
        http_client=httpx.AsyncClient(transport=transport),
    )
    return client, bodies


REQUEST: dict[str, Any] = {
    "model": "chat-model",
    "max_tokens": 512,
    "system": [
        {"type": "text", "text": "static", "cache_control": {"type": "ephemeral"}},
        {"type": "text", "text": "context"},
    ],
    "tools": [
        {"name": "search", "description": "Search.", "input_schema": {"type": "object"}},
        {"type": "web_search_20250305", "name": "web_search"},
    ],
    "tool_choice": {"type": "tool", "name": "search"},
    "thinking": {"type": "disabled"},
    "messages": [
        {"role": "user", "content": "a tent"},
        {
            "role": "assistant",
            "content": [
                {"type": "thinking", "thinking": "...", "signature": "s"},
                {"type": "text", "text": "Looking."},
                {"type": "tool_use", "id": "tu-1", "name": "search", "input": {"q": "tent"}},
            ],
        },
        {
            "role": "user",
            "content": [
                {"type": "tool_result", "tool_use_id": "tu-1", "content": "none", "is_error": True},
                {"type": "text", "text": "try again"},
            ],
        },
    ],
}


def test_request_translation_keeps_calls_next_to_results_and_drops_what_does_not_carry():
    body = chat_request(REQUEST, max_tokens_field="max_completion_tokens")
    assert body["max_completion_tokens"] == 512
    assert "thinking" not in body
    assert [m["role"] for m in body["messages"]] == ["system", "user", "assistant", "tool", "user"]
    assert body["messages"][0]["content"] == "static\n\ncontext"
    assistant = body["messages"][2]
    assert assistant["content"] == "Looking."
    assert json.loads(assistant["tool_calls"][0]["function"]["arguments"]) == {"q": "tent"}
    assert body["messages"][3] == {"role": "tool", "tool_call_id": "tu-1", "content": "Error: none"}
    assert [t["function"]["name"] for t in body["tools"]] == ["search"]
    assert body["tool_choice"] == {"type": "function", "function": {"name": "search"}}


@pytest.mark.parametrize(
    ("choice", "expected"),
    [({"type": "auto"}, "auto"), ({"type": "none"}, "none"), ({"type": "any"}, "required")],
)
def test_tool_choice_maps(choice, expected):
    assert chat_request({**REQUEST, "tool_choice": choice})["tool_choice"] == expected


async def test_stream_yields_messages_api_events_and_the_final_message():
    chunks = [
        {"choices": [{"delta": {"content": "Two "}}]},
        {"choices": [{"delta": {"content": "picks."}}]},
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {
                                "index": 0,
                                "id": "call-1",
                                "function": {"name": "search", "arguments": '{"q":'},
                            }
                        ]
                    }
                }
            ]
        },
        {
            "choices": [
                {"delta": {"tool_calls": [{"index": 0, "function": {"arguments": '"tent"}'}}]}}
            ]
        },
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
        {
            "choices": [],
            "usage": {"prompt_tokens": 90, "completion_tokens": 12, "prompt_cache_hit_tokens": 30},
        },
    ]
    client, bodies = client_for(lambda _: httpx.Response(200, content=sse(*chunks)))
    streamed = StreamedRound()
    async with client.messages.stream(**REQUEST) as stream:
        kinds = []
        async for event in stream:
            streamed.feed(event)
            kinds.append(event.type)
        final = await stream.get_final_message()
    assert bodies[0]["stream"] is True
    assert kinds[0] == "message_start" and kinds[-2:] == ["message_delta", "message_stop"]
    assert final.stop_reason == "tool_use"
    assert [block.type for block in final.content] == ["text", "tool_use"]
    assert final.content[0].text == "Two picks."
    assert final.content[1].input == {"q": "tent"}
    assert (final.usage.input_tokens, final.usage.cache_read_input_tokens) == (60, 30)
    # The turn loop's own accumulator reads the same events.
    assert streamed.tools[1].parsed() == {"q": "tent"}
    assert streamed.usage.output_tokens == 12


async def test_tool_input_that_is_not_json_raises_value_error_while_the_tool_is_open():
    chunks = [
        {
            "choices": [
                {
                    "delta": {
                        "tool_calls": [
                            {"index": 0, "id": "c", "function": {"name": "s", "arguments": "{oops"}}
                        ]
                    }
                }
            ]
        },
        {"choices": [{"delta": {}, "finish_reason": "tool_calls"}]},
    ]
    client, _ = client_for(lambda _: httpx.Response(200, content=sse(*chunks)))
    streamed = StreamedRound()
    async with client.messages.stream(**REQUEST) as stream:
        with pytest.raises(ValueError):
            async for event in stream:
                streamed.feed(event)
    assert streamed.tool_open()


async def test_create_returns_a_message_with_tool_calls():
    reply = {
        "id": "x",
        "choices": [
            {
                "message": {
                    "content": None,
                    "tool_calls": [
                        {
                            "id": "c1",
                            "function": {"name": "record_fact", "arguments": '{"key":"k"}'},
                        }
                    ],
                },
                "finish_reason": "tool_calls",
            }
        ],
        "usage": {"prompt_tokens": 5, "completion_tokens": 2},
    }
    client, bodies = client_for(lambda _: httpx.Response(200, json=reply))
    message = await client.messages.create(**REQUEST)
    assert "stream" not in bodies[0]
    assert message.stop_reason == "tool_use"
    assert message.content[0].name == "record_fact" and message.content[0].input == {"key": "k"}


async def test_errors_map_to_auth_and_provider_failures():
    client, _ = client_for(lambda _: httpx.Response(401, json={"error": "bad key"}))
    with pytest.raises(ModelAuthenticationError) as auth:
        await client.messages.create(**REQUEST)
    assert auth.value.status == 401
    client, _ = client_for(lambda _: httpx.Response(404, json={"error": "no such model"}))
    with pytest.raises(ModelProviderError) as missing:
        async with client.messages.stream(**REQUEST):
            pass
    assert missing.value.status == 404


async def test_a_missing_key_fails_before_any_request():
    calls: list[httpx.Request] = []
    client = OpenAICompatibleClient(
        base_url="https://models.test/v1",
        api_key=None,
        http_client=httpx.AsyncClient(transport=httpx.MockTransport(lambda r: calls.append(r))),
    )
    with pytest.raises(ModelAuthenticationError) as missing:
        await client.messages.create(**REQUEST)
    assert missing.value.status is None and not calls
