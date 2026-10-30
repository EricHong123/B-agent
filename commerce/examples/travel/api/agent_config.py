# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The ACME Travel deployment's two agent configs."""

from __future__ import annotations

from demo_common import host_approval_default, model_config_fields
from merchant_agent import MerchantAgentConfig
from shopping_agent import ShoppingAgentConfig

_MERCHANT_DEFAULTS = MerchantAgentConfig()

# Supplier vocabulary added to the metrics-grounding lexicon.
_METRICS_TERMS = (
    "occupancy",
    "pacing",
    "pace",
    "room nights",
    "nightly rate",
    "adr",
    "bookings",
    "cancellations",
)


def build_shopping_config() -> ShoppingAgentConfig:
    return ShoppingAgentConfig(
        **model_config_fields(),
        brand_name="ACME Travel",
        assistant_name="ACME Assistant",
        brand_voice="well-traveled, candid, and allergic to tourist traps",
        domain_search_notes=(
            "Stays and experiences are date-bound: when the traveler has named dates, "
            "pass the check-in date as an ISO filters.attributes['travel_date'] on "
            "every search — results and prices are quotes for those dates, not "
            "catalog constants."
        ),
    )


def build_merchant_config(store_name: str) -> MerchantAgentConfig:
    return MerchantAgentConfig(
        **model_config_fields(),
        brand_name=store_name,
        require_host_approval=host_approval_default(),
        approval_surface="the Approve button on the change preview card",
        metrics_intent_terms=_MERCHANT_DEFAULTS.metrics_intent_terms + _METRICS_TERMS,
        # Stays price under nightly_rate, so the price-delta caps follow that field and a
        # free-form listing update cannot change it.
        price_bearing_fields=_MERCHANT_DEFAULTS.price_bearing_fields + ("nightly_rate",),
        listing_update_blocked_fields=_MERCHANT_DEFAULTS.listing_update_blocked_fields
        + ("nightly_rate",),
    )
