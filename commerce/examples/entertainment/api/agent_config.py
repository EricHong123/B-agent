# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The ACME Tickets deployment's two agent configs."""

from __future__ import annotations

from demo_common import host_approval_default, model_config_fields
from merchant_agent import MerchantAgentConfig
from shopping_agent import ShoppingAgentConfig

_SHOPPING_DEFAULTS = ShoppingAgentConfig()
_MERCHANT_DEFAULTS = MerchantAgentConfig()

# Ticketing vocabulary added to the policy-grounding lexicon.
_POLICY_TERMS = (
    "service fee",
    "facility fee",
    "processing fee",
    "all-in",
    "face value",
    "hold",
    "holds",
    "hold timer",
    "waitlist",
    "return offer",
    "claim window",
    "transfer",
    "transfers",
    "resale",
    "value score",
    "sold out",
    "rescheduled",
    "postponed",
    "barcode",
    "will-call",
    "accessible seating",
)

# Promoter vocabulary added to the metrics-grounding lexicon.
_METRICS_TERMS = (
    "sell-through",
    "sell through",
    "sellthrough",
    "pacing",
    "pace",
    "on-sale",
    "on sale",
    "gross",
    "tickets sold",
    "ticket sales",
    "waitlist",
    "holds",
    "allocation",
    "tier",
)

# The itemized fee lines and the face value: the fee breakdown is a disclosure, and face
# value moves only through the price-update path that keeps the itemization summing to
# the sticker price.
_PROTECTED_FIELDS = (
    "service_fee_usd",
    "facility_fee_usd",
    "processing_fee_usd",
    "face_price_usd",
)


def build_shopping_config() -> ShoppingAgentConfig:
    return ShoppingAgentConfig(
        **model_config_fields(),
        brand_name="ACME Tickets",
        assistant_name="ACME Assistant",
        brand_voice=(
            "knows the room: upfront about fees and about what is left, and never in a hurry "
            "to sell"
        ),
        enable_disclosures=True,
        # Matches the engine's per-event hold cap.
        max_quantity_per_item=8,
        policy_intent_terms=_SHOPPING_DEFAULTS.policy_intent_terms + _POLICY_TERMS,
    )


def build_merchant_config(store_name: str) -> MerchantAgentConfig:
    return MerchantAgentConfig(
        **model_config_fields(),
        brand_name=store_name,
        require_host_approval=host_approval_default(),
        approval_surface="the Approve button on the change preview card",
        metrics_intent_terms=_MERCHANT_DEFAULTS.metrics_intent_terms + _METRICS_TERMS,
        protected_fields=_MERCHANT_DEFAULTS.protected_fields + _PROTECTED_FIELDS,
    )
