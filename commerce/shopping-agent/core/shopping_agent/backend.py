# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The StorefrontBackend interface: the one integration surface an adopter implements,
mapping each method onto their catalog, cart, profile, order, and policy services.
Everything these methods return reaches the model as fenced data (fencing.py).
``examples/retail/api/mock_retail.py`` is a complete in-memory implementation.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from .types import (
    Cart,
    CheckoutHandoff,
    Disclosure,
    FulfillmentOption,
    Order,
    Policy,
    Product,
    ProductDetails,
    SearchFilters,
    ShoppingSessionContext,
    UserPreferences,
)


class NotOffered(Exception):  # a signal the executor relays, not a failure
    """Raised by a backend method for something this store does not provide for the item
    or context in hand (delivery options that belong to another seller, say), as opposed
    to a system that is down or not wired yet. The executor tells the model the store does
    not offer it; a whole system the store lacks is switched off in the config instead."""


class Unavailable(Exception):  # relayed like NotOffered, with its own wording
    """Raised by ``add_to_cart`` for a product or variant that exists but cannot be bought
    right now (out of stock, not sold in this context). The message names ids only: what
    is unavailable and, for a variant, which sibling variants are in stock. The executor
    relays it and nothing is written."""


class StorefrontBackend(ABC):
    """Every method acts for the customer in ``session``, calling that system's own API
    server-side with the credential the host holds for the session; the model sees the
    method's result, never a token. The cart methods are the only writes; each arrives
    after the executor's provenance gate and quantity caps (gates.py) and returns the
    whole cart, and the backend still enforces its own business rules (eligibility,
    stock, limits) atomically, since the executor's lock covers one process's session
    only. No method places an order or moves money: ``checkout`` renders the cart for
    the host to complete. :class:`NotOffered` reaches the model as "not something this
    store offers"; any other exception as the tool being temporarily unavailable, logged
    by the executor.
    """

    # -- Catalog ------------------------------------------------------------------

    @abstractmethod
    async def search_products(
        self,
        session: ShoppingSessionContext,
        query: str,
        filters: SearchFilters | None = None,
        limit: int = 8,
    ) -> list[Product]:
        """The closest text matches, best first, at most ``limit`` (already clamped to the
        config's ceiling); an empty list when nothing matches. A family is one result
        (its variants are not results of their own), and ids resolve through
        :meth:`get_product_details`. Domain dimensions arrive in ``filters.attributes``
        (described to the model by ``ShoppingAgentConfig.domain_search_notes``); a backend
        whose prices hold only for the searched context states that context in the
        product's ``attributes``."""

    @abstractmethod
    async def get_product_details(
        self, session: ShoppingSessionContext, product_id: str
    ) -> ProductDetails | None:
        """The full record for one id as the model wrote it, or None when the id is
        unknown. A family's ``variants`` carries its purchasable records inside one fenced
        result (``docs/backends.md`` gives the size limit; each variant may override any
        field it inherits), and the record and its variants are what enter the session's
        provenance. A variant's id returns that variant."""

    # -- Cart ---------------------------------------------------------------------

    @abstractmethod
    async def get_cart(self, session: ShoppingSessionContext) -> Cart:
        """The session's cart, empty when nothing is in it. Read before a turn, by the
        cart gates, and by ``checkout``."""

    @abstractmethod
    async def add_to_cart(
        self, session: ShoppingSessionContext, product_id: str, quantity: int
    ) -> Cart:
        """Add ``quantity`` to the line for a product returned this session; the amount is
        already reduced so the line stays within ``max_quantity_per_item``. The id is a
        product without ``options`` or a variant, never a family record; the executor
        holds an add of a family and points the model at its variants. The line's
        ``option_values`` come from the variant."""

    @abstractmethod
    async def update_cart_item(
        self, session: ShoppingSessionContext, product_id: str, quantity: int
    ) -> Cart:
        """Set a line to ``quantity`` (1 to ``max_quantity_per_item``). A product the cart
        does not hold leaves the cart as it is."""

    @abstractmethod
    async def remove_from_cart(self, session: ShoppingSessionContext, product_id: str) -> Cart:
        """Remove a line. A product the cart does not hold leaves the cart as it is."""

    # -- Customer context ---------------------------------------------------------

    @abstractmethod
    async def get_preferences(self, session: ShoppingSessionContext) -> UserPreferences:
        """The customer's profile, a guest profile included. Read before every turn; no
        tool writes to it."""

    async def checkout_handoff(
        self, session: ShoppingSessionContext, cart: Cart
    ) -> list[CheckoutHandoff]:
        """Optional: where this cart is paid for when that is not a route in the host app,
        such as the platform's hosted checkout URL, or one URL per seller on a marketplace.
        The executor puts the result on the ``checkout`` card's payload after the model's
        call, so the URL is never a tool argument and never reaches the model. The default
        returns none and the host's card leads to its own checkout."""
        return []

    async def get_account_context(self, session: ShoppingSessionContext) -> dict[str, Any] | None:
        """Optional account facts (plan, contract dates, computed eligibility) for the
        dynamic context block, or None when the deployment has no account model. It is
        sent on every request, so keep it small; the default returns None."""
        return None

    # -- Orders and policies ------------------------------------------------------

    @abstractmethod
    async def get_orders(self, session: ShoppingSessionContext, limit: int = 5) -> list[Order]:
        """The customer's own orders, newest first, at most ``limit`` (already clamped).
        Their items enter provenance, so a reorder needs no search."""

    @abstractmethod
    async def get_order(self, session: ShoppingSessionContext, order_id: str) -> Order | None:
        """One of the customer's own orders, or None when the id is unknown or belongs to
        someone else. ``present_order_status`` reads it too."""

    @abstractmethod
    async def search_policies(self, session: ShoppingSessionContext, query: str) -> list[Policy]:
        """The help and policy passages matching ``query``; an empty list when none do."""

    # -- Disclosures (optional) ---------------------------------------------------

    async def get_disclosure(
        self, session: ShoppingSessionContext, product_id: str
    ) -> Disclosure | None:
        """Optional: the facts box ``present_disclosure`` renders for a product returned
        this session, authored here in full, or None when the product has none. The
        tool exists only under ``ShoppingAgentConfig.enable_disclosures``; the default
        returns None."""
        return None

    # -- Fulfillment --------------------------------------------------------------

    @abstractmethod
    async def get_fulfillment_options(
        self, session: ShoppingSessionContext, product_ids: list[str]
    ) -> list[FulfillmentOption]:
        """The delivery, pickup, and shipping options for up to twenty ids as the model
        wrote them; ids the catalog does not know are skipped."""
