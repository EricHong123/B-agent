# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

from datetime import UTC, datetime, timedelta

import pytest

from demo_common.tests.fixtures import *  # noqa: F403
from entertainment.api import main as main_module
from entertainment.api.agent_config import build_merchant_config
from entertainment.api.event_pacing import build_event_pacing_extension
from entertainment.api.merchant import IDENTITY, create_merchant_router
from entertainment.api.mock_merchant import MockTicketingMerchant
from entertainment.api.mock_ticketing import MockTicketing


class FakeClock:
    def __init__(self) -> None:
        self.current = datetime(2026, 7, 9, 12, 0, 0, tzinfo=UTC)

    def __call__(self) -> datetime:
        return self.current

    def advance(self, seconds: float) -> None:
        self.current += timedelta(seconds=seconds)


@pytest.fixture(scope="session")
def main():
    return main_module


@pytest.fixture(scope="session")
def make_storefront():
    return MockTicketing


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock()


@pytest.fixture
def backend(clock: FakeClock) -> MockTicketing:
    return MockTicketing(now=clock)


@pytest.fixture
def merchant(backend) -> MockTicketingMerchant:
    return MockTicketingMerchant(backend, build_merchant_config("ACME Tickets"))


@pytest.fixture
def merchant_extensions(merchant) -> list:
    return [build_event_pacing_extension(merchant)]


@pytest.fixture(scope="session")
def merchant_identity():
    return IDENTITY


@pytest.fixture(scope="session")
def make_merchant_router():
    return create_merchant_router


@pytest.fixture(scope="session")
def extra_public_routes() -> set[str]:
    # The demo return trigger stands in for the inventory system's returns feed.
    return {"/api/demo/return"}


@pytest.fixture(scope="session")
def restockable_listing() -> None:
    return None  # a ticketing "restock" releases held seats and is re-checked at apply


@pytest.fixture(scope="session")
def cart_product() -> str:
    return "AT-TIX-101-LOW"


@pytest.fixture(scope="session")
def relevance_probe() -> tuple[str, str, str, set[str]]:
    """Query, non-relevance sort, the product it must lead with, one-token matches it must omit."""
    return (
        "philharmonic season opener balcony",
        "price_asc",
        "AT-TIX-106-BAL",
        {"AT-TIX-105-BAL"},
    )


@pytest.fixture(scope="session")
def showcase_stamps() -> set[str]:
    return {
        "labels",
        "in_stock",
        "tickets_remaining",
        "value_score",
        "value_verdict",
        "vs_box_office",
        "box_office_all_in_usd",
    }
