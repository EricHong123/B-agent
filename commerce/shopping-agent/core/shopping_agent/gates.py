# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The cart gates and the terms gate. A cart write accepts only product ids that catalog
or order tools returned this session (or lines already in the cart), holds an add of a
product that still has options to choose and points at its variants, caps the resulting
line quantity at the config's limit, and reports any cap it applied; writes for one
session are serialized because a turn's tool calls run concurrently.

The terms gate reads every versioned passage a policy search returns against the session
clock: of a source's versions, the one in force passes, an older or a scheduled one is
dropped, and a source with no version in force (expired, not yet effective) or with two
in force at once is withheld, so the model is told it cannot state those terms.
"""

from __future__ import annotations

import asyncio
import weakref
from collections.abc import Sequence
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from commerce_common.streaming import AgentEvent, ToolOutcome

from .backend import StorefrontBackend
from .config import ShoppingAgentConfig
from .fencing import STOREFRONT_FENCE
from .serialization import cart_payload, cart_summary
from .types import (
    Cart,
    Order,
    Policy,
    Product,
    ShoppingSessionContext,
    ShoppingSessionState,
    TermsEvidence,
)

PROVENANCE_GATE = "provenance"
OPTIONS_GATE = "options"
TERMS_GATE = "terms_validity"

# What the terms gate made of a versioned passage: the version in force, an older or a
# newer one beside it, or one of a source with no version in force or with two.
CURRENT, SUPERSEDED, SCHEDULED = "current", "superseded", "scheduled"
EXPIRED, NOT_IN_FORCE, CONFLICT = "expired", "not_in_force", "conflict"
WITHHELD = frozenset({EXPIRED, NOT_IN_FORCE, CONFLICT})


def provenance_error(product_id: str) -> str:
    # get_product_details comes first in the hint: text search does not match ids, and
    # an empty search reads to the model as proof the product does not exist.
    return (
        f"product_id {product_id} was not returned by catalog or order tools in this "
        "session. Resolve it first: call get_product_details with this exact id (text "
        "search does not match product ids), or find it via search or order history, "
        "then add it using a product_id from those results."
    )


def check_provenance(state: ShoppingSessionState, product_id: str) -> ToolOutcome | None:
    """The held outcome when ``product_id`` has no session provenance, else None."""
    if product_id in state.seen_products:
        return None
    return ToolOutcome.held(PROVENANCE_GATE, provenance_error(product_id))


def options_error(product: Product) -> str:
    # Option names are catalog text arriving outside the fence: sanitized and kept
    # short. The values themselves are in the fenced record the model already holds.
    names = STOREFRONT_FENCE.sanitize_text(", ".join(product.options), max_chars=60)
    return (
        f"product_id {product.product_id} has options still to choose ({names}), so the "
        "cart takes one of its variants. Settle each option from what the customer said "
        "or the customer's profile, ask once with the values as chips when one is still "
        "open, then add the matching variant's product_id from the variants "
        "get_product_details returns for this id."
    )


def check_options(state: ShoppingSessionState, product_id: str) -> ToolOutcome | None:
    """The held outcome when the record for ``product_id`` is a family with options
    still to choose; its variants are what the cart takes."""
    product = state.seen_products.get(product_id)
    if product is None or not product.has_options:
        return None
    return ToolOutcome.held(OPTIONS_GATE, options_error(product))


def remember_order_items(state: ShoppingSessionState, orders: Sequence[Order]) -> None:
    """Items on the customer's own orders count as provenance, so a reorder needs no search."""
    state.remember_products(
        [
            Product(
                product_id=item.product_id,
                title=item.title,
                price=item.price,
                option_values=item.option_values,
                variant_of=item.variant_of,
            )
            for order in orders
            for item in order.items
        ]
    )


# The gates read the cart, compute, then write; a second mutation for the same session
# in the same gather must not interleave with that. Locks live only while held.
_cart_locks: weakref.WeakValueDictionary[str, asyncio.Lock] = weakref.WeakValueDictionary()


def _cart_lock(session: ShoppingSessionContext) -> asyncio.Lock:
    lock = _cart_locks.get(session.session_id)
    if lock is None:
        lock = _cart_locks[session.session_id] = asyncio.Lock()
    return lock


def _written(text: str, cart: Cart) -> ToolOutcome:
    return ToolOutcome(text, [AgentEvent.cart_update(cart_payload(cart))])


async def gated_add_to_cart(
    *,
    backend: StorefrontBackend,
    config: ShoppingAgentConfig,
    session: ShoppingSessionContext,
    state: ShoppingSessionState,
    product_id: str,
    quantity: int,
) -> ToolOutcome:
    if held := check_provenance(state, product_id) or check_options(state, product_id):
        return held
    requested = max(1, quantity)
    max_quantity = config.max_quantity_per_item
    async with _cart_lock(session):
        current = await backend.get_cart(session)
        existing = next((i for i in current.items if i.product_id == product_id), None)
        if existing is None and len(current.items) >= config.max_cart_lines:
            return ToolOutcome.error("The cart is full.")
        allowed = min(requested, max(0, max_quantity - (existing.quantity if existing else 0)))
        if allowed <= 0:
            return ToolOutcome.error(
                f"This item is already at the per-item limit of {max_quantity}."
            )
        cart = await backend.add_to_cart(session, product_id, allowed)
    # The confirmation names the id only: titles are catalog text and stay inside fences.
    capped = f" (capped at the per-item limit of {max_quantity})" if allowed < requested else ""
    return _written(
        f"Added {product_id} x{allowed}{capped}. Cart now has {cart_summary(cart)}.", cart
    )


async def gated_update_cart_item(
    *,
    backend: StorefrontBackend,
    config: ShoppingAgentConfig,
    session: ShoppingSessionContext,
    state: ShoppingSessionState,
    product_id: str,
    quantity: int,
) -> ToolOutcome:
    requested = max(1, quantity)
    applied = min(requested, config.max_quantity_per_item)
    async with _cart_lock(session):
        if held := await _check_provenance_or_cart(backend, session, state, product_id):
            return held
        cart = await backend.update_cart_item(session, product_id, applied)
    capped = (
        f" (capped at the per-item limit of {config.max_quantity_per_item})"
        if applied < requested
        else ""
    )
    return _written(f"Updated quantity{capped}. Cart now has {cart_summary(cart)}.", cart)


async def gated_remove_from_cart(
    *,
    backend: StorefrontBackend,
    session: ShoppingSessionContext,
    state: ShoppingSessionState,
    product_id: str,
) -> ToolOutcome:
    async with _cart_lock(session):
        if held := await _check_provenance_or_cart(backend, session, state, product_id):
            return held
        cart = await backend.remove_from_cart(session, product_id)
    return _written(f"Removed. Cart now has {cart_summary(cart)}.", cart)


async def _check_provenance_or_cart(
    backend: StorefrontBackend,
    session: ShoppingSessionContext,
    state: ShoppingSessionState,
    product_id: str,
) -> ToolOutcome | None:
    """Update and remove also accept a line already in the cart, which may predate the
    session; the cart is fetched only when provenance alone does not pass."""
    if check_provenance(state, product_id) is None:
        return None
    current = await backend.get_cart(session)
    if any(item.product_id == product_id for item in current.items):
        return None
    return ToolOutcome.held(PROVENANCE_GATE, provenance_error(product_id))


# -- the terms gate --------------------------------------------------------------------


def terms_clock(session: ShoppingSessionContext) -> datetime:
    """The moment terms are judged at: the session's clock (a naive one read as the
    server's local time), else the server's UTC now."""
    now = session.local_now()
    if now is None:
        return datetime.now(UTC)
    return now if now.tzinfo is not None else now.astimezone()


@dataclass
class TermsCheck:
    """``current``: the passages that pass, unversioned ones included, in the backend's
    order. ``verdicts``: every versioned passage with what the gate made of it."""

    current: list[Policy] = field(default_factory=list)
    verdicts: list[tuple[Policy, str]] = field(default_factory=list)

    @property
    def withheld(self) -> list[tuple[Policy, str]]:
        return [(policy, verdict) for policy, verdict in self.verdicts if verdict in WITHHELD]

    def evidence(self) -> list[dict[str, Any]]:
        """The trace entries: one ``{"source_id", "version", "effective_at", "status"}`` per
        versioned passage, ``effective_at`` as an ISO day."""
        return [
            {
                "source_id": policy.source_id,
                "version": policy.version,
                "effective_at": policy.effective_at.date().isoformat()
                if policy.effective_at
                else None,
                "status": verdict,
            }
            for policy, verdict in self.verdicts
        ]


def check_terms(policies: Sequence[Policy], now: datetime) -> TermsCheck:
    """Judge each versioned source's passages at ``now``; see the module docstring."""
    by_source: dict[str, list[TermsEvidence]] = {}
    for policy in policies:
        if (evidence := policy.evidence()) is not None:
            by_source.setdefault(evidence.source_id, []).append(evidence)
    in_force = {
        source: {e.policy_id for e in versions if e.in_force(now)}
        for source, versions in by_source.items()
    }
    check = TermsCheck()
    for policy in policies:
        evidence = policy.evidence()
        if evidence is None:
            check.current.append(policy)
            continue
        live = in_force[evidence.source_id]
        if len(live) == 1 and policy.policy_id in live:
            verdict = CURRENT
            check.current.append(policy)
        elif len(live) > 1 and policy.policy_id in live:
            verdict = CONFLICT
        elif evidence.expires_at is not None and evidence.expires_at <= now:
            verdict = SUPERSEDED if live else EXPIRED
        else:
            verdict = SCHEDULED if live else NOT_IN_FORCE
        check.verdicts.append((policy, verdict))
    return check


def _withheld_reason(policy: Policy, verdict: str, check: TermsCheck) -> str:
    if verdict == CONFLICT:
        versions = sorted(
            str(other.version)
            for other, v in check.verdicts
            if v == CONFLICT and other.source_id == policy.source_id
        )
        return f"versions {' and '.join(versions)} are both in force"
    if verdict == EXPIRED and policy.expires_at is not None:
        return f"version {policy.version} expired {policy.expires_at.date().isoformat()}"
    return f"version {policy.version} is not yet in force"


def terms_withheld_text(check: TermsCheck) -> str:
    """The runtime-authored note for withheld sources; ids and versions are backend text
    outside the fence, so each is sanitized and capped."""
    seen: dict[str, str] = {}
    for policy, verdict in check.withheld:
        source = STOREFRONT_FENCE.sanitize_text(str(policy.source_id), max_chars=60)
        seen.setdefault(
            source, STOREFRONT_FENCE.sanitize_text(_withheld_reason(policy, verdict, check), 80)
        )
    listed = "; ".join(f"{source} ({reason})" for source, reason in seen.items())
    return (
        f"Withheld by the terms check: {listed}. No single version of these sources is in "
        "force today, so their terms cannot be stated from this result, a saved memory, or "
        "your own knowledge. Tell the customer the current terms could not be confirmed and "
        "point them to the app's support flow for an answer from a person."
    )


def terms_refusal(evidence: Sequence[TermsEvidence], now: datetime) -> str | None:
    """Why a card citing ``evidence`` cannot show it at ``now``, or None when every
    version it cites is in force."""
    lapsed = [e for e in evidence if not e.in_force(now)]
    if not lapsed:
        return None
    named = ", ".join(
        STOREFRONT_FENCE.sanitize_text(f"{e.source_id} v{e.version}", max_chars=60) for e in lapsed
    )
    return (
        f"The terms this card cites are not in force today ({named}). Run search_policies "
        "again and state only what a current passage says."
    )
