# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The entertainment example's ``StorefrontBackend``: the ticketing engine mapped onto
the interface. A cart line is a timed hold, every catalog read carries the live remaining
count and the labels derived from it, resale listings carry a value score computed here,
and the disclosure is the fee itemization from the catalog."""

from __future__ import annotations

import re
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path
from typing import Any

from commerce_common.streaming import ToolOutcome
from demo_common.storefront_fixtures import (
    anchored_shift,
    cart_line,
    cited_evidence,
    example_data_dir,
    find_by_id,
    find_order,
    keyword_score,
    load_help_synonyms,
    load_json,
    load_orders,
    load_policies,
    load_users,
    matches_attribute_filters,
    newest_orders,
    orders_for,
    preferences_of,
    rank_products,
    search_help,
    summary_of,
    within_price_and_rating,
)
from shopping_agent import (
    Cart,
    Disclosure,
    DisclosureRow,
    FulfillmentOption,
    Order,
    Policy,
    Product,
    ProductDetails,
    SearchFilters,
    ShoppingSessionContext,
    StorefrontBackend,
    UserPreferences,
)
from shopping_agent.executor import ShoppingToolExecutor

from .ticketing import (
    HOLD_TTL_S,
    OFFER_CLAIM_WINDOW_S,
    Ticket,
    TicketingEngine,
    TicketingError,
)

DATA_DIR = example_data_dir(__file__)

# "Selling fast" applies at or below this many open tickets (or 2% of capacity).
_SELLING_FAST_FLOOR = 12
_MIN_QUANTITY = "min_quantity"
_SEARCH_WEIGHTS = {
    "title": 3.0,
    "brand": 2.5,
    "category": 2.0,
    "attributes": 1.5,
    "description": 1.0,
}
# Resale value score by listing price as a ratio of the box-office all-in price: the
# first rung the ratio does not exceed applies; above the last rung the score is 1.
_VALUE_LADDER = (
    (0.80, 10),
    (0.90, 9),
    (1.00, 8),
    (1.10, 6),
    (1.20, 5),
    (1.30, 4),
    (1.45, 3),
    (1.65, 2),
)

_SYNONYMS: dict[str, list[str]] = {
    "concert": ["tour", "show", "tickets"],
    "show": ["tour", "tickets"],
    "gig": ["tour", "show"],
    "band": ["tour", "indie", "pop"],
    "music": ["tour", "indie", "pop", "orchestral"],
    "comedy": ["doe", "taping"],
    "comedian": ["comedy", "doe"],
    "standup": ["comedy", "doe"],
    "symphony": ["philharmonic", "orchestral", "opener"],
    "orchestra": ["philharmonic", "orchestral"],
    "classical": ["philharmonic", "orchestral"],
    "outdoor": ["amphitheater", "terrace"],
    "seat": ["reserved", "bowl", "balcony", "orchestra"],
    "seats": ["reserved", "bowl", "balcony", "orchestra"],
    "standing": ["pit", "floor", "general"],
    "floor": ["pit", "general"],
    "cheap": ["terrace", "balcony"],
    "cheapest": ["terrace", "balcony"],
    "front": ["pit", "rail"],
    "resale": ["fan", "listing"],
    "soldout": ["waitlist"],
    "waitlist": ["sold"],
    "tonight": ["aug", "sep", "oct"],
    "weekend": ["fri", "sat"],
    "friday": ["fri"],
    "saturday": ["sat"],
}


def _min_quantity(filters: SearchFilters) -> int | None:
    raw = str(filters.attributes.get(_MIN_QUANTITY, "")).strip()
    try:
        return int(raw) if raw else None
    except ValueError:
        return None


def _date_text(day: date) -> str:
    """The date as the titles carry it: ``Fri Aug 14``."""
    return f"{day:%a %b} {day.day}"


def shift_event_dates(
    catalog: dict[str, Any], today: date
) -> tuple[timedelta, Callable[[str], str]]:
    """Move every event forward by the whole weeks from the catalog's ``dates_anchored_to``
    to ``today``, in place: ``attributes.event_date`` and the date text in the title. The
    pacing book and the orders that name these shows shift by the same amount, so the shows
    stay as many days out as they were written to be. Returns the shift and a function that
    redates any other text carrying the old date labels."""
    delta = anchored_shift(catalog, today)
    if not delta:
        return delta, lambda text: text
    replacements: dict[str, str] = {}
    for product in catalog["products"]:
        attributes = product.get("attributes") or {}
        if not (authored := attributes.get("event_date")):
            continue
        moved = date.fromisoformat(authored) + delta
        attributes["event_date"] = moved.isoformat()
        old_text, new_text = _date_text(date.fromisoformat(authored)), _date_text(moved)
        replacements[old_text] = new_text
        product["title"] = product["title"].replace(old_text, new_text)
    return delta, redater(replacements)


def redater(replacements: dict[str, str]) -> Callable[[str], str]:
    """One pass over the text, so a label is not moved twice when two shows fall a shift
    apart, and a label is not matched inside a longer one (``Sat Aug 1`` in ``Sat Aug 15``)."""
    labels = re.compile("(?:" + "|".join(map(re.escape, replacements)) + r")(?!\d)")
    return lambda text: labels.sub(lambda match: replacements[match.group(0)], text)


class TicketingToolExecutor(ShoppingToolExecutor):
    """The engine enforces hold limits, expiry, and inventory and raises
    ``TicketingError`` with a message written for the caller; relay it so the model says
    what stands in the way instead of reporting a system failure. Passed as
    ``executor_class`` to the agent, which the host's button routes reuse."""

    ticketing_rule_text = "Nothing changed: {detail}. Tell the fan and offer what fits the rule."

    def domain_error(self, error: Exception) -> ToolOutcome | None:
        if isinstance(error, TicketingError):
            return ToolOutcome.error(
                self.ticketing_rule_text.format(detail=self._sanitize(str(error), 200))
            )
        return super().domain_error(error)


class MockTicketing(StorefrontBackend):
    def __init__(
        self, data_dir: Path = DATA_DIR, now: Callable[[], datetime] | None = None
    ) -> None:
        catalog = load_json(data_dir, "catalog.json")
        today = (now() if now is not None else datetime.now(UTC)).date()
        self.calendar_shift, redate = shift_event_dates(catalog, today)
        self.store_name: str = catalog.get("store_name", "the box office")
        self.products: dict[str, ProductDetails] = {
            p["product_id"]: ProductDetails.model_validate(p) for p in catalog["products"]
        }
        self._users = load_users(data_dir)
        self._orders = load_orders(data_dir)
        for _user_id, order in self._orders:
            for item in order.items:
                item.title = redate(item.title)
        self._policies = load_policies(data_dir)
        self._help_synonyms = load_help_synonyms(data_dir)
        inventory = {
            row["product_id"]: row for row in load_json(data_dir, "inventory.json")["inventory"]
        }
        tickets = [Ticket(**t) for t in load_json(data_dir, "tickets.json")["tickets"]]
        self.venues: dict[str, dict[str, Any]] = {
            v["venue_id"]: v for v in load_json(data_dir, "venues.json")["venues"]
        }
        # Fixture-authored simulated fans already queued on sold-out tiers, so a demo
        # join lands at a real position that then advances.
        waitlist_seed = {
            pid: int(row["waitlist_sim"])
            for pid, row in inventory.items()
            if int(row.get("waitlist_sim", 0)) > 0
        }
        self.engine = TicketingEngine(
            inventory=inventory,
            tickets=tickets,
            event_of=self._event_of,
            sold_together_of=self._sold_together_of,
            waitlist_seed=waitlist_seed,
            **({"now": now} if now is not None else {}),
        )

    def _event_of(self, product_id: str) -> str:
        product = self.products.get(product_id)
        return product.attributes.get("event_id", product_id) if product else product_id

    def _sold_together_of(self, product_id: str) -> int:
        """Catalog-authored sale unit ("pair, sold together" resale listings); default 1."""
        product = self.products.get(product_id)
        if product is None:
            return 1
        try:
            return max(1, int(product.attributes.get("sold_together", "1")))
        except (TypeError, ValueError):
            return 1

    # ------------------------------------------------------------------
    # Live state
    # ------------------------------------------------------------------

    def _value_score(self, listing: ProductDetails) -> tuple[int, str, str] | None:
        """A resale listing's (score, verdict, delta versus the box office), from its
        price against the box-office all-in price and whether that tier is sold out."""
        primary_id = listing.attributes.get("resale_of")
        primary = self.products.get(primary_id) if primary_id else None
        if primary is None or primary.price <= 0:
            return None
        ratio = listing.price / primary.price
        score = next((points for ceiling, points in _VALUE_LADDER if ratio <= ceiling), 1)
        if self.engine.remaining(primary_id) == 0:
            score = min(
                10, score + 1
            )  # the same premium is worth more against a sold-out box office
        verdict = "green" if score >= 8 else "amber" if score >= 5 else "red"
        delta = round((ratio - 1) * 100)
        vs_face = f"{delta:+d}%"
        return score, verdict, vs_face

    def _with_live_state(self, product: ProductDetails) -> ProductDetails:
        """The record with the live remaining count, the labels derived from it, in_stock,
        and a resale listing's value score."""
        remaining = self.engine.remaining(product.product_id)
        capacity = self.engine.capacity(product.product_id)
        attributes = dict(product.attributes)
        attributes["tickets_remaining"] = str(remaining)
        labels = [
            label for label in product.labels if not label.startswith(("Selling fast", "Sold out"))
        ]
        if remaining == 0:
            labels.insert(0, "Sold out, waitlist open")
        elif remaining <= max(_SELLING_FAST_FLOOR, capacity // 50):
            labels.insert(0, f"Selling fast, {remaining} left")
        if product.category == "resale":
            scored = self._value_score(product)
            if scored is not None:
                score, verdict, vs_face = scored
                primary = self.products[product.attributes["resale_of"]]
                attributes["value_score"] = str(score)
                attributes["value_verdict"] = verdict
                attributes["vs_box_office"] = vs_face
                attributes["box_office_all_in_usd"] = f"{primary.price:.2f}"
        return product.model_copy(
            update={
                "attributes": attributes,
                "labels": labels,
                "in_stock": remaining > 0,
            }
        )

    # ------------------------------------------------------------------
    # Catalog
    # ------------------------------------------------------------------

    def _searchable_text(self, product: ProductDetails) -> dict[str, str]:
        return {
            "title": product.title,
            "brand": product.brand or "",
            "category": product.category or "",
            "attributes": " ".join(f"{k} {v}" for k, v in product.attributes.items()),
            "description": f"{product.short_description or ''} {product.long_description or ''}",
        }

    def _score(self, product: ProductDetails, query_tokens: list[str]) -> float:
        return keyword_score(
            self._searchable_text(product), _SEARCH_WEIGHTS, query_tokens, _SYNONYMS
        )

    def _hard_filter(self, product: ProductDetails, filters: SearchFilters) -> bool:
        # A stated seat count is checked against live inventory, never relaxed.
        if not within_price_and_rating(product, filters):
            return False
        need = _min_quantity(filters)
        return need is None or self.engine.remaining(product.product_id) >= need

    @staticmethod
    def _soft_filter(product: ProductDetails, filters: SearchFilters) -> bool:
        return matches_attribute_filters(product, filters, ignore=frozenset({_MIN_QUANTITY}))

    async def search_products(
        self,
        session: ShoppingSessionContext,
        query: str,
        filters: SearchFilters | None = None,
        limit: int = 8,
    ) -> list[Product]:
        del session
        ranked = rank_products(
            self.products.values(),
            query,
            filters,
            limit,
            score=self._score,
            hard_filter=self._hard_filter,
            soft_filter=self._soft_filter,
            relevance_tiebreak=lambda product: product.price,
        )
        return [summary_of(self._with_live_state(product)) for product in ranked]

    def get_live_product(self, product_id: str) -> ProductDetails | None:
        resolved = find_by_id(self.products, product_id)
        return self._with_live_state(self.products[resolved]) if resolved else None

    product = get_live_product

    async def get_product_details(
        self, session: ShoppingSessionContext, product_id: str
    ) -> ProductDetails | None:
        del session
        return self.get_live_product(product_id)

    # ------------------------------------------------------------------
    # Cart: a view of the session's live holds
    # ------------------------------------------------------------------

    async def get_cart(self, session: ShoppingSessionContext) -> Cart:
        holds = self.engine.holds_for_session(session.session_id)
        return Cart(
            items=[
                cart_line(product, hold.quantity)
                for hold in holds
                if (product := self.products.get(hold.product_id)) is not None
            ]
        )

    async def add_to_cart(
        self, session: ShoppingSessionContext, product_id: str, quantity: int
    ) -> Cart:
        self.engine.create_hold(session.session_id, session.user_id, product_id, quantity)
        return await self.get_cart(session)

    async def update_cart_item(
        self, session: ShoppingSessionContext, product_id: str, quantity: int
    ) -> Cart:
        self.engine.set_hold_quantity(session.session_id, product_id, quantity)
        return await self.get_cart(session)

    async def remove_from_cart(self, session: ShoppingSessionContext, product_id: str) -> Cart:
        self.engine.release_hold(session.session_id, product_id)
        return await self.get_cart(session)

    def reset_session(self, session_id: str) -> None:
        self.engine.release_session(session_id)

    # ------------------------------------------------------------------
    # Fan, wallet, disclosures, orders, help content, fulfillment
    # ------------------------------------------------------------------

    async def get_preferences(self, session: ShoppingSessionContext) -> UserPreferences:
        return preferences_of(self._users, session.user_id)

    async def get_account_context(self, session: ShoppingSessionContext) -> dict[str, Any] | None:
        """The fan's wallet, holds, waitlist positions, open offers, and pending
        transfers, with countdowns from the engine's clock."""
        engine = self.engine
        tickets = engine.tickets_for(session.user_id)
        if not tickets and session.user_id not in self._users:
            return None
        upcoming = [
            {
                "ticket_id": t.ticket_id,
                "event": self.products[t.product_id].attributes.get("event_name", t.product_id),
                "date": self.products[t.product_id].attributes.get("event_date"),
                "tier": self.products[t.product_id].attributes.get("tier"),
                "seat": t.seat,
                "status": t.status,
            }
            for t in tickets
            if t.product_id in self.products
        ]
        holds = [
            {
                "hold_id": h.hold_id,
                "product_id": h.product_id,
                "quantity": h.quantity,
                "seconds_remaining": engine.seconds_until(h.expires_at),
            }
            for h in engine.holds_for_user(session.user_id)
        ]
        waitlist = [
            {"product_id": entry.product_id, "quantity": entry.quantity, "position": position}
            for entry, position in engine.waitlist_entries_for(session.user_id)
        ]
        offers = [
            {
                "offer_id": o.offer_id,
                "product_id": o.product_id,
                "quantity": o.quantity,
                "claim_window_seconds_remaining": engine.seconds_until(o.expires_at),
            }
            for o in engine.offers_for(session.user_id)
        ]
        transfers = [
            {
                "transfer_id": t.transfer_id,
                "ticket_ids": t.ticket_ids,
                "recipient": t.recipient,
                "status": t.status,
            }
            for t in engine.transfers_for(session.user_id)
            if t.status == "pending"
        ]
        return {
            "wallet": {"upcoming_tickets": upcoming},
            "active_holds": holds,
            "hold_policy": {"hold_minutes": HOLD_TTL_S // 60, "never_charged_until_checkout": True},
            "waitlist_entries": waitlist,
            "open_return_offers": offers,
            "offer_claim_window_minutes": OFFER_CLAIM_WINDOW_S // 60,
            "pending_transfers": transfers,
        }

    async def get_disclosure(
        self, session: ShoppingSessionContext, product_id: str
    ) -> Disclosure | None:
        """The all-in price itemized from the catalog's fee attributes (check.py verifies
        they sum to the price), plus live availability."""
        product = self.products.get(product_id)
        if product is None or product.category not in {"tickets", "resale"}:
            return None
        attrs = product.attributes

        rows: list[DisclosureRow] = [
            DisclosureRow(
                label="All-in price",
                value=f"${product.price:.2f}",
                note="per ticket; what you actually pay, no fees added later",
            ),
        ]
        # Box-office tickets itemize from the face value, resale from the seller's ask.
        if "face_price_usd" in attrs:
            rows.append(
                DisclosureRow(label="Face value", value=f"${float(attrs['face_price_usd']):.2f}")
            )
        elif "seller_price_usd" in attrs:
            rows.append(
                DisclosureRow(
                    label="Seller price",
                    value=f"${float(attrs['seller_price_usd']):.2f}",
                    note="the fan seller's asking price for this listing",
                )
            )
        if "service_fee_usd" in attrs:
            rows += [
                DisclosureRow(label="Service fee", value=f"${float(attrs['service_fee_usd']):.2f}"),
                DisclosureRow(
                    label="Facility fee", value=f"${float(attrs['facility_fee_usd']):.2f}"
                ),
                DisclosureRow(
                    label="Order processing",
                    value=f"${float(attrs['processing_fee_usd']):.2f}",
                    note="per ticket in this demo catalog",
                ),
            ]
        if product.category == "resale":
            scored = self._value_score(product)
            primary = self.products.get(attrs.get("resale_of", ""))
            if primary is not None:
                rows.append(
                    DisclosureRow(
                        label="Box-office all-in price",
                        value=f"${primary.price:.2f}",
                        note="same tier, sold by the venue"
                        + (
                            ", currently sold out"
                            if self.engine.remaining(primary.product_id) == 0
                            else ""
                        ),
                    )
                )
            if scored is not None:
                score, verdict, vs_face = scored
                rows.append(
                    DisclosureRow(
                        label="Value score",
                        value=f"{score}/10 ({verdict})",
                        note=f"listing is {vs_face} vs the box-office all-in price",
                    )
                )
        rows += [
            DisclosureRow(
                label="Hold policy",
                value=f"{HOLD_TTL_S // 60}-minute hold, then tickets return to sale",
                note="nothing is charged until you complete purchase",
            ),
            DisclosureRow(label="Delivery", value="mobile ticket, rotating barcode"),
        ]

        sources = [
            "all-in-pricing",
            "ticket-holds",
            "resale-value-scores" if product.category == "resale" else "mobile-entry",
            "refunds-event-changes",
        ]
        return Disclosure(
            title=f"{product.title}: price and terms",
            product_id=product.product_id,
            rows=rows,
            sources=sources,
            evidence=cited_evidence(self._policies, session, sources),
            footnotes=[
                "All prices are all-in: face value plus every fee, itemized above.",
                "Availability counts are live inventory numbers, never marketing copy.",
            ],
        )

    async def get_orders(self, session: ShoppingSessionContext, limit: int = 5) -> list[Order]:
        return orders_for(self._orders, session.user_id, limit)

    async def get_order(self, session: ShoppingSessionContext, order_id: str) -> Order | None:
        return find_order(self._orders, session.user_id, order_id)

    def recent_orders(self, limit: int = 6) -> list[Order]:
        return newest_orders(self._orders, limit)

    async def search_policies(self, session: ShoppingSessionContext, query: str) -> list[Policy]:
        del session
        return search_help(self._policies, query, synonyms=self._help_synonyms)

    async def get_fulfillment_options(
        self, session: ShoppingSessionContext, product_ids: list[str]
    ) -> list[FulfillmentOption]:
        del session, product_ids
        return [
            FulfillmentOption(
                method="delivery",
                eta="instant; mobile tickets land in your ACME Tickets wallet at purchase",
                fee=0.0,
            ),
            FulfillmentOption(
                method="pickup",
                eta="will-call at the venue box office from 2 hours before doors (photo ID)",
                fee=0.0,
                location="venue box office",
            ),
        ]
