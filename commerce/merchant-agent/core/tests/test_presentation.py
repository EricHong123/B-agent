# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

import pytest
from pydantic import ValidationError

from merchant_agent.enrichment import (
    reconcile_change_preview_currency,
    reconcile_change_preview_weekdays,
)
from merchant_agent.tools.presentation import (
    PresentChangePreviewPayload,
    PresentDigestPayload,
    PresentMetricsPayload,
)


def test_metrics_payload_validates_picks_and_drops_undeclared_keys():
    payload = PresentMetricsPayload.model_validate(
        {
            "title": "Last week at a glance",
            "period": "last_7_days",
            "picks": [{"metric": "sales", "note": "up on the prior week"}],
            "suggestions": ["Break sales down by category", "Show conversion by day"],
        }
    )
    assert payload.picks[0].metric == "sales"
    assert "suggestions" not in payload.model_dump()
    with pytest.raises(ValidationError):
        PresentMetricsPayload.model_validate({"picks": []})


def test_metric_shorthand_resolves_to_canonical_snapshot_values():
    from merchant_agent.enrichment import resolve_metrics
    from merchant_agent.types import BusinessSnapshot, MerchantSessionState

    state = MerchantSessionState()
    state.remember_snapshot(
        BusinessSnapshot(
            period="last_7_days",
            sales=17338.0,
            orders=386,
            traffic=9120,
            conversion_rate=2.9,
            average_order_value=44.92,
        )
    )
    payload = PresentMetricsPayload.model_validate(
        {
            "picks": [
                {"metric": "conversion"},  # shorthand for conversion_rate
                {"metric": "AOV"},  # shorthand for average_order_value
                {"metric": "revenue"},  # shorthand for sales
                {"metric": "made-up-metric"},  # no snapshot field
            ]
        }
    )
    resolved, missing = resolve_metrics(state, payload.picks)
    by_metric = {entry["metric"]: entry for entry in resolved}
    assert by_metric["conversion_rate"]["value"] == 2.9
    assert by_metric["average_order_value"]["value"] == 44.92
    assert by_metric["sales"]["value"] == 17338.0
    assert missing == ["made-up-metric"]


def test_a_figure_the_store_cannot_supply_is_a_missing_pick_not_a_zero_tile():
    from merchant_agent.enrichment import resolve_campaign_metric, resolve_metrics
    from merchant_agent.types import BusinessSnapshot, Campaign, MerchantSessionState, MetricSeries

    state = MerchantSessionState()
    # No analytics scope: traffic and conversion are None, and the note says why.
    state.remember_snapshot(
        BusinessSnapshot(
            period="last_7_days",
            sales=17338.0,
            orders=386,
            note="traffic and conversion need the analytics scope this store has not granted",
        )
    )
    state.remember_series(MetricSeries(metric="sessions", note="history limited to 60 days"))
    state.remember_campaigns(
        [Campaign(campaign_id="c-1", name="Spring push", status="active", budget=500.0)]
    )
    payload = PresentMetricsPayload.model_validate(
        {
            "picks": [
                {"metric": "sales"},
                {"metric": "traffic"},
                {"metric": "conversion"},
                {"metric": "sessions"},
            ]
        }
    )
    resolved, missing = resolve_metrics(state, payload.picks)
    assert [entry["metric"] for entry in resolved] == ["sales"]
    assert missing == ["traffic", "conversion", "sessions"]
    # A channel that does not report spend or revenue yields no ROAS tile either.
    assert resolve_campaign_metric(state, "Spring push roas") is None
    assert resolve_campaign_metric(state, "Spring push budget")["value"] == 500.0


def test_metric_alias_never_shadows_a_series_seen_under_the_raw_name():
    from merchant_agent.enrichment import resolve_metrics
    from merchant_agent.types import BusinessSnapshot, MerchantSessionState, MetricSeries

    state = MerchantSessionState()
    state.remember_snapshot(
        BusinessSnapshot(
            period="last_7_days",
            sales=17338.0,
            orders=386,
            traffic=9120,
            conversion_rate=2.9,
            average_order_value=44.92,
        )
    )
    state.remember_series(
        MetricSeries(
            metric="revenue",
            period="last_30_days",
            granularity="day",
            points=[{"date": "2026-07-01", "value": 2100.0}],
        )
    )
    payload = PresentMetricsPayload.model_validate({"picks": [{"metric": "revenue"}]})
    resolved, missing = resolve_metrics(state, payload.picks)
    assert missing == []
    (entry,) = resolved
    assert entry["metric"] == "revenue"
    assert entry["series"]["period"] == "last_30_days"
    assert "value" not in entry


def test_digest_payload_requires_kind_and_headline():
    payload = PresentDigestPayload.model_validate(
        {
            "items": [
                {
                    "kind": "low_stock",
                    "ref_id": "L-001",
                    "headline": "Two kids-room planters are nearly out of stock",
                    "why_it_matters": "They sold 41 units last week",
                }
            ]
        }
    )
    assert payload.items[0].kind == "low_stock"
    with pytest.raises(ValidationError):
        PresentDigestPayload.model_validate({"items": [{"headline": "missing kind"}]})


def test_change_preview_payload_requires_change_id():
    payload = PresentChangePreviewPayload.model_validate(
        {"change_id": "chg-0001", "headline": "Restock 24 planters"}
    )
    assert payload.change_id == "chg-0001"
    with pytest.raises(ValidationError):
        PresentChangePreviewPayload.model_validate({"headline": "no change id"})


def test_change_preview_currency_reconciliation_drops_conflicting_text():
    enriched = {
        "change_id": "chg-0002",
        "headline": "Rate ease: $204 to $183.60",
        "note": "Nightly rate moves from €204 to €183.60 (−€889 for the window).",
        "change": {"change_id": "chg-0002", "currency": "USD"},
    }
    message = reconcile_change_preview_currency(enriched)
    assert message is not None and "USD" in message
    assert "note" not in enriched
    assert enriched["headline"] == "Rate ease: $204 to $183.60"


def test_change_preview_currency_reconciliation_is_a_no_op_when_consistent():
    enriched = {
        "change_id": "chg-0003",
        "note": "Margin moves from 56.2% to 53.9% ($24.00 → $22.80).",
        "change": {"change_id": "chg-0003", "currency": "USD"},
    }
    assert reconcile_change_preview_currency(enriched) is None
    assert "note" in enriched
    dollar_elsewhere = {"note": "$24.00 → $22.80", "change": {"change_id": "c", "currency": "CAD"}}
    assert reconcile_change_preview_currency(dollar_elsewhere) is None
    assert "note" in dollar_elsewhere
    no_currency = {"note": "€10 off", "change": {"change_id": "chg-0004"}}
    assert reconcile_change_preview_currency(no_currency) is None
    assert "note" in no_currency


# 2026-07-11 is a Saturday, 2026-07-12 a Sunday, 2026-07-13 a Monday.
_PROMO_CHANGE = {
    "change_id": "chg-0006",
    "summary": "Weekend Promo (15% off, 2026-07-11 to 2026-07-13)",
    "items": [{"target": "AR-2102", "field": "promotion_price", "before": 24.0, "after": 20.4}],
    "created_at": "2026-07-10T09:06:29Z",
}


def test_change_preview_weekday_reconciliation_drops_mismatched_text():
    enriched = {
        "headline": "Weekend Promo: 15% off — Sat 12 Jul & Sun 13 Jul",
        "note": "Runs Saturday and Sunday only.",
        "change": dict(_PROMO_CHANGE),
    }
    message = reconcile_change_preview_weekdays(enriched)
    assert message is not None and "headline" in message
    assert "headline" not in enriched
    # A weekday with no date attached is not checked.
    assert enriched["note"] == "Runs Saturday and Sunday only."


def test_change_preview_weekday_reconciliation_keeps_correct_pairs():
    enriched = {
        "headline": "Weekend Promo: 15% off — Sat 11 Jul & Sun 12 Jul",
        "note": "Ends Monday, Jul 13.",
        "change": dict(_PROMO_CHANGE),
    }
    assert reconcile_change_preview_weekdays(enriched) is None
    assert enriched["headline"].startswith("Weekend Promo")


def test_change_preview_weekday_reconciliation_uses_created_at_year_when_no_dates():
    dateless = {
        "change_id": "chg-0007",
        "summary": "Title refresh",
        "items": [{"target": "AR-2102", "field": "title", "before": "a", "after": "b"}],
        "created_at": "2026-07-10T09:06:29Z",
    }
    wrong = {"headline": "Ready for Sat 12 Jul", "change": dict(dateless)}
    assert reconcile_change_preview_weekdays(wrong) is not None
    right = {"headline": "Ready for Sun 12 Jul", "change": dict(dateless)}
    assert reconcile_change_preview_weekdays(right) is None
    # Without a change record or a parseable created_at there is nothing to check against.
    assert reconcile_change_preview_weekdays({"headline": "Sat 12 Jul"}) is None
    assert (
        reconcile_change_preview_weekdays(
            {"headline": "Sat 12 Jul", "change": {"summary": "x", "created_at": "unknown"}}
        )
        is None
    )


def test_change_preview_weekday_reconciliation_matches_whole_words_only():
    # "Wedding" is not a weekday; full month names are parsed.
    enriched = {
        "headline": "Wedding Jul 11 party bundle",
        "note": "Runs Saturday, July 11 through Sunday, July 12.",
        "change": dict(_PROMO_CHANGE),
    }
    assert reconcile_change_preview_weekdays(enriched) is None
    wrong_full = {"note": "Starts Saturday, July 12.", "change": dict(_PROMO_CHANGE)}
    assert reconcile_change_preview_weekdays(wrong_full) is not None
    assert "note" not in wrong_full
