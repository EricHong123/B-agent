# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

import pytest

from demo_common.tests.fixtures import *  # noqa: F403
from telecom.api import main as main_module
from telecom.api.agent_config import build_merchant_config
from telecom.api.merchant import IDENTITY, create_merchant_router
from telecom.api.mock_merchant import MockTelecomMerchant
from telecom.api.mock_telecom import MockTelecom
from telecom.api.plan_mix import build_plan_mix_extension


@pytest.fixture(scope="session")
def main():
    return main_module


@pytest.fixture(scope="session")
def make_storefront():
    return MockTelecom


@pytest.fixture
def merchant(backend) -> MockTelecomMerchant:
    return MockTelecomMerchant(backend, build_merchant_config("ACME Mobile"))


@pytest.fixture
def merchant_extensions(merchant) -> list:
    return [build_plan_mix_extension(merchant)]


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
    return "AM-DEV-201"


@pytest.fixture(scope="session")
def cart_product() -> str:
    return "AM-ADD-401"


@pytest.fixture(scope="session")
def relevance_probe() -> tuple[str, str, str, set[str]]:
    """Query, non-relevance sort, the product it must lead with, one-token matches it must omit."""
    return ("prepaid plan", "rating", "AM-PLAN-105", {"AM-PLAN-103", "AM-PLAN-104"})
