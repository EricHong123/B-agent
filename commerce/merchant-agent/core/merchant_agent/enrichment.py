# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The built-in merchant components: metric picks resolved to the values tools returned
this session, digest items joined to their listing or change records, and a change
preview built from the staged record with model text that contradicts it removed. Each
has a partial hook that renders the grounded part of a still-streaming call.
"""

from __future__ import annotations

import re
from datetime import date, datetime
from typing import Any, get_args

from commerce_common.presentation import (
    CHIPS_COMPONENT,
    CHIPS_TOOL,
    EnrichmentContext,
    PresentationComponent,
    PresentationRefused,
    PresentSuggestionsPayload,
)

from .tools.presentation import (
    PREVIEW_TOOL,
    DigestItem,
    MetricPick,
    PresentChangePreviewPayload,
    PresentDigestPayload,
    PresentMetricsPayload,
)
from .types import MerchantSessionState

# -- present_metrics --------------------------------------------------------------------

# Shorthand tried only after a pick resolves under no name the session holds.
_METRIC_ALIASES: dict[str, str] = {
    "conversion": "conversion_rate",
    "cvr": "conversion_rate",
    "aov": "average_order_value",
    "avg_order_value": "average_order_value",
    "average_order": "average_order_value",
    "revenue": "sales",
}


def resolve_campaign_metric(state: MerchantSessionState, pick: str) -> dict[str, Any] | None:
    """A pick naming a seen campaign (by id or name) and one of spend, revenue,
    budget, or roas; the longest matching campaign token wins."""
    text = pick.lower()
    matches = [
        (len(token), campaign)
        for campaign in state.seen_campaigns.values()
        for token in (campaign.campaign_id.lower(), campaign.name.lower())
        if token in text
    ]
    if not matches:
        return None
    campaign = max(matches, key=lambda match: match[0])[1]
    currency: str | None = campaign.currency
    value: float | None
    if "roas" in text or "return on ad spend" in text:
        measure = "roas"
        value = (
            round(campaign.revenue / campaign.spend, 2)
            if campaign.spend and campaign.revenue is not None
            else None
        )
        currency = None
    elif "revenue" in text:
        measure, value = "revenue", campaign.revenue
    elif "budget" in text:
        measure, value = "budget", campaign.budget
    elif "spend" in text or "spent" in text:
        measure, value = "spend", campaign.spend
    else:
        return None
    if value is None:
        return None
    return {
        "metric": f"{campaign.name} — {measure}",
        "value": value,
        "change_pct": None,
        "currency": currency,
    }


def resolve_analysis_metric(state: MerchantSessionState, pick: str) -> dict[str, Any] | None:
    """A pick naming a figure or derived series from an analysis recorded this session;
    the longest matching label wins."""
    text = pick.lower()
    figures = [
        (len(figure.label), figure)
        for analysis in state.seen_analyses.values()
        for figure in analysis.figures
        if figure.label.lower() in text
    ]
    if figures:
        figure = max(figures, key=lambda match: match[0])[1]
        return {
            "metric": figure.label,
            "value": figure.value,
            "change_pct": figure.change_pct,
            "currency": None,
        }
    series_matches = [
        (len(series.metric), series)
        for analysis in state.seen_analyses.values()
        for series in analysis.derived_series
        if series.metric.lower() in text
    ]
    if series_matches:
        series = max(series_matches, key=lambda match: match[0])[1]
        return {
            "metric": series.metric,
            "series": series.model_dump(mode="json", exclude_none=True),
        }
    return None


def resolve_metrics(
    state: MerchantSessionState, picks: list[MetricPick]
) -> tuple[list[dict[str, Any]], list[str]]:
    """Each pick as a tile from the snapshot, a queried series, a campaign, or an
    analysis, plus the picks nothing this session can supply."""
    snapshot = state.latest_snapshot
    snapshot_values: dict[str, tuple[float | None, float | None]] = {}
    if snapshot is not None:
        snapshot_values = {
            "sales": (snapshot.sales, snapshot.sales_change_pct),
            "orders": (float(snapshot.orders), snapshot.orders_change_pct),
            "traffic": (snapshot.traffic, snapshot.traffic_change_pct),
            "conversion_rate": (snapshot.conversion_rate, snapshot.conversion_change_pct),
            "average_order_value": (snapshot.average_order_value, None),
        }
    resolved: list[dict[str, Any]] = []
    missing: list[str] = []
    for pick in picks:
        key = pick.metric.strip().lower().replace(" ", "_")
        series = state.seen_series.get(pick.metric) or state.seen_series.get(key)
        campaign = resolve_campaign_metric(state, pick.metric)
        analysis = resolve_analysis_metric(state, pick.metric)
        if key not in snapshot_values and series is None and campaign is None and analysis is None:
            key = _METRIC_ALIASES.get(key, key)
        if key in snapshot_values and snapshot_values[key][0] is not None:
            value, change_pct = snapshot_values[key]
            resolved.append(
                {
                    "metric": key,
                    "value": value,
                    "change_pct": change_pct,
                    "note": pick.note,
                    "currency": snapshot.currency if snapshot else None,
                }
            )
        elif series is not None and not series.points:
            missing.append(pick.metric)
        elif series is not None:
            resolved.append(
                {
                    "metric": series.metric,
                    "series": series.model_dump(mode="json", exclude_none=True),
                    "note": pick.note,
                }
            )
        elif campaign is not None:
            resolved.append(campaign | {"note": pick.note})
        elif analysis is not None:
            resolved.append(analysis | {"note": pick.note})
        else:
            missing.append(pick.metric)
    return resolved, missing


async def enrich_metrics(
    payload: PresentMetricsPayload, context: EnrichmentContext
) -> dict[str, Any]:
    state: MerchantSessionState = context.state
    metrics, missing = resolve_metrics(state, payload.picks)
    if not metrics:
        raise PresentationRefused(
            "None of those picks names a measure a tool returned this session (a "
            "snapshot figure, a queried series, a campaign, or an analysis figure). Read "
            "the figures first (get_business_snapshot, query_metrics, "
            "get_campaign_performance), then name each pick as the tool spelled it, or "
            "as a campaign id plus one measure ('<campaign_id> spend')."
        )
    if missing:
        context.notes.append(f"Skipped metrics not returned this session: {', '.join(missing)}.")
    enriched = payload.model_dump(exclude_none=True, exclude={"picks"})
    enriched["metrics"] = metrics
    _snapshot_period(enriched, state)
    return enriched


def _snapshot_period(payload: dict[str, Any], state: MerchantSessionState) -> None:
    if state.latest_snapshot is not None and not payload.get("period"):
        payload["period"] = state.latest_snapshot.period


def partial_metrics(data: dict[str, Any], state: MerchantSessionState) -> dict[str, Any] | None:
    """The grounded tiles of a still-streaming call; nothing until one pick resolves, so
    no card appears ahead of a refusal."""
    picks = [
        MetricPick.model_construct(metric=pick["metric"], note=pick.get("note"))
        for pick in data.get("picks") or []
        if isinstance(pick, dict) and isinstance(pick.get("metric"), str) and pick["metric"]
    ]
    metrics, _missing = resolve_metrics(state, picks)
    if not metrics:
        return None
    payload: dict[str, Any] = {"metrics": metrics}
    for key in ("title", "period"):
        if data.get(key):
            payload[key] = data[key]
    _snapshot_period(payload, state)
    return payload


# -- present_digest ---------------------------------------------------------------------


async def enrich_digest(
    payload: PresentDigestPayload, context: EnrichmentContext
) -> dict[str, Any]:
    enriched = payload.model_dump(exclude_none=True)
    enriched["items"] = [
        _joined(item.model_dump(exclude_none=True), item.ref_id, context.state)
        for item in payload.items
    ]
    return enriched


def _joined(entry: dict[str, Any], ref_id: Any, state: MerchantSessionState) -> dict[str, Any]:
    """A digest entry with the listing or change record its ``ref_id`` names attached,
    when a tool returned that record this session."""
    ref_id = str(ref_id or "")
    if ref_id in state.seen_listings:
        entry["listing"] = state.seen_listings[ref_id].model_dump(exclude_none=True)
    if ref_id in state.seen_changes:
        entry["change"] = state.seen_changes[ref_id].model_dump(mode="json", exclude_none=True)
    return entry


_DIGEST_KINDS = frozenset(get_args(DigestItem.model_fields["kind"].annotation))


def partial_digest(data: dict[str, Any], state: MerchantSessionState) -> dict[str, Any] | None:
    """The entries of a still-streaming digest whose kind and headline have closed (a
    kind the schema does not list waits for validation), each joined to its listing or
    change record."""
    items = [
        _joined(dict(item), item.get("ref_id"), state)
        for item in data.get("items") or []
        if isinstance(item, dict) and item.get("kind") in _DIGEST_KINDS and item.get("headline")
    ]
    if not items and not data.get("title"):
        return None
    return {"title": data.get("title") or "", "items": items}


# -- present_change_preview -------------------------------------------------------------

# Only a conflict matters: a symbol none of whose currencies is the change's.
_CURRENCY_SYMBOLS: dict[str, frozenset[str]] = {
    "$": frozenset({"USD", "CAD", "AUD", "NZD", "SGD", "HKD", "MXN"}),
    "€": frozenset({"EUR"}),
    "£": frozenset({"GBP"}),
    "¥": frozenset({"JPY", "CNY"}),
}

_MONTH_NUMBERS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}
_WEEKDAYS_PATTERN = (
    r"mon(?:day)?|tue(?:s(?:day)?)?|wed(?:nesday)?|thu(?:r(?:s(?:day)?)?)?"
    r"|fri(?:day)?|sat(?:urday)?|sun(?:day)?"
)
_MONTHS_PATTERN = (
    r"jan(?:uary)?|feb(?:ruary)?|mar(?:ch)?|apr(?:il)?|may|jun(?:e)?"
    r"|jul(?:y)?|aug(?:ust)?|sep(?:t(?:ember)?)?|oct(?:ober)?|nov(?:ember)?|dec(?:ember)?"
)
# A weekday followed by a day-month or month-day pair; a bare weekday is not checkable.
# Whole words only, so "Wedding Jul 12" is not a Wednesday.
_WEEKDAY_DATE = re.compile(
    rf"\b(?P<w>{_WEEKDAYS_PATTERN})\b\.?,?\s+"
    rf"(?:(?P<d1>\d{{1,2}})\s+(?P<m1>{_MONTHS_PATTERN})\b"
    rf"|(?P<m2>{_MONTHS_PATTERN})\b\.?\s+(?P<d2>\d{{1,2}}))\b",
    re.IGNORECASE,
)
_ISO_DATE = re.compile(r"\b(\d{4})-(\d{2})-(\d{2})\b")
_WEEKDAY_INDEX = {"mon": 0, "tue": 1, "wed": 2, "thu": 3, "fri": 4, "sat": 5, "sun": 6}


def _drop_fields(enriched: dict[str, Any], offending: Any) -> list[str]:
    return [
        name
        for name in ("headline", "note")
        if isinstance(text := enriched.get(name), str)
        and offending(text)
        and enriched.pop(name, None) is not None
    ]


def reconcile_change_preview_currency(enriched: dict[str, Any]) -> str | None:
    """Remove model text whose currency symbol conflicts with the change's currency;
    returns the note for the model when something was removed."""
    change = enriched.get("change")
    currency = change.get("currency") if isinstance(change, dict) else None
    if not currency:
        return None
    conflicting = tuple(sym for sym, codes in _CURRENCY_SYMBOLS.items() if currency not in codes)
    dropped = _drop_fields(enriched, lambda text: any(sym in text for sym in conflicting))
    if not dropped:
        return None
    return (
        f"Dropped {' and '.join(dropped)}: amounts on this card must be stated in the "
        f"change's currency ({currency}). Restate them using the staged change record's "
        "own figures."
    )


def _candidate_years(change: dict[str, Any]) -> list[int]:
    """The years the change's own dates name; failing that, the staging year and the
    next, since a window staged in December can start in January."""
    corpus = [str(change.get("summary", ""))]
    for item in change.get("items") or []:
        if isinstance(item, dict):
            corpus.extend(str(v) for v in (item.get("before"), item.get("after")) if v)
    years = {int(m.group(1)) for text in corpus for m in _ISO_DATE.finditer(text)}
    if not years:
        created = str(change.get("created_at", ""))
        try:
            year = datetime.fromisoformat(created.replace("Z", "+00:00")).year
        except ValueError:
            return []
        years = {year, year + 1}
    return sorted(years)


def reconcile_change_preview_weekdays(enriched: dict[str, Any]) -> str | None:
    """Remove model text pairing a weekday with a date that is not that weekday in any
    year the change's dates span; returns the note for the model when something was
    removed."""
    change = enriched.get("change")
    if not isinstance(change, dict):
        return None
    years = _candidate_years(change)
    if not years:
        return None

    def has_wrong_weekday(text: str) -> bool:
        for match in _WEEKDAY_DATE.finditer(text):
            weekday = _WEEKDAY_INDEX[match.group("w").lower()[:3]]
            month = _MONTH_NUMBERS[(match.group("m1") or match.group("m2")).lower()[:3]]
            day = int(match.group("d1") or match.group("d2"))
            plausible = False
            for year in years:
                try:
                    plausible = date(year, month, day).weekday() == weekday
                except ValueError:
                    continue
                if plausible:
                    break
            if not plausible:
                return True
        return False

    dropped = _drop_fields(enriched, has_wrong_weekday)
    if not dropped:
        return None
    return (
        f"Dropped {' and '.join(dropped)}: a weekday named there does not match its "
        "date. Derive weekday names from the staged change record's own dates and "
        "restate, or state the dates without weekday names."
    )


async def enrich_change_preview(
    payload: PresentChangePreviewPayload, context: EnrichmentContext
) -> dict[str, Any]:
    change = context.state.seen_changes.get(payload.change_id)
    if change is None:
        raise PresentationRefused(
            "That change_id was not staged or listed in this session. Stage the "
            "change first, then preview it."
        )
    enriched = payload.model_dump(exclude_none=True)
    enriched["change"] = change.model_dump(mode="json", exclude_none=True)
    for reconcile in (reconcile_change_preview_currency, reconcile_change_preview_weekdays):
        if note := reconcile(enriched):
            context.notes.append(note)
    return enriched


def partial_change_preview(
    data: dict[str, Any], state: MerchantSessionState
) -> dict[str, Any] | None:
    """The staged record as soon as the change_id closes; the model's headline and note
    join on the final event, after the reconcilers have read them."""
    change = state.seen_changes.get(str(data.get("change_id") or ""))
    if change is None:
        return None
    return {
        "change_id": change.change_id,
        "change": change.model_dump(mode="json", exclude_none=True),
    }


PRESENTATION_COMPONENTS: dict[str, PresentationComponent] = {
    spec.name: spec
    for spec in (
        PresentationComponent(
            name="present_metrics",
            component="metrics",
            payload_model=PresentMetricsPayload,
            enrich=enrich_metrics,
            enrich_partial=partial_metrics,
        ),
        PresentationComponent(
            name="present_digest",
            component="digest",
            payload_model=PresentDigestPayload,
            enrich=enrich_digest,
            enrich_partial=partial_digest,
        ),
        PresentationComponent(
            name=PREVIEW_TOOL,
            component="change_preview",
            payload_model=PresentChangePreviewPayload,
            enrich=enrich_change_preview,
            enrich_partial=partial_change_preview,
        ),
        PresentationComponent(
            name=CHIPS_TOOL,
            component=CHIPS_COMPONENT,
            payload_model=PresentSuggestionsPayload,
        ),
    )
}
