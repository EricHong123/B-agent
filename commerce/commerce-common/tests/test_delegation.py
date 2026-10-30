# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The delegate-extension contract and its tool definition."""

from __future__ import annotations

import dataclasses

import pytest
from pydantic import BaseModel

from commerce_common.delegation import DelegateExtension, DelegationContext


class _Result(BaseModel):
    answer: str


async def _run(context: DelegationContext, args: dict) -> _Result:
    del context, args
    return _Result(answer="ok")


def _extension() -> DelegateExtension:
    return DelegateExtension(
        name="crunch_numbers",
        description="Answer a bounded computational question.",
        input_schema={"type": "object", "properties": {"question": {"type": "string"}}},
        result_model=_Result,
        run=_run,
    )


def test_tool_definition_carries_the_model_facing_contract():
    definition = _extension().tool_definition()
    assert definition == {
        "name": "crunch_numbers",
        "description": "Answer a bounded computational question.",
        "input_schema": {"type": "object", "properties": {"question": {"type": "string"}}},
    }


def test_extension_is_frozen():
    with pytest.raises(dataclasses.FrozenInstanceError):
        _extension().name = "other"


def test_context_carries_the_four_session_handles_plus_status_and_usage():
    # Nothing here lets a delegate reach the executor, the delegate registry, or the event
    # stream; emit_status only carries a status line to the person watching, and usage is
    # the turn's token counters.
    fields = [field.name for field in dataclasses.fields(DelegationContext)]
    assert fields == ["backend", "config", "session", "state", "emit_status", "usage"]


def test_emit_status_defaults_to_none_and_rides_the_frozen_context():
    context = DelegationContext(backend=None, config=None, session=None, state=None)
    assert context.emit_status is None
    lines: list[str] = []
    with_channel = DelegationContext(
        backend=None, config=None, session=None, state=None, emit_status=lines.append
    )
    assert with_channel.emit_status is not None
    with_channel.emit_status("working")
    assert lines == ["working"]
    with pytest.raises(dataclasses.FrozenInstanceError):
        with_channel.emit_status = None


async def test_run_returns_the_result_model():
    extension = _extension()
    context = DelegationContext(backend=None, config=None, session=None, state=None)
    result = await extension.run(context, {"question": "2+2"})
    assert isinstance(result, extension.result_model)
