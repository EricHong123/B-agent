# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

import logging

import pytest
from pydantic import BaseModel, ValidationError

from commerce_common.config import BaseAgentConfig
from commerce_common.execution import (
    BaseToolExecutor,
    InvalidArguments,
    clamp_limit,
    contracts_by_name,
    parse_argument,
)
from commerce_common.fencing import Fence
from commerce_common.memory import MemoryRuntime
from commerce_common.skills import SkillRegistry
from commerce_common.streaming import ToolOutcome

FENCE = Fence(label="test_data", notice="Data.")


class Quantity(BaseModel):
    count: int


class Executor(BaseToolExecutor):
    fence = FENCE
    components = {}
    displayed_text = "Displayed."
    unavailable_text = "{name} is down."
    memory_subject = "subject"

    def handlers(self):
        return {"count": self._count, "read": self._read}

    async def _count(self, tool_input):
        return ToolOutcome(str(parse_argument(Quantity, tool_input).count))

    async def _read(self, tool_input):
        return ToolOutcome(str(await self._backend.read()))


class Backend:
    async def read(self):
        return Quantity.model_validate({"count": "not a number"})


def executor() -> Executor:
    config = BaseAgentConfig(model="test-model")
    return Executor(
        backend=Backend(),
        config=config,
        skills=SkillRegistry([]),
        session=None,
        state=None,
        memory=MemoryRuntime.build(config, None, fence=FENCE, extraction_prompt="p"),
    )


async def test_execute_reports_bad_arguments_only_from_argument_parsing(caplog):
    assert (await executor().execute("count", {"count": 3})).result_text == "3"
    with caplog.at_level(logging.WARNING, logger="commerce_common.execution"):
        invalid = await executor().execute("count", {"count": "three"})
    assert invalid.is_error
    assert invalid.result_text.startswith("count arguments were invalid — count: ")
    assert invalid.result_text.endswith(" Adjust and call it again.")
    assert not [r for r in caplog.records if r.name == "commerce_common.execution"]
    backend_failure = await executor().execute("read", {})
    assert backend_failure.is_error and backend_failure.result_text == "read is down."


def test_invalid_arguments_is_a_value_error_raised_from_the_validation_error():
    with pytest.raises(ValueError) as raised:
        parse_argument(Quantity, {"count": "three"})
    assert isinstance(raised.value, InvalidArguments)
    assert isinstance(raised.value.invalid, ValidationError)


async def test_backend_failure_is_reported_as_unavailable_and_logged_with_the_exception(caplog):
    with caplog.at_level(logging.WARNING, logger="commerce_common.execution"):
        outcome = await executor().execute("read", {})
    assert outcome.is_error and outcome.result_text == "read is down."
    (record,) = [r for r in caplog.records if r.name == "commerce_common.execution"]
    assert record.levelno == logging.WARNING and "read" in record.getMessage()
    assert record.exc_info is not None and isinstance(record.exc_info[1], ValidationError)


async def test_domain_errors_are_answered_without_a_warning(caplog):
    class Refusing(Executor):
        def handlers(self):
            return {"refuse": self._refuse}

        async def _refuse(self, tool_input):
            raise KeyError("stock")

        def domain_error(self, error):
            return ToolOutcome.error("stock is out.") if isinstance(error, KeyError) else None

    config = BaseAgentConfig(model="test-model")
    refusing = Refusing(
        backend=Backend(),
        config=config,
        skills=SkillRegistry([]),
        session=None,
        state=None,
        memory=MemoryRuntime.build(config, None, fence=FENCE, extraction_prompt="p"),
    )
    with caplog.at_level(logging.WARNING, logger="commerce_common.execution"):
        outcome = await refusing.execute("refuse", {})
    assert outcome.result_text == "stock is out."
    assert not [r for r in caplog.records if r.name == "commerce_common.execution"]


def test_clamp_limit_uses_the_ceiling_floors_at_one_and_defaults_when_missing():
    assert clamp_limit(25, 8, 5) == 5
    assert clamp_limit(3, 8, 5) == 3
    assert clamp_limit(-3, 8, 8) == 1
    assert clamp_limit(0, 8, 8) == 8
    assert clamp_limit(None, 8, 8) == 8


def test_contracts_by_name_skips_server_tools():
    tools = [
        {"name": "search", "description": "d", "input_schema": {}},
        {"type": "web_search_20250305", "name": "web_search"},
    ]
    assert list(contracts_by_name(tools)) == ["search"]


def test_outcome_refused_covers_held_calls_and_errors():
    assert ToolOutcome.held("provenance", "x").refused
    assert ToolOutcome.error("x").refused
    assert not ToolOutcome("x").refused
    assert not ToolOutcome.held("provenance", "x").is_error
