# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Data types both roles share. Role-specific types live in the role packages."""

from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import TypeVar
from zoneinfo import ZoneInfo

from pydantic import BaseModel, Field, field_validator

# Records a provenance map keeps: the newest; a dropped id needs a fresh read.
PROVENANCE_CAP = 200

RecordT = TypeVar("RecordT")


def remember(records: dict[str, RecordT], key: str, value: RecordT) -> None:
    records.pop(key, None)
    records[key] = value
    while len(records) > PROVENANCE_CAP:
        del records[next(iter(records))]


class MemoryCategory(StrEnum):
    PREFERENCE = "preference"
    CONSTRAINT = "constraint"
    CONTEXT = "context"


class MemoryFact(BaseModel):
    """One stored fact. The schema bounds the shape; ``validate_fact`` decides what a
    value may be about. Constraints are injected on every turn."""

    key: str = Field(max_length=64)
    value: str = Field(max_length=200)
    category: MemoryCategory = MemoryCategory.PREFERENCE
    updated_at: datetime | None = None
    # Recalled facts carry the session that wrote them, so the model reads them as a
    # past turn's claim and a poisoned session's writes stay traceable. The value is the
    # session's ``session_tag``, not the id: a fact is read back by other sessions of the
    # subject, and on the example hosts the id is also the request credential.
    source_session_id: str | None = Field(default=None, max_length=80)


class ClockContext(BaseModel):
    """The host-supplied clock a session context carries: an IANA ``timezone``, or an
    explicit ``now`` that overrides it. With neither set the prompt carries no local time,
    because the server's clock is not the user's. ``reply_language`` names the language
    the user picked in the host's UI ("Simplified Chinese"); the context block carries it
    and the prompt has the model write in it."""

    timezone: str | None = None
    now: datetime | None = None
    reply_language: str | None = Field(default=None, max_length=40)

    @field_validator("timezone")
    @classmethod
    def _known_zone(cls, value: str | None) -> str | None:
        if value is not None:
            try:
                ZoneInfo(value)
            except (KeyError, ValueError) as exc:
                raise ValueError(f"unknown IANA timezone: {value!r}") from exc
        return value

    def local_now(self) -> datetime | None:
        if self.now is not None:
            return self.now
        if self.timezone is not None:
            return datetime.now(ZoneInfo(self.timezone))
        return None
