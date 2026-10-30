# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The get_return_reasons result: per-listing return counts by reason over a window,
computed here from the backend's :class:`~merchant_agent.types.ReturnLog`, so every path
and every backend report the same arithmetic and the model only reads it. Each reason
carries the stage it usually points at; a few buyer notes per listing ride along as
evidence, clipped, inside the merchant data fence."""

from __future__ import annotations

import json
from collections import Counter, defaultdict

from commerce_common.fencing import truncate_display

from .types import (
    ListingReturns,
    ReasonCount,
    ReturnLog,
    ReturnNote,
    ReturnReason,
    ReturnRecord,
    ReturnsSummary,
    ReturnStage,
)

# The part of the operation a reason usually points at: what the listing says or shows,
# the item or service itself, getting it to the buyer, or helping them use it. "none"
# marks the baseline every listing has (a buyer who changed their plans); "unknown" is a
# reason the platform recorded outside this set.
REASON_STAGES: dict[ReturnReason, ReturnStage] = {
    ReturnReason.RUNS_SMALL: "listing",
    ReturnReason.RUNS_LARGE: "listing",
    ReturnReason.NOT_AS_DESCRIBED: "listing",
    ReturnReason.UNEXPECTED_CHARGE: "listing",
    ReturnReason.DEFECTIVE: "product",
    ReturnReason.SCHEDULE_CHANGED: "product",
    ReturnReason.COVERAGE_ISSUE: "product",
    ReturnReason.MISSING_PART: "fulfilment",
    ReturnReason.DAMAGED_IN_TRANSIT: "fulfilment",
    ReturnReason.ARRIVED_LATE: "fulfilment",
    ReturnReason.ACCESS_ISSUE: "support",
    ReturnReason.CHANGED_MIND: "none",
    ReturnReason.BOOKING_CANCELLED: "none",
    ReturnReason.TICKET_TRANSFERRED: "none",
    ReturnReason.OTHER: "unknown",
}

MAX_RETURN_LISTINGS = 10
MAX_NOTES_PER_LISTING = 3
NOTE_MAX_CHARS = 200


def _share(part: int, whole: int) -> float:
    return round(part / whole * 100, 1) if whole else 0.0


def reason_counts(records: list[ReturnRecord]) -> list[ReasonCount]:
    """Counts per reason, largest first, ties in the reason set's order."""
    counts = Counter(record.reason for record in records)
    order = list(ReturnReason)
    return [
        ReasonCount(
            reason=reason,
            count=count,
            share_pct=_share(count, len(records)),
            stage=REASON_STAGES[reason],
        )
        for reason, count in sorted(
            counts.items(), key=lambda item: (-item[1], order.index(item[0]))
        )
    ]


def _sample_notes(records: list[ReturnRecord], ranked: list[ReasonCount]) -> list[ReturnNote]:
    """Notes from the most frequent reason first, most recent first within a reason."""
    rank = {count.reason: index for index, count in enumerate(ranked)}
    with_notes = [record for record in records if record.note and record.note.strip()]
    with_notes.sort(key=lambda record: (rank[record.reason], -record.returned_on.toordinal()))
    return [
        ReturnNote(
            reason=record.reason,
            returned_on=record.returned_on,
            text=truncate_display(" ".join((record.note or "").split()), NOTE_MAX_CHARS),
        )
        for record in with_notes[:MAX_NOTES_PER_LISTING]
    ]


def summarize_returns(
    log: ReturnLog, *, max_listings: int = MAX_RETURN_LISTINGS, max_chars: int | None = None
) -> ReturnsSummary:
    """The window's totals and reason counts, then one row per listing (a family rolls up
    its variants) ranked by returns, cut to ``max_listings`` and then, from the bottom,
    until the summary, serialized as the fence serializes it, fits ``max_chars``, so the
    fence never cuts it mid-row."""
    records = log.records
    groups: dict[str, list[ReturnRecord]] = defaultdict(list)
    for record in records:
        groups[record.variant_of or record.listing_id].append(record)

    rows: list[ListingReturns] = []
    for listing_id, group in groups.items():
        ranked = reason_counts(group)
        variants = Counter(record.listing_id for record in group if record.variant_of)
        dates = [record.returned_on for record in group]
        rows.append(
            ListingReturns(
                listing_id=listing_id,
                title=next((record.title for record in group if record.title), None),
                returns=len(group),
                share_of_returns_pct=_share(len(group), len(records)),
                by_reason=ranked,
                variants=dict(variants.most_common()) or None,
                first_returned_on=min(dates),
                last_returned_on=max(dates),
                sample_notes=_sample_notes(group, ranked),
            )
        )
    rows.sort(key=lambda row: (-row.returns, row.listing_id))

    summary = ReturnsSummary(
        period=log.period,
        total_returns=len(records),
        by_reason=reason_counts(records),
        listings=rows[:max_listings],
        listings_with_returns=len(rows),
        note=log.note,
    )
    while (
        max_chars is not None
        and summary.listings
        and len(json.dumps(summary.model_dump(mode="json", exclude_none=True), ensure_ascii=False))
        > max_chars
    ):
        summary.listings.pop()
    return summary
