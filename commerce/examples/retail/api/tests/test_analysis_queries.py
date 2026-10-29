# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Analysis queries: SELECT-only enforcement, tenant scoping, and row caps."""

from __future__ import annotations

import pytest

from merchant_agent import MerchantAgentConfig, MerchantSessionContext
from retail.api.mock_merchant import MockRetailMerchant


async def test_selects_run_against_the_live_fixture_state(merchant, operator_session):
    table = await merchant.execute_analysis_query(
        operator_session, "SELECT count(*), sum(sales) FROM daily_metrics"
    )
    assert table is not None
    assert table.columns == ["count(*)", "sum(sales)"]
    assert table.rows[0][0] == 90  # the 90-day daily fixture
    assert table.rows[0][1] > 0

    joined = await merchant.execute_analysis_query(
        operator_session,
        "SELECT category, count(*) AS n, sum(price * stock) AS shelf_value "
        "FROM listings GROUP BY category ORDER BY shelf_value DESC",
    )
    assert joined is not None
    assert len(joined.columns) == 3
    assert joined.rows


async def test_writes_are_refused_before_the_engine(merchant, operator_session):
    with pytest.raises(ValueError, match="refused"):
        await merchant.execute_analysis_query(operator_session, "UPDATE listings SET price = 1")
    with pytest.raises(ValueError, match="refused"):
        await merchant.execute_analysis_query(operator_session, "SELECT 1; DROP TABLE listings")


async def test_the_engine_itself_denies_writes(merchant, operator_session, monkeypatch):
    # With the allowlist bypassed, the sqlite authorizer is what denies the write.
    monkeypatch.setattr("retail.api.mock_merchant.check_analysis_sql", lambda sql: None)
    with pytest.raises(ValueError, match="not authorized|prohibited|denied"):
        await merchant.execute_analysis_query(operator_session, "DELETE FROM listings")


async def test_queries_are_tenant_scoped(merchant):
    foreign = MerchantSessionContext(session_id="ms-x", merchant_id="someone-else", operator="op")
    with pytest.raises(PermissionError):
        await merchant.execute_analysis_query(foreign, "SELECT 1")
    assert await merchant.get_analysis_schema(foreign) is None


async def test_row_cap_marks_truncation(backend, operator_session):
    merchant = MockRetailMerchant(
        backend, MerchantAgentConfig(brand_name="ACME", max_analysis_rows=5)
    )
    table = await merchant.execute_analysis_query(
        operator_session, "SELECT date, sales FROM daily_metrics ORDER BY date"
    )
    assert table is not None
    assert len(table.rows) == 5
    assert table.truncated
    assert table.note == "row-capped"


async def test_bad_sql_surfaces_the_engine_reason(merchant, operator_session):
    with pytest.raises(ValueError, match="no such column"):
        await merchant.execute_analysis_query(operator_session, "SELECT nonsense FROM listings")


async def test_schema_notes_describe_the_tables(merchant, operator_session):
    schema = await merchant.get_analysis_schema(operator_session)
    assert schema is not None
    for table_name in ("daily_metrics", "listings", "campaigns"):
        assert table_name in schema
