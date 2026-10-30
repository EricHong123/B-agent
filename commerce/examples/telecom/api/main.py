# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""ACME Mobile example API: the mock carrier behind the shared storefront routes, the
commercial-ops router under /api/merchant, and the telecom-only routes below.

    uvicorn telecom.api.main:app --app-dir examples --reload --port 8002

The demo has two profiles: the subscriber ``demo-user`` and the prospect ``demo-user-2``.
The storefront's profile switcher starts a session for the chosen one.
"""

from __future__ import annotations

from fastapi import HTTPException

from commerce_common.memory import InMemoryMemoryStore
from demo_common import (
    REPO_ROOT,
    CartAddRequest,
    MemorySeeder,
    build_storefront_host,
    load_demo_env,
    model_client,
)
from shopping_agent_runtime import ShoppingAgent

from .agent_config import build_shopping_config
from .merchant import create_merchant_router
from .mock_telecom import DATA_DIR, MockTelecom
from .plan_matrix import build_plan_matrix_extension

load_demo_env(DATA_DIR.parent)

backend = MockTelecom()
agent = ShoppingAgent(
    backend=backend,
    skills_dir=REPO_ROOT / "shopping-agent" / "skills",
    config=build_shopping_config(),
    client=model_client(),
    memory_store=InMemoryMemoryStore(),
    extra_presentation_tools=[build_plan_matrix_extension()],
)
host = build_storefront_host(
    title="ACME Mobile demo API",
    example_root=DATA_DIR.parent,
    backend=backend,
    agent=agent,
    memory_seeder=MemorySeeder(DATA_DIR / "memory-seed.json"),
)
app = host.app
app.include_router(create_merchant_router(backend, InMemoryMemoryStore()), prefix="/api/merchant")

# Plans and home internet are contracts, so only these categories get a button that
# skips the conversation and its disclosure step.
_DIRECT_ADD_CATEGORIES = {"devices", "add-ons"}


@app.post("/api/cart/add")
async def cart_add(request: CartAddRequest, record: host.CurrentSession) -> dict:
    product = backend.product(request.product_id)
    if product is None or product.category not in _DIRECT_ADD_CATEGORIES:
        raise HTTPException(
            status_code=400,
            detail=(
                "Only devices and add-ons can be added directly. Plan and home-internet "
                "changes go through the ACME Assistant so the terms can be reviewed first."
            ),
        )
    return await host.direct_add(
        record,
        request,
        note="Customer tapped the add-to-order button on {title} ({product_id}), quantity {quantity}.",
    )


@app.get("/api/account")
async def get_account(record: host.CurrentSession) -> dict:
    """The signed-in profile's account context, as the agent sees it, for the storefront
    chrome; a prospect gets ``{"account": null}``."""
    return {"account": await backend.get_account_context(host.context(record))}
