# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The ACME Tickets box-office router: the shared portal routes over
``MockTicketingMerchant``, the ``present_event_pacing`` extension, and the portal's
pacing read."""

from __future__ import annotations

from fastapi import APIRouter

from commerce_common.memory import MemoryStore
from demo_common import REPO_ROOT, MerchantIdentity, build_merchant_router, model_client
from merchant_agent_runtime import MerchantAgent

from .agent_config import build_merchant_config
from .event_pacing import build_event_pacing_extension
from .mock_merchant import MockTicketingMerchant
from .mock_ticketing import MockTicketing

IDENTITY = MerchantIdentity(merchant_id="acme-tickets", operator="Jo")


def create_merchant_router(storefront: MockTicketing, memory_store: MemoryStore) -> APIRouter:
    config = build_merchant_config(storefront.store_name)
    merchant = MockTicketingMerchant(storefront, config)
    agent = MerchantAgent(
        backend=merchant,
        skills_dir=REPO_ROOT / "merchant-agent" / "skills",
        config=config,
        client=model_client(),
        memory_store=memory_store,
        extra_presentation_tools=[build_event_pacing_extension(merchant)],
    )
    return build_merchant_router(
        storefront=storefront,
        backend=merchant,
        agent=agent,
        identity=IDENTITY,
        example_dir="entertainment",
        overview_extras=lambda: {"today": merchant.today_snapshot()},
        portal_reads={"/pacing": merchant.pacing_overview},
    )
