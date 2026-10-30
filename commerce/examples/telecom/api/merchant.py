# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The ACME Mobile commercial-ops router: the shared portal routes over
``MockTelecomMerchant``, the ``present_plan_mix`` extension, and the portal's
subscriber-base read."""

from __future__ import annotations

from fastapi import APIRouter

from commerce_common.memory import MemoryStore
from demo_common import REPO_ROOT, MerchantIdentity, build_merchant_router, model_client
from merchant_agent_runtime import MerchantAgent

from .agent_config import build_merchant_config
from .mock_merchant import MockTelecomMerchant
from .mock_telecom import MockTelecom
from .plan_mix import build_plan_mix_extension

IDENTITY = MerchantIdentity(merchant_id="acme-mobile", operator="Sam")


def create_merchant_router(storefront: MockTelecom, memory_store: MemoryStore) -> APIRouter:
    config = build_merchant_config(storefront.store_name)
    merchant = MockTelecomMerchant(storefront, config)
    agent = MerchantAgent(
        backend=merchant,
        skills_dir=REPO_ROOT / "merchant-agent" / "skills",
        config=config,
        client=model_client(),
        memory_store=memory_store,
        extra_presentation_tools=[build_plan_mix_extension(merchant)],
    )
    return build_merchant_router(
        storefront=storefront,
        backend=merchant,
        agent=agent,
        identity=IDENTITY,
        example_dir="telecom",
        overview_extras=lambda: {"today": merchant.today_snapshot()},
        portal_reads={"/base": merchant.base_overview},
    )
