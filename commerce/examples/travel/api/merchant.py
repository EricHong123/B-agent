# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The ACME Travel supplier router: the shared portal routes over ``MockTravelMerchant``,
the ``present_occupancy_calendar`` extension, and the portal's occupancy read."""

from __future__ import annotations

from fastapi import APIRouter

from commerce_common.memory import MemoryStore
from demo_common import REPO_ROOT, MerchantIdentity, build_merchant_router, model_client
from merchant_agent_runtime import MerchantAgent

from .agent_config import build_merchant_config
from .mock_merchant import MockTravelMerchant
from .mock_travel import MockTravel
from .occupancy import build_occupancy_extension

IDENTITY = MerchantIdentity(merchant_id="acme-travel", operator="Marta")


def create_merchant_router(storefront: MockTravel, memory_store: MemoryStore) -> APIRouter:
    config = build_merchant_config(storefront.store_name)
    merchant = MockTravelMerchant(storefront, config)
    agent = MerchantAgent(
        backend=merchant,
        skills_dir=REPO_ROOT / "merchant-agent" / "skills",
        config=config,
        client=model_client(),
        memory_store=memory_store,
        extra_presentation_tools=[build_occupancy_extension(merchant)],
    )
    return build_merchant_router(
        storefront=storefront,
        backend=merchant,
        agent=agent,
        identity=IDENTITY,
        example_dir="travel",
        overview_extras=lambda: {"today": merchant.today_snapshot()},
        portal_reads={"/occupancy": merchant.occupancy_overview},
    )
