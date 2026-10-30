# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

import pytest

from demo_common.tests.fixtures import *  # noqa: F403
from retail.api import main as main_module
from retail.api.agent_config import build_merchant_config
from retail.api.merchant import IDENTITY, create_merchant_router
from retail.api.mock_merchant import MockRetailMerchant
from retail.api.mock_retail import MockRetail


@pytest.fixture(scope="session")
def main():
    return main_module


@pytest.fixture(scope="session")
def make_storefront():
    return MockRetail


@pytest.fixture
def merchant(backend) -> MockRetailMerchant:
    return MockRetailMerchant(backend, build_merchant_config("ACME"))


@pytest.fixture(scope="session")
def merchant_identity():
    return IDENTITY


@pytest.fixture(scope="session")
def make_merchant_router():
    return create_merchant_router


@pytest.fixture(scope="session")
def extra_public_routes() -> set[str]:
    return set()


@pytest.fixture(scope="session")
def restockable_listing() -> str:
    return "AR-1601"


@pytest.fixture(scope="session")
def cart_product() -> str:
    return "AR-1301"


@pytest.fixture(scope="session")
def relevance_probe() -> tuple[str, str, str, set[str]]:
    """Returns (query, non-relevance sort, product that must lead, faint matches that must be cut)."""
    return ("sleeping bag camping", "rating", "AR-1203", {"AR-2003", "AR-1507"})


@pytest.fixture(scope="session")
def showcase_stamps() -> set[str]:
    return {"low_stock"}
