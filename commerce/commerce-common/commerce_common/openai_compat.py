# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""A model client for OpenAI-compatible Chat Completions endpoints that the Messages API
runtimes take as ``client=`` in place of ``AsyncAnthropic``.

The runtimes call two things on a client: ``messages.create(**request)`` and
``messages.stream(**request)``, whose stream yields raw Messages API events and ends with
``get_final_message()``. :class:`OpenAICompatibleClient` translates each request to a
``/chat/completions`` body and each response back, so the turn loop, eager dispatch,
partial frames, memory extraction, and the analysis delegate run unchanged.

What does not carry over: cache breakpoints, thinking, and server tools are dropped from
the request (an endpoint caches by its own rules, if at all); the usage counters map
``prompt_tokens`` and the cached share the endpoint reports onto the four Messages API
counters. A tool call whose arguments are not JSON raises ``ValueError`` before its
``content_block_stop``, the way the SDK's accumulator rejects such input, so the turn loop
salvages the round as it does on the first-party API.
"""

from __future__ import annotations

import asyncio
import json
import logging
import uuid
from collections.abc import AsyncIterator
from typing import Any

import httpx
from anthropic.types import (
    InputJSONDelta,
    Message,
    MessageDeltaUsage,
    RawContentBlockDeltaEvent,
    RawContentBlockStartEvent,
    RawContentBlockStopEvent,
    RawMessageDeltaEvent,
    RawMessageStartEvent,
    RawMessageStopEvent,
    TextBlock,
    TextDelta,
    ToolUseBlock,
    Usage,
)
from anthropic.types.raw_message_delta_event import Delta

logger = logging.getLogger(__name__)

# Statuses retried before any event is read, with these waits between attempts.
_RETRY_STATUSES = frozenset({408, 409, 429, 500, 502, 503, 504})
_RETRY_WAITS_S = (0.5, 1.5)
_ERROR_BODY_CHARS = 500


class ModelProviderError(Exception):
    """The endpoint refused or failed a call. ``status`` is the HTTP status, if any."""

    def __init__(self, message: str, status: int | None = None) -> None:
        super().__init__(message)
        self.status = status


class ModelAuthenticationError(ModelProviderError):
    """No API key was configured, or the endpoint rejected the one sent (401 or 403)."""


# -- request translation -------------------------------------------------------------------


def _as_dict(block: Any) -> dict[str, Any]:
    if isinstance(block, dict):
        return block
    if hasattr(block, "model_dump"):
        return block.model_dump(exclude_none=True)
    return dict(vars(block))


def _text_of(content: Any) -> str:
    """A tool result's or system prompt's text, from a string or a list of blocks."""
    if isinstance(content, str):
        return content
    parts = [_as_dict(block) for block in content or []]
    return "\n\n".join(part["text"] for part in parts if part.get("type") == "text")


def chat_messages(system: Any, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Messages API ``system`` and ``messages`` as Chat Completions messages. An assistant
    message's ``tool_use`` blocks become ``tool_calls``; a user message's ``tool_result``
    blocks become ``tool`` messages ahead of its text, which keeps each result next to its
    call. Thinking, server-tool, and image blocks are dropped."""
    out: list[dict[str, Any]] = []
    if system_text := _text_of(system):
        out.append({"role": "system", "content": system_text})
    for message in messages:
        role, content = message["role"], message["content"]
        if isinstance(content, str):
            out.append({"role": role, "content": content})
            continue
        blocks = [_as_dict(block) for block in content]
        if role == "assistant":
            text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
            calls = [
                {
                    "id": b["id"],
                    "type": "function",
                    "function": {
                        "name": b["name"],
                        "arguments": json.dumps(b.get("input") or {}, ensure_ascii=False),
                    },
                }
                for b in blocks
                if b.get("type") == "tool_use"
            ]
            entry: dict[str, Any] = {
                "role": "assistant",
                "content": text or ("" if not calls else None),
            }
            if calls:
                entry["tool_calls"] = calls
            out.append(entry)
            continue
        texts: list[str] = []
        for block in blocks:
            kind = block.get("type")
            if kind == "tool_result":
                result = _text_of(block.get("content"))
                out.append(
                    {
                        "role": "tool",
                        "tool_call_id": block["tool_use_id"],
                        "content": f"Error: {result}" if block.get("is_error") else result,
                    }
                )
            elif kind == "text" and block.get("text"):
                texts.append(block["text"])
        if texts:
            out.append({"role": "user", "content": "\n\n".join(texts)})
    return out


def chat_tools(tools: list[dict[str, Any]] | None) -> list[dict[str, Any]]:
    """The client tools as functions; server tools (no ``input_schema``) are dropped."""
    return [
        {
            "type": "function",
            "function": {
                "name": tool["name"],
                "description": tool.get("description", ""),
                "parameters": tool["input_schema"],
            },
        }
        for tool in tools or []
        if "input_schema" in tool
    ]


def chat_tool_choice(choice: dict[str, Any] | None) -> Any:
    kind = (choice or {}).get("type", "auto")
    if kind == "tool":
        return {"type": "function", "function": {"name": choice["name"]}}  # type: ignore[index]
    return {"any": "required", "none": "none"}.get(kind, "auto")


def chat_request(
    request: dict[str, Any], *, max_tokens_field: str = "max_tokens", stream: bool = False
) -> dict[str, Any]:
    """A Messages API request as a Chat Completions body. ``max_tokens_field`` names the
    endpoint's output cap (``max_completion_tokens`` on endpoints that renamed it)."""
    body: dict[str, Any] = {
        "model": request["model"],
        "messages": chat_messages(request.get("system"), request["messages"]),
        max_tokens_field: request["max_tokens"],
    }
    if tools := chat_tools(request.get("tools")):
        body["tools"] = tools
        body["tool_choice"] = chat_tool_choice(request.get("tool_choice"))
    if "temperature" in request:
        body["temperature"] = request["temperature"]
    if stream:
        body["stream"] = True
        body["stream_options"] = {"include_usage": True}
    return body


# -- response translation ------------------------------------------------------------------


def _stop_reason(finish_reason: str | None, has_tool_calls: bool) -> str:
    if has_tool_calls or finish_reason in ("tool_calls", "function_call"):
        return "tool_use"
    return "max_tokens" if finish_reason == "length" else "end_turn"


def _usage_counts(usage: dict[str, Any] | None) -> dict[str, int]:
    """Chat Completions usage as the Messages API's four counters; the cached share comes
    from ``prompt_tokens_details.cached_tokens`` or ``prompt_cache_hit_tokens``."""
    usage = usage or {}
    prompt = int(usage.get("prompt_tokens") or 0)
    details = usage.get("prompt_tokens_details") or {}
    cached = int(details.get("cached_tokens") or usage.get("prompt_cache_hit_tokens") or 0)
    return {
        "input_tokens": max(prompt - cached, 0),
        "output_tokens": int(usage.get("completion_tokens") or 0),
        "cache_read_input_tokens": cached,
        "cache_creation_input_tokens": 0,
    }


def _parse_arguments(arguments: str) -> dict[str, Any] | None:
    try:
        parsed = json.loads(arguments) if arguments.strip() else {}
    except ValueError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _message(
    model: str, content: list[Any], stop_reason: str | None, counts: dict[str, int], message_id: str
) -> Message:
    return Message(
        id=message_id,
        type="message",
        role="assistant",
        model=model,
        content=content,
        stop_reason=stop_reason,  # type: ignore[arg-type]
        stop_sequence=None,
        usage=Usage(**counts),
    )


def message_from_completion(data: dict[str, Any], model: str) -> Message:
    """A non-streamed Chat Completions response as a Messages API ``Message``."""
    choice = (data.get("choices") or [{}])[0]
    reply = choice.get("message") or {}
    content: list[Any] = []
    if text := reply.get("content"):
        content.append(TextBlock(type="text", text=text))
    calls = reply.get("tool_calls") or []
    for call in calls:
        function = call.get("function") or {}
        content.append(
            ToolUseBlock(
                type="tool_use",
                id=call.get("id") or f"call_{uuid.uuid4().hex[:12]}",
                name=function.get("name", ""),
                input=_parse_arguments(function.get("arguments") or "") or {},
            )
        )
    return _message(
        data.get("model") or model,
        content,
        _stop_reason(choice.get("finish_reason"), bool(calls)),
        _usage_counts(data.get("usage")),
        data.get("id") or f"msg_{uuid.uuid4().hex}",
    )


class _OpenBlock:
    """One content block while it streams: text, or a tool call with its argument text."""

    def __init__(self, index: int, kind: str, call_index: int | None = None) -> None:
        self.index = index
        self.kind = kind
        self.call_index = call_index
        self.text = ""
        self.id = ""
        self.name = ""


class ChatStream:
    """One streamed call: an async context manager whose iteration yields raw Messages API
    events translated from the Chat Completions chunks, then ``get_final_message``."""

    def __init__(self, client: OpenAICompatibleClient, request: dict[str, Any]) -> None:
        self._client = client
        self._request = request
        self._model = request["model"]
        self._response: httpx.Response | None = None
        self._blocks: list[_OpenBlock] = []
        self._open: _OpenBlock | None = None
        self._finish: str | None = None
        self._counts = _usage_counts(None)
        self._id = f"msg_{uuid.uuid4().hex}"
        self._done = False

    async def __aenter__(self) -> ChatStream:
        body = chat_request(
            self._request, max_tokens_field=self._client.max_tokens_field, stream=True
        )
        self._response = await self._client.open_stream(body)
        return self

    async def __aexit__(self, *exc: Any) -> bool:
        if self._response is not None:
            await self._response.aclose()
        return False

    def __aiter__(self) -> AsyncIterator[Any]:
        return self._events()

    async def _events(self) -> AsyncIterator[Any]:
        assert self._response is not None, "iterate inside `async with`"
        yield RawMessageStartEvent(
            type="message_start", message=_message(self._model, [], None, self._counts, self._id)
        )
        async for line in self._response.aiter_lines():
            if not line.startswith("data:"):
                continue
            payload = line[5:].strip()
            if payload == "[DONE]":
                break
            chunk = json.loads(payload)
            if chunk.get("usage"):
                self._counts = _usage_counts(chunk["usage"])
            for choice in chunk.get("choices") or []:
                if choice.get("finish_reason"):
                    self._finish = choice["finish_reason"]
                delta = choice.get("delta") or {}
                if text := delta.get("content"):
                    for event in self._text(text):
                        yield event
                for position, call in enumerate(delta.get("tool_calls") or []):
                    for event in self._tool_delta(call, position):
                        yield event
        for event in self._close():
            yield event
        has_calls = any(block.kind == "tool_use" for block in self._blocks)
        yield RawMessageDeltaEvent(
            type="message_delta",
            delta=Delta(stop_reason=_stop_reason(self._finish, has_calls), stop_sequence=None),  # type: ignore[arg-type]
            usage=MessageDeltaUsage(**self._counts),
        )
        yield RawMessageStopEvent(type="message_stop")
        self._done = True

    def _start(self, kind: str, call_index: int | None = None) -> list[Any]:
        events = self._close()
        block = _OpenBlock(len(self._blocks), kind, call_index)
        self._blocks.append(block)
        self._open = block
        return events

    def _close(self) -> list[Any]:
        block, self._open = self._open, None
        if block is None:
            return []
        if block.kind == "tool_use" and _parse_arguments(block.text) is None:
            # The SDK's accumulator raises here too; the turn loop salvages the round.
            raise ValueError(f"tool input for {block.name} is not JSON")
        return [RawContentBlockStopEvent(type="content_block_stop", index=block.index)]

    def _text(self, text: str) -> list[Any]:
        events: list[Any] = []
        if self._open is None or self._open.kind != "text":
            events += self._start("text")
            events.append(
                RawContentBlockStartEvent(
                    type="content_block_start",
                    index=self._open.index,  # type: ignore[union-attr]
                    content_block=TextBlock(type="text", text=""),
                )
            )
        block = self._open
        assert block is not None
        block.text += text
        events.append(
            RawContentBlockDeltaEvent(
                type="content_block_delta",
                index=block.index,
                delta=TextDelta(type="text_delta", text=text),
            )
        )
        return events

    def _tool_delta(self, call: dict[str, Any], position: int) -> list[Any]:
        call_index = call.get("index", position)
        function = call.get("function") or {}
        events: list[Any] = []
        block = self._open
        if block is None or block.kind != "tool_use" or block.call_index != call_index:
            earlier = next((b for b in self._blocks if b.call_index == call_index), None)
            if earlier is not None:
                # Arguments for a call already closed: kept for the final message only.
                earlier.text += function.get("arguments") or ""
                return events
            events += self._start("tool_use", call_index)
            block = self._open
            assert block is not None
            block.id = call.get("id") or f"call_{uuid.uuid4().hex[:12]}"
            block.name = function.get("name") or ""
            events.append(
                RawContentBlockStartEvent(
                    type="content_block_start",
                    index=block.index,
                    content_block=ToolUseBlock(
                        type="tool_use", id=block.id, name=block.name, input={}
                    ),
                )
            )
        elif function.get("name") and not block.name:
            block.name = function["name"]
        if arguments := function.get("arguments"):
            block.text += arguments
            events.append(
                RawContentBlockDeltaEvent(
                    type="content_block_delta",
                    index=block.index,
                    delta=InputJSONDelta(type="input_json_delta", partial_json=arguments),
                )
            )
        return events

    async def get_final_message(self) -> Message:
        if not self._done:
            async for _ in self:
                pass
        content: list[Any] = []
        for block in self._blocks:
            if block.kind == "text":
                if block.text:
                    content.append(TextBlock(type="text", text=block.text))
            else:
                content.append(
                    ToolUseBlock(
                        type="tool_use",
                        id=block.id,
                        name=block.name,
                        input=_parse_arguments(block.text) or {},
                    )
                )
        has_calls = any(block.kind == "tool_use" for block in self._blocks)
        return _message(
            self._model, content, _stop_reason(self._finish, has_calls), self._counts, self._id
        )


class _Messages:
    def __init__(self, client: OpenAICompatibleClient) -> None:
        self._client = client

    async def create(self, **request: Any) -> Message:
        body = chat_request(request, max_tokens_field=self._client.max_tokens_field)
        response = await self._client.post(body)
        return message_from_completion(response.json(), request["model"])

    def stream(self, **request: Any) -> ChatStream:
        return ChatStream(self._client, request)


class OpenAICompatibleClient:
    """``messages.create`` and ``messages.stream`` over ``{base_url}/chat/completions``.
    ``api_key`` is sent as a bearer token; with ``key_required`` and no key, every call
    raises :class:`ModelAuthenticationError` without reaching the endpoint. 408, 409, 429,
    and 5xx responses are retried twice before the first event."""

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str | None,
        timeout: float = 120.0,
        max_tokens_field: str = "max_tokens",
        key_required: bool = True,
        provider_label: str = "the model provider",
        http_client: httpx.AsyncClient | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.max_tokens_field = max_tokens_field
        self.provider_label = provider_label
        self._api_key = api_key
        self._key_required = key_required
        self._http = http_client or httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=15.0))
        self.messages = _Messages(self)

    def _headers(self) -> dict[str, str]:
        if not self._api_key:
            if self._key_required:
                raise ModelAuthenticationError(
                    f"no API key is configured for {self.provider_label}"
                )
            return {}
        return {"Authorization": f"Bearer {self._api_key}"}

    async def _send(self, body: dict[str, Any], *, stream: bool) -> httpx.Response:
        headers = self._headers()
        url = f"{self.base_url}/chat/completions"
        for attempt in range(len(_RETRY_WAITS_S) + 1):
            request = self._http.build_request("POST", url, json=body, headers=headers)
            response = await self._http.send(request, stream=stream)
            if response.status_code < 400:
                return response
            text = (await response.aread()).decode(errors="replace")[:_ERROR_BODY_CHARS]
            await response.aclose()
            if response.status_code in _RETRY_STATUSES and attempt < len(_RETRY_WAITS_S):
                logger.warning(
                    "%s returned %d; retrying", self.provider_label, response.status_code
                )
                await asyncio.sleep(_RETRY_WAITS_S[attempt])
                continue
            message = f"{self.provider_label} returned {response.status_code}: {text}"
            if response.status_code in (401, 403):
                raise ModelAuthenticationError(message, response.status_code)
            raise ModelProviderError(message, response.status_code)
        raise AssertionError("unreachable")

    async def post(self, body: dict[str, Any]) -> httpx.Response:
        return await self._send(body, stream=False)

    async def open_stream(self, body: dict[str, Any]) -> httpx.Response:
        return await self._send(body, stream=True)
