"""The assistants' operations log in ``commerce_operation_events``: one record per turn,
vote, handoff ticket and approval-card action, in the record format of
``commerce/examples/demo_common/analytics.py`` so ``commerce/scripts/metrics_report.py``
computes the same metrics (``commerce/docs/metrics.md``) from B-agent's rows.

No tool result or memory value is stored, and the only message text is a handoff's copy
of the user's last request with identifier shapes masked.
"""

import importlib.util
import os
import re
import sys
import uuid
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Collection, Dict, Iterable, List, Literal, Optional, Tuple

from commerce_common.memory import DEFAULT_BLOCKED_PATTERNS
from commerce_common.streaming import AgentEvent
from commerce_common.turn import session_tag
from shopping_agent.gates import TERMS_GATE, WITHHELD

from app.commerce.stores import SessionScope, utcnow
from app.models.database import CommerceOperationEvent


SCHEMA_VERSION = 1
RequestedHandoffReason = Literal["user_requested", "after_negative_feedback", "after_error"]
_ID_KEYS = ("product_id", "listing_id", "change_id", "order_id", "campaign_id", "event_id")
_MAX_IDS = 20
_BRIEF_TURNS = 20
REQUEST_MAX_CHARS = 200
_IDENTIFIER = re.compile(
    "|".join(f"(?:{p})" for p in (r"(?:\d[ .()-]{0,2}){8,}\d", *DEFAULT_BLOCKED_PATTERNS[1:]))
)
METRICS_REPORT = (
    Path(os.environ.get("COMMERCE_ROOT") or Path(__file__).resolve().parents[3] / "commerce")
    / "scripts"
    / "metrics_report.py"
)


def _ids_in(value: Any, found: List[str]) -> None:
    if len(found) >= _MAX_IDS:
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if key in _ID_KEYS or key.endswith("_ids"):
                for one in item if isinstance(item, list) else [item]:
                    if isinstance(one, str) and one not in found and len(found) < _MAX_IDS:
                        found.append(one[:80])
            elif isinstance(item, (dict, list)):
                _ids_in(item, found)
    elif isinstance(value, list):
        for item in value:
            _ids_in(item, found)


def handoff_request(messages: List[Dict[str, Any]], host_texts: Collection[str] = ()) -> str:
    """The user's last typed request, identifier shapes masked, cut to 200 characters."""
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        blocks = [content] if isinstance(content, str) else content
        if not isinstance(blocks, list):
            continue
        texts = [
            block if isinstance(block, str) else str(block.get("text", ""))
            for block in blocks
            if isinstance(block, str) or (isinstance(block, dict) and block.get("type") == "text")
        ]
        typed = [text for text in texts if text not in host_texts and not text.startswith("[")]
        if not typed:
            continue
        text = " ".join(_IDENTIFIER.sub("[removed]", typed[-1]).split())
        if len(text) > REQUEST_MAX_CHARS:
            text = text[: REQUEST_MAX_CHARS - 1].rstrip() + "…"
        return text
    return ""


def _unique(items: Iterable[Any]) -> List[Any]:
    seen: List[Any] = []
    for item in items:
        if item not in seen:
            seen.append(item)
    return seen


class TurnRecorder:
    """Watches one turn's events and writes its record when the turn ends; ``observe``
    stamps ``turn_id`` on ``turn_complete`` so the client can vote on that turn."""

    def __init__(self, log: "OperationsLog", session_id: str, locale: Optional[str], *, model: Optional[str], provider: str) -> None:
        self.log = log
        self.session_id = session_id
        self.turn_id = f"t_{uuid.uuid4().hex[:16]}"
        self.record: Dict[str, Any] = {
            "kind": "turn",
            "turn_id": self.turn_id,
            "session": session_tag(session_id),
            "locale": locale,
            "provider": provider,
            "model": model[:120] if model else None,
            "tools": [],
            "evidence_ids": [],
            "evidence_versions": [],
            "blocked": [],
            "writes": [],
            "error": None,
            "fallback_reason": None,
        }
        self._tools: Dict[str, Dict[str, Any]] = {}
        self._withheld = self._no_match = False

    def observe(self, event: AgentEvent) -> AgentEvent:
        data = event.data
        if event.type == "tool_call":
            entry = {"name": data.get("tool"), "status": "started"}
            self._tools[str(data.get("id"))] = entry
            self.record["tools"].append(entry)
            _ids_in(data.get("input"), self.record["evidence_ids"])
        elif event.type == "tool_result":
            entry = self._tools.get(str(data.get("id")))
            status = data.get("status") or ("error" if data.get("is_error") else "ok")
            if entry is not None:
                entry["status"] = status
            versions = self.record["evidence_versions"]
            for item in data.get("evidence") or []:
                if isinstance(item, dict) and item.get("status") in WITHHELD:
                    self._withheld = True
                if len(versions) < _MAX_IDS and isinstance(item, dict):
                    versions.append(
                        {
                            "source_id": str(item.get("source_id"))[:80],
                            "version": str(item.get("version"))[:20],
                            "status": item.get("status"),
                        }
                    )
            if data.get("no_match") and data.get("tool") == "search_policies":
                self._no_match = True
            if status == "blocked":
                self.record["blocked"].append({"tool": data.get("tool"), "reason": data.get("reason")})
        elif event.type == "cart_update":
            self.record["writes"].append("cart")
        elif event.type == "change_update":
            change = data.get("change") or {}
            self.record["writes"].append(f"change:{change.get('status', 'staged')}")
        elif event.type == "turn_complete":
            self.record.update(
                stop_reason=data.get("stop_reason"),
                usage=data.get("usage"),
                elapsed_ms=data.get("elapsed_ms"),
            )
            return AgentEvent(type=event.type, data={**data, "turn_id": self.turn_id})
        return event

    def failed(self, kind: str) -> None:
        self.record["error"] = kind

    def fallback_reason(self) -> Optional[str]:
        if self._withheld:
            return "terms_withheld"
        if self._no_match:
            return "no_terms_match"
        for held in self.record["blocked"]:
            if held.get("reason") != TERMS_GATE:
                return f"gate_held:{held.get('reason')}"
        return None

    def write(self) -> None:
        self.record["fallback_reason"] = self.fallback_reason()
        self.log.write(self.record, session_id=self.session_id, turn_id=self.turn_id)


class OperationsLog:
    """One role's records. Writes never raise into the chat: a failed write costs the
    metrics, not the turn."""

    def __init__(self, scope: SessionScope, *, role: str) -> None:
        self._scope = scope
        self.role = role

    def turn(self, session_id: str, locale: Optional[str], *, model: Optional[str], provider: str) -> TurnRecorder:
        return TurnRecorder(self, session_id, locale, model=model, provider=provider)

    def write(
        self,
        record: Dict[str, Any],
        *,
        session_id: Optional[str],
        turn_id: Optional[str] = None,
        ticket: Optional[str] = None,
    ) -> None:
        document = {
            "v": SCHEMA_VERSION,
            "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "vertical": "b-agent",
            "role": self.role,
            **record,
        }
        try:
            with self._scope() as db:
                db.add(
                    CommerceOperationEvent(
                        role=self.role,
                        kind=str(record.get("kind")),
                        session_id=session_id,
                        turn_id=turn_id,
                        ticket=ticket,
                        record_json=document,
                    )
                )
                db.commit()
        except Exception:  # pragma: no cover - logged by SQLAlchemy; the chat goes on
            pass

    def _turns(self, session_id: str) -> List[Dict[str, Any]]:
        with self._scope() as db:
            rows = (
                db.query(CommerceOperationEvent)
                .filter(
                    CommerceOperationEvent.role == self.role,
                    CommerceOperationEvent.kind == "turn",
                    CommerceOperationEvent.session_id == session_id,
                )
                .order_by(CommerceOperationEvent.id.desc())
                .limit(_BRIEF_TURNS)
                .all()
            )
            return [row.record_json for row in reversed(rows)]

    def owns(self, turn_id: str, session_id: str) -> bool:
        with self._scope() as db:
            return (
                db.query(CommerceOperationEvent.id)
                .filter(
                    CommerceOperationEvent.role == self.role,
                    CommerceOperationEvent.kind == "turn",
                    CommerceOperationEvent.turn_id == turn_id,
                    CommerceOperationEvent.session_id == session_id,
                )
                .first()
                is not None
            )

    def brief(self, session_id: str, reason: str, request: str = "") -> Dict[str, Any]:
        turns = self._turns(session_id)
        statuses: Dict[str, Any] = {}
        for turn in turns:
            for tool in turn.get("tools", []):
                name = tool.get("name")
                if isinstance(name, str) and not name.startswith("present_"):
                    statuses[name] = tool.get("status")
        return {
            "request": request or None,
            "tried": {
                "tools": [{"name": name, "status": status} for name, status in statuses.items()],
                "held": _unique(held for turn in turns for held in turn.get("blocked", [])),
                "fallbacks": _unique(turn["fallback_reason"] for turn in turns if turn.get("fallback_reason")),
            },
            "evidence_versions": _unique(item for turn in turns for item in turn.get("evidence_versions", []))[:_MAX_IDS],
            "reason": reason,
        }

    def handoff_reason(self, session_id: str, turn_id: Optional[str], requested: RequestedHandoffReason) -> str:
        if turn_id and requested != "after_error":
            for turn in self._turns(session_id):
                if turn.get("turn_id") == turn_id and turn.get("fallback_reason"):
                    return "rule_triggered"
        return requested

    def feedback(self, session_id: str, turn_id: str, helpful: bool) -> None:
        self.write(
            {"kind": "feedback", "turn_id": turn_id, "session": session_tag(session_id), "helpful": helpful},
            session_id=session_id,
            turn_id=turn_id,
        )

    def handoff(self, session_id: str, turn_id: Optional[str], reason: str, request: str = "") -> Tuple[str, Dict[str, Any]]:
        ticket = f"H-{uuid.uuid4().hex[:6].upper()}"
        brief = self.brief(session_id, reason, request)
        self.write(
            {"kind": "handoff", "turn_id": turn_id, "session": session_tag(session_id), "ticket": ticket, **brief},
            session_id=session_id,
            turn_id=turn_id,
            ticket=ticket,
        )
        return ticket, brief

    def action(self, session_id: str, name: str, ids: Iterable[str] = ()) -> None:
        self.write(
            {"kind": "action", "session": session_tag(session_id), "name": name, "ids": list(ids)},
            session_id=session_id,
        )


def _metrics_module():
    name = "commerce_metrics_report"
    if name in sys.modules:
        return sys.modules[name]
    spec = importlib.util.spec_from_file_location(name, METRICS_REPORT)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def metrics_report(scope: SessionScope, *, days: int = 30) -> Dict[str, Any]:
    """Resolution, self-service and handoff metrics per role over the last ``days``, by
    the definitions in ``commerce/docs/metrics.md`` (``metrics_report.compute``)."""
    report = _metrics_module()
    since = utcnow() - timedelta(days=days)
    with scope() as db:
        rows = (
            db.query(CommerceOperationEvent)
            .filter(CommerceOperationEvent.created_at >= since)
            .order_by(CommerceOperationEvent.id)
            .all()
        )
        records = [row.record_json for row in rows]
    by_role: Dict[str, Dict[str, Any]] = {}
    for role in ("buyer", "merchant"):
        sessions: Dict[str, Any] = {}
        for record in records:
            if record.get("role") != role:
                continue
            session = sessions.setdefault(record.get("session") or "-", report.Session())
            bucket = {
                "turn": session.turns,
                "feedback": session.votes,
                "handoff": session.handoffs,
                "action": session.actions,
            }.get(record.get("kind"))
            if bucket is not None:
                bucket.append(record)
        by_role[role] = report.compute(sessions)
        by_role[role]["terms_gaps"] = report.terms_gaps(sessions)
    return {"definitions_version": report.DEFINITIONS_VERSION, "days": days, "roles": by_role}
