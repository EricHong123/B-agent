"""Database scope, memory store and session store for the commerce agents.

Backends never hold a request's session: a streamed reply outlives the request, so every
read or write opens its own scope from a ``SessionScope`` factory the runtime carries.
"""

import secrets
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, ContextManager, Dict, Generic, Iterator, List, Optional, Type, TypeVar

from pydantic import BaseModel
from sqlalchemy import update
from sqlalchemy.orm import Session

from commerce_common.memory import match_facts
from commerce_common.types import MemoryCategory, MemoryFact

from app.db import SessionLocal
from app.models.database import CommerceMemoryFact, CommerceMemoryPurge, CommerceSession


SessionScope = Callable[[], ContextManager[Session]]
StateT = TypeVar("StateT", bound=BaseModel)


@contextmanager
def default_scope() -> Iterator[Session]:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class SqlMemoryStore:
    """``commerce_common.memory.MemoryStore`` over ``commerce_memory_facts``."""

    def __init__(self, scope: SessionScope) -> None:
        self._scope = scope

    async def get_facts(self, subject_id: str) -> List[MemoryFact]:
        with self._scope() as db:
            rows = (
                db.query(CommerceMemoryFact)
                .filter(CommerceMemoryFact.subject_id == subject_id)
                .order_by(CommerceMemoryFact.id)
                .all()
            )
            return [
                MemoryFact(
                    key=row.key,
                    value=row.value,
                    category=MemoryCategory(row.category),
                    updated_at=row.updated_at,
                    source_session_id=row.source_session_id,
                )
                for row in rows
            ]

    async def upsert_facts(self, subject_id: str, facts: List[MemoryFact]) -> None:
        with self._scope() as db:
            for fact in facts:
                row = (
                    db.query(CommerceMemoryFact)
                    .filter(
                        CommerceMemoryFact.subject_id == subject_id,
                        CommerceMemoryFact.key == fact.key,
                    )
                    .one_or_none()
                )
                if row is None:
                    row = CommerceMemoryFact(subject_id=subject_id, key=fact.key)
                    db.add(row)
                row.value = fact.value
                row.category = MemoryCategory(fact.category).value
                row.source_session_id = fact.source_session_id
                row.updated_at = (
                    fact.updated_at.astimezone(timezone.utc).replace(tzinfo=None)
                    if fact.updated_at and fact.updated_at.tzinfo
                    else fact.updated_at or utcnow()
                )
            db.commit()

    async def search_facts(self, subject_id: str, query: str) -> List[MemoryFact]:
        return match_facts(await self.get_facts(subject_id), query)

    async def delete_fact(self, subject_id: str, key: str) -> bool:
        with self._scope() as db:
            deleted = (
                db.query(CommerceMemoryFact)
                .filter(
                    CommerceMemoryFact.subject_id == subject_id,
                    CommerceMemoryFact.key == key,
                )
                .delete()
            )
            db.commit()
            return bool(deleted)

    async def clear(self, subject_id: str) -> None:
        with self._scope() as db:
            db.query(CommerceMemoryFact).filter(
                CommerceMemoryFact.subject_id == subject_id
            ).delete()
            purge = db.get(CommerceMemoryPurge, subject_id)
            if purge is None:
                db.add(CommerceMemoryPurge(subject_id=subject_id, generation=1))
            else:
                purge.generation += 1
            db.commit()

    async def purge_generation(self, subject_id: str) -> int:
        with self._scope() as db:
            purge = db.get(CommerceMemoryPurge, subject_id)
            return purge.generation if purge else 0


class UnknownSession(LookupError):
    pass


class SessionConflict(RuntimeError):
    pass


@dataclass
class SessionRecord(Generic[StateT]):
    """One assistant session as the turn loop reads it; ``version`` guards the write back."""

    session_id: str
    role: str
    subject_id: str
    state: StateT
    user_id: Optional[int] = None
    customer_id: Optional[int] = None
    invite_id: Any = None
    messages: List[Dict[str, Any]] = field(default_factory=list)
    pending_app_events: List[str] = field(default_factory=list)
    version: int = 1
    ended: bool = False


class SessionStore(Generic[StateT]):
    """Compare-and-set persistence of ``SessionRecord`` in ``commerce_sessions``."""

    def __init__(self, scope: SessionScope, role: str, state_type: Type[StateT]) -> None:
        self._scope = scope
        self._role = role
        self._state_type = state_type

    def start(
        self,
        *,
        subject_id: str,
        user_id: Optional[int] = None,
        customer_id: Optional[int] = None,
        invite_id: Any = None,
    ) -> SessionRecord[StateT]:
        record: SessionRecord[StateT] = SessionRecord(
            session_id=secrets.token_urlsafe(32),
            role=self._role,
            subject_id=subject_id,
            state=self._state_type(),
            user_id=user_id,
            customer_id=customer_id,
            invite_id=invite_id,
        )
        with self._scope() as db:
            db.add(
                CommerceSession(
                    id=record.session_id,
                    role=self._role,
                    subject_id=subject_id,
                    user_id=user_id,
                    customer_id=customer_id,
                    invite_id=invite_id,
                    state_json=record.state.model_dump(mode="json"),
                    pending_app_events_json=[],
                    messages_json=[],
                    version=1,
                )
            )
            db.commit()
        return record

    def require(self, session_id: str) -> SessionRecord[StateT]:
        with self._scope() as db:
            row = db.get(CommerceSession, session_id)
            if row is None or row.role != self._role:
                raise UnknownSession(session_id)
            db.refresh(row)
            return SessionRecord(
                session_id=row.id,
                role=row.role,
                subject_id=row.subject_id,
                state=self._state_type.model_validate(row.state_json or {}),
                user_id=row.user_id,
                customer_id=row.customer_id,
                invite_id=row.invite_id,
                messages=list(row.messages_json or []),
                pending_app_events=list(row.pending_app_events_json or []),
                version=row.version,
            )

    def save(self, record: SessionRecord[StateT], *, force: bool = False) -> None:
        if record.ended:
            return
        with self._scope() as db:
            query = update(CommerceSession).where(CommerceSession.id == record.session_id)
            if not force:
                query = query.where(CommerceSession.version == record.version)
            result = db.execute(
                query.values(
                    state_json=record.state.model_dump(mode="json"),
                    pending_app_events_json=list(record.pending_app_events),
                    messages_json=record.messages,
                    version=CommerceSession.version + 1,
                    updated_at=utcnow(),
                )
            )
            if result.rowcount != 1:
                db.rollback()
                raise SessionConflict(record.session_id)
            db.commit()
            row = db.get(CommerceSession, record.session_id)
            db.refresh(row)
            record.version = row.version

    def end(self, record: SessionRecord[StateT]) -> None:
        record.ended = True
        with self._scope() as db:
            db.query(CommerceSession).filter(CommerceSession.id == record.session_id).delete()
            db.commit()
