# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

from commerce_common.presentation import invalid_payload_prefix


async def test_enrichment_fills_the_calendar_from_backend_data(merchant_executor):
    result = await merchant_executor.execute(
        "present_occupancy_calendar",
        {
            "listing_ids": ["AL-STAY-103", "AL-STAY-110"],
            "start": "2026-10-01",
            "end": "2026-10-31",
            "notes": {"AL-STAY-103": "Midweek pacing is the gap here."},
        },
    )
    assert not result.is_error
    ui = next(event for event in result.events if event.type == "ui")
    assert ui.data["component"] == "occupancy_calendar"
    payload = ui.data["payload"]
    assert payload["start"] == "2026-10-01"
    assert "suggestions" not in payload
    assert [row["listing_id"] for row in payload["listings"]] == ["AL-STAY-103", "AL-STAY-110"]

    baixa = payload["listings"][0]
    assert baixa["title"] == "ACME Guesthouses Baixa"
    assert baixa["base_nightly_rate"] == 126.0
    assert baixa["note"] == "Midweek pacing is the gap here."
    assert baixa["weeks"]
    assert all(week["nightly_rate"] == 126.0 for week in baixa["weeks"])
    assert min(week["midweek_occupancy_pct"] for week in baixa["weeks"]) < 50
    assert max(week["weekend_occupancy_pct"] for week in baixa["weeks"]) > 70


async def test_ungrounded_listing_ids_are_refused(merchant_executor):
    result = await merchant_executor.execute(
        "present_occupancy_calendar",
        {"listing_ids": ["AL-STAY-999"], "start": "2026-10-01", "end": "2026-10-31"},
    )
    assert result.is_error
    assert "occupancy data" in result.result_text
    assert not result.events

    # AL-STAY-105 exists but is outside the supplier's portfolio.
    kyoto = await merchant_executor.execute(
        "present_occupancy_calendar",
        {"listing_ids": ["AL-STAY-105"], "start": "2026-10-01", "end": "2026-10-31"},
    )
    assert kyoto.is_error


async def test_invalid_payloads_are_soft_errors(merchant_executor):
    missing_window = await merchant_executor.execute(
        "present_occupancy_calendar", {"listing_ids": ["AL-STAY-103"]}
    )
    assert missing_window.is_error
    assert missing_window.result_text.startswith(
        invalid_payload_prefix("present_occupancy_calendar")
    )

    bad_dates = await merchant_executor.execute(
        "present_occupancy_calendar",
        {"listing_ids": ["AL-STAY-103"], "start": "October", "end": "2026-10-3"},
    )
    assert bad_dates.is_error
    assert "ISO dates" in bad_dates.result_text


async def test_promotion_apply_flow_through_the_executor(
    merchant_executor, merchant, merchant_state
):
    listed = await merchant_executor.execute(
        "search_listings", {"query": "Lisbon stays", "limit": 25}
    )
    assert not listed.is_error
    assert "AL-STAY-103" in merchant_state.seen_listings
    # AL-STAY-110 is not in the Lisbon results, so get_listing supplies its provenance.
    condesa = await merchant_executor.execute("get_listing", {"listing_id": "AL-STAY-110"})
    assert not condesa.is_error

    staged = await merchant_executor.execute(
        "stage_promotion",
        {
            "name": "October midweek rate adjustment",
            "listing_ids": ["AL-STAY-103", "AL-STAY-110"],
            "discount_pct": 15,
            "starts": "2026-10-05",
            "ends": "2026-10-29",
        },
    )
    assert not staged.is_error
    change_id = next(
        event.data["change"]["change_id"]
        for event in staged.events
        if event.type == "change_update"
    )

    applied = await merchant_executor.execute("apply_change", {"change_id": change_id})
    assert not applied.is_error
    assert merchant.rate_overrides["AL-STAY-110"][0]["change_id"] == change_id

    calendar = await merchant_executor.execute(
        "present_occupancy_calendar",
        {"listing_ids": ["AL-STAY-110"], "start": "2026-10-05", "end": "2026-10-29"},
    )
    ui = next(event for event in calendar.events if event.type == "ui")
    weeks = ui.data["payload"]["listings"][0]["weeks"]
    assert all(week["override"]["change_id"] == change_id for week in weeks)

    again = await merchant_executor.execute("apply_change", {"change_id": change_id})
    assert again.is_error
    assert "applied" in again.result_text
