# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The staged-change guardrails and the in-memory ``ChangeLedger`` the example backends
build on. Guardrails run when a change is staged and again before it is applied; at
apply a change must also be inside its time to live and still match the live records.
"""

from __future__ import annotations

import functools
import math
import re
from collections.abc import Callable, Mapping
from datetime import UTC, datetime, timedelta

from commerce_common.fencing import truncate_display

from .config import MerchantAgentConfig
from .types import ActorKind, ChangeItem, ChangeKind, ChangeStatus, StagedChange


class GuardrailViolation(ValueError):
    """The change breaks the guardrails; ``violations`` holds one message per rule."""

    def __init__(self, violations: list[str]):
        super().__init__("; ".join(violations))
        self.violations = violations


class ChangeNotApplicable(ValueError):
    """The change id is unknown or not in a state that allows the transition; backends
    also raise it for operations their systems lack. The executor relays the message."""


def check_guardrails(
    kind: ChangeKind, items: list[ChangeItem], config: MerchantAgentConfig
) -> list[str]:
    """Operator-readable messages for every guardrail the items break; empty when the
    change may proceed."""
    violations: list[str] = []
    if len(items) > config.max_items_per_change:
        violations.append(
            f"change touches {len(items)} items and the limit is "
            f"{config.max_items_per_change} per change; stage it as separate changes within "
            "the limit, each approved on its own"
        )
    protected = {name.casefold() for name in config.protected_fields}
    listing_blocked = {name.casefold() for name in config.listing_update_blocked_fields}
    price_bearing = {name.casefold() for name in config.price_bearing_fields}
    seen: set[tuple[str, str]] = set()
    for item in items:
        field = item.field.casefold()
        # The caps below are checked per item and the preview shows one line per item, so
        # a target repeated within a change would pass each cap once per repeat and apply
        # the sum.
        if (item.target, field) in seen:
            violations.append(
                f"'{item.field}' on {item.target} appears more than once in this change — "
                "stage one line per item"
            )
        seen.add((item.target, field))
        if field in protected:
            violations.append(
                f"field '{item.field}' on {item.target} is protected and cannot be "
                "changed by the assistant"
            )
        if kind is ChangeKind.LISTING_UPDATE and field in listing_blocked:
            violations.append(
                f"'{item.field}' cannot be changed through a listing update — stage it as "
                "a price update or inventory action so its own limits apply"
            )
        # A promotion's items are price moves whatever the field is called; they are
        # checked against the promotion cap, other price moves against the per-change cap.
        if field in price_bearing or kind is ChangeKind.PROMOTION:
            before = _as_price(item.before)
            after = _as_price(item.after)
            if after is None:
                violations.append(f"price for {item.target} must be a positive amount")
            elif before is None:
                violations.append(
                    f"price for {item.target} has no grounded current price — "
                    "the movement cap cannot be checked"
                )
            else:
                delta_pct = abs(after - before) / before * 100
                if kind is ChangeKind.PROMOTION:
                    if delta_pct > config.max_promotion_discount_pct:
                        violations.append(
                            f"promotion move of {delta_pct:.0f}% on {item.target} exceeds "
                            f"the {config.max_promotion_discount_pct:.0f}% promotion limit"
                        )
                elif delta_pct > config.max_price_delta_pct:
                    violations.append(
                        f"price move of {delta_pct:.0f}% on {item.target} exceeds the "
                        f"{config.max_price_delta_pct:.0f}% per-change limit"
                    )
        # Any inventory action that raises the level counts as a restock.
        if kind is ChangeKind.INVENTORY_ACTION:
            added = _as_quantity(item.after) - _as_quantity(item.before)
            if added > config.max_restock_quantity:
                violations.append(
                    f"restock of {added} units on {item.target} exceeds the "
                    f"{config.max_restock_quantity}-unit per-change limit"
                )
        claim = (
            blocked_claim(item.after, config.blocked_claim_patterns)
            if kind in _COPY_KINDS and isinstance(item.after, str)
            else None
        )
        if claim:
            violations.append(
                f"'{item.field}' on {item.target} claims '{claim}', which the store "
                "cannot stand behind; state what the record shows in checkable terms"
            )
        if kind is ChangeKind.CAMPAIGN and field == "budget":
            budget = _as_price(item.after)
            if budget is not None and budget > config.max_campaign_budget:
                violations.append(
                    f"campaign budget of {budget:.0f} exceeds the "
                    f"{config.max_campaign_budget:.0f} per-change limit"
                )
    return violations


# The kinds whose text items publish copy: a listing's content and a campaign's message.
_COPY_KINDS = frozenset({ChangeKind.LISTING_UPDATE, ChangeKind.CAMPAIGN})


@functools.cache
def _claim_pattern(patterns: tuple[str, ...]) -> re.Pattern[str] | None:
    return re.compile("|".join(f"(?:{p})" for p in patterns), re.IGNORECASE) if patterns else None


def blocked_claim(text: str, patterns: tuple[str, ...]) -> str | None:
    """The first phrase in ``text`` a blocked-claim pattern matches, or None."""
    pattern = _claim_pattern(patterns)
    match = pattern.search(text) if pattern else None
    return match.group(0)[:60] if match else None


def _as_price(value: object) -> float | None:
    try:
        price = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    return price if price > 0 else None


def expires_at(change: StagedChange, config: MerchantAgentConfig) -> datetime:
    """When ``change`` expires if it is still unapproved, under the current config."""
    return change.created_at + timedelta(minutes=config.staged_change_ttl_minutes)


def check_drift(change: StagedChange, live: Mapping[tuple[str, str], object]) -> list[str]:
    """Operator-readable messages for every item whose ``before`` no longer matches the
    live record; empty when the change still applies to what the operator previewed.
    ``live`` maps ``(target, field)`` to the current value, and an item it leaves out is
    not compared. An inventory quantity applies as the staged delta (the restock cap
    reads it the same way), so a level that moved since staging is not drift."""
    drifted: list[str] = []
    for item in change.items:
        if (item.target, item.field) not in live:
            continue
        if change.kind is ChangeKind.INVENTORY_ACTION and _is_quantity(item.before):
            continue
        current = live[(item.target, item.field)]
        if not _same_value(item.before, current):
            drifted.append(
                f"'{item.field}' on {item.target} was {_shown(item.before)} when staged "
                f"and is {_shown(current)} now"
            )
    return drifted


def _is_quantity(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _same_value(staged: object, current: object) -> bool:
    numbers = (int, float)
    if (
        isinstance(staged, numbers)
        and isinstance(current, numbers)
        and not isinstance(staged, bool)
        and not isinstance(current, bool)
    ):
        return math.isclose(staged, current, rel_tol=1e-9, abs_tol=1e-9)
    return staged == current


def _shown(value: object) -> str:
    return "unset" if value is None else truncate_display(str(value), 60)


def _as_quantity(value: object) -> int:
    try:
        return int(value)  # type: ignore[call-overload]
    except (TypeError, ValueError):
        return 0


class ChangeLedger:
    """In-memory staged-change lifecycle a MerchantBackend can build on. ``stage`` checks
    the guardrails and records the actor; ``apply`` and ``discard`` accept only changes
    that are currently staged; a change left staged past ``staged_change_ttl_minutes``
    turns expired the next time the ledger is read; applied, discarded, and expired
    changes stay in the ledger as the audit trail. ``clock`` supplies the current UTC
    time."""

    def __init__(
        self,
        config: MerchantAgentConfig,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ):
        self._config = config
        self._clock = clock
        self._changes: dict[str, StagedChange] = {}
        self._sequence = 0

    def stage(
        self,
        *,
        kind: ChangeKind,
        summary: str,
        items: list[ChangeItem],
        actor: str,
        actor_kind: ActorKind = ActorKind.OPERATOR,
        currency: str | None = None,
        margin_impact: float | None = None,
        margin_before_pct: float | None = None,
        margin_after_pct: float | None = None,
        guardrail_notes: list[str] | None = None,
    ) -> StagedChange:
        violations = check_guardrails(kind, items, self._config)
        if violations:
            raise GuardrailViolation(violations)
        self._sequence += 1
        change = StagedChange(
            change_id=f"chg-{self._sequence:04d}",
            kind=kind,
            status=ChangeStatus.STAGED,
            # The summary is display text for the preview card, so an overlong one is
            # trimmed rather than refused.
            summary=truncate_display(summary, 200),
            items=items,
            created_at=self._clock(),
            created_by=actor,
            created_by_kind=actor_kind,
            guardrail_notes=guardrail_notes or [],
            currency=currency,
            margin_impact=margin_impact,
            margin_before_pct=margin_before_pct,
            margin_after_pct=margin_after_pct,
        )
        self._changes[change.change_id] = change
        return change

    def get(self, change_id: str) -> StagedChange | None:
        self._expire_overdue()
        return self._changes.get(change_id)

    def pending(self) -> list[StagedChange]:
        self._expire_overdue()
        return [c for c in self._changes.values() if c.status is ChangeStatus.STAGED]

    def applied(self) -> list[StagedChange]:
        return [c for c in self._changes.values() if c.status is ChangeStatus.APPLIED]

    def resolved(self) -> list[StagedChange]:
        """Applied, discarded, and expired changes, for a portal's audit view."""
        self._expire_overdue()
        return [c for c in self._changes.values() if c.status is not ChangeStatus.STAGED]

    def apply(
        self,
        change_id: str,
        actor: str,
        live: Mapping[tuple[str, str], object] | None = None,
    ) -> StagedChange:
        """Mark a staged change applied. ``live`` holds the current values the backend
        read for the change's items (see :func:`check_drift`); a change whose values
        moved since staging is refused and stays staged."""
        change = self._require_staged(change_id, "apply")
        # Config may have tightened since the change was staged.
        violations = check_guardrails(change.kind, change.items, self._config)
        if violations:
            raise GuardrailViolation(violations)
        if live is not None and (drifted := check_drift(change, live)):
            raise ChangeNotApplicable(
                f"change {change_id} was not applied: {'; '.join(drifted)}. Discard it and "
                "stage it again from the current values"
            )
        updated = change.model_copy(
            update={
                "status": ChangeStatus.APPLIED,
                "applied_at": self._clock(),
                "applied_by": actor,
            }
        )
        self._changes[change_id] = updated
        return updated

    def discard(
        self, change_id: str, actor: str, actor_kind: ActorKind = ActorKind.OPERATOR
    ) -> StagedChange:
        change = self._require_staged(change_id, "discard")
        updated = change.model_copy(
            update={
                "status": ChangeStatus.DISCARDED,
                "discarded_at": self._clock(),
                "discarded_by": actor,
                "discarded_by_kind": actor_kind,
            }
        )
        self._changes[change_id] = updated
        return updated

    def _expire_overdue(self) -> None:
        # Expiry only ever moves a change out of the queue; it never applies one.
        now = self._clock()
        for change in self._changes.values():
            if change.status is ChangeStatus.STAGED and now >= expires_at(change, self._config):
                self._changes[change.change_id] = change.model_copy(
                    update={
                        "status": ChangeStatus.EXPIRED,
                        "expired_at": expires_at(change, self._config),
                    }
                )

    def _require_staged(self, change_id: str, action: str) -> StagedChange:
        self._expire_overdue()
        change = self._changes.get(change_id)
        if change is None:
            raise ChangeNotApplicable(f"no change with id {change_id!r} to {action}")
        if change.status is ChangeStatus.EXPIRED:
            raise ChangeNotApplicable(
                f"change {change_id} expired unapproved after "
                f"{self._config.staged_change_ttl_minutes} minutes and was not applied — "
                f"nothing to {action}; stage it again from the current values"
            )
        if change.status is not ChangeStatus.STAGED:
            raise ChangeNotApplicable(
                f"change {change_id} is {change.status.value}, not staged — nothing to {action}"
            )
        return change
