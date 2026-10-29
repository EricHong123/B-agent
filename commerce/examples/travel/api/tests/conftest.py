# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

from datetime import date

import pytest

from demo_common.storefront_fixtures import load_json
from demo_common.tests.fixtures import *  # noqa: F403
from travel.api import main as main_module
from travel.api.agent_config import build_merchant_config
from travel.api.merchant import IDENTITY, create_merchant_router
from travel.api.mock_merchant import MockTravelMerchant
from travel.api.mock_travel import DATA_DIR, MockTravel
from travel.api.occupancy import build_occupancy_extension


@pytest.fixture(scope="session")
def main():
    return main_module


# Availability windows and the occupancy calendar shift by the whole weeks between
# catalog.json's dates_anchored_to and the backend's clock; a backend pinned to that day
# keeps the authored dates the tests name.
PINNED_TODAY = date.fromisoformat(load_json(DATA_DIR, "catalog.json")["dates_anchored_to"])


@pytest.fixture(scope="session")
def make_storefront():
    return lambda: MockTravel(today=PINNED_TODAY)


@pytest.fixture
def merchant(backend) -> MockTravelMerchant:
    return MockTravelMerchant(backend, build_merchant_config("ACME Travel"))


@pytest.fixture
def merchant_extensions(merchant) -> list:
    return [build_occupancy_extension(merchant)]


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
    return "AL-STAY-101"


@pytest.fixture(scope="session")
def cart_product() -> str:
    return "AL-EXP-301"


@pytest.fixture(scope="session")
def relevance_probe() -> tuple[str, str, str, set[str]]:
    """Returns (query, non-relevance sort, product that must lead, faint matches that must be cut)."""
    return ("riverside inn kyoto", "rating", "AL-STAY-106", {"AL-STAY-108", "AL-EXP-304"})


@pytest.fixture(scope="session")
def showcase_stamps() -> set[str]:
    return {"free_cancellation_until", "date_flex", "units_left_for_dates"}
