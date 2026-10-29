# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""``present_itinerary``: the day-by-day trip card. The model supplies the day labels,
notes, and product ids; the ids resolve to the records this session has seen, and a
rendered plan also records the trip's night structure on the backend for later cart
adds."""

from __future__ import annotations

import re
from datetime import date, timedelta
from typing import Any

from pydantic import BaseModel, Field

from commerce_common.presentation import EnrichmentContext, PresentationExtension
from shopping_agent import ShoppingSessionState

from .mock_travel import cancellation_deadline


class ItineraryDay(BaseModel):
    label: str = Field(max_length=80)
    note: str | None = Field(default=None, max_length=280)
    product_ids: list[str] = Field(default_factory=list, max_length=6)


class ItineraryPayload(BaseModel):
    title: str = Field(max_length=80)
    days: list[ItineraryDay] = Field(min_length=1, max_length=10)
    travel_dates: str | None = Field(default=None, max_length=60)


# The JSON schema the model sees; the payload model above is what the executor enforces.
_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "maxLength": 80},
        "days": {
            "type": "array",
            "minItems": 1,
            "maxItems": 10,
            "items": {
                "type": "object",
                "properties": {
                    "label": {"type": "string", "maxLength": 80},
                    "note": {"type": "string", "maxLength": 280},
                    "product_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 6,
                    },
                },
                "required": ["label"],
                "additionalProperties": False,
            },
        },
        "travel_dates": {"type": "string", "maxLength": 60},
    },
    "required": ["title", "days"],
    "additionalProperties": False,
}


# "Day N" labels carry the plan's structure; the free-text travel_dates is the fallback
# ("2026-10-15 to 2026-10-18", "Thu 15 Oct — Sun 18 Oct", "October 15–18").
_DAY_NUMBER = re.compile(r"day\s+(\d+)", re.IGNORECASE)
_ISO_DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
_DAY_PAIR = re.compile(r"(\d{1,2})(?:\s+[A-Za-z]+)?\s*[–—-]\s*(?:[A-Za-z]+\s+)*(\d{1,2})")
_MONTH_NAMES = "jan|feb|mar|apr|may|jun|jul|aug|sep|oct|nov|dec"
_MONTH_DAY = re.compile(
    rf"\b(?:({_MONTH_NAMES})[a-z]*\.?\s+(\d{{1,2}})|(\d{{1,2}})\s+({_MONTH_NAMES})[a-z]*)\b",
    re.IGNORECASE,
)
_MONTHS = {name: i for i, name in enumerate(_MONTH_NAMES.split("|"), start=1)}


def _parse_trip_start(travel_dates: str | None) -> date | None:
    if not travel_dates:
        return None
    iso = _ISO_DATE.search(travel_dates)
    if iso:
        try:
            return date.fromisoformat(iso.group(0))
        except ValueError:
            return None
    for match in _MONTH_DAY.finditer(travel_dates):
        month = _MONTHS[(match.group(1) or match.group(4)).lower()[:3]]
        today = date.today()
        try:
            start = date(today.year, month, int(match.group(2) or match.group(3)))
            # A date well past this year means next year's occurrence.
            return start if (today - start).days <= 30 else start.replace(year=today.year + 1)
        except ValueError:
            continue
    return None


def _parse_trip_nights(travel_dates: str | None) -> int | None:
    if not travel_dates:
        return None
    iso = _ISO_DATE.findall(travel_dates)
    if len(iso) >= 2:
        try:
            nights = (date.fromisoformat(iso[1]) - date.fromisoformat(iso[0])).days
        except ValueError:
            return None
        return nights if 0 < nights <= 30 else None
    pair = _DAY_PAIR.search(travel_dates)
    if pair:
        nights = int(pair.group(2)) - int(pair.group(1))
        return nights if 0 < nights <= 30 else None
    return None


def _plan_structure(
    days: list[dict[str, Any]], travel_dates: str | None
) -> tuple[int | None, dict[str, int], list[int], dict[str, int]]:
    """The trip's span in nights and each stay's nights. Stays introduced on the same day
    are alternatives; stays starting on different days split the trip between them."""
    parsed = [
        int(m.group(1)) if (m := _DAY_NUMBER.search(day["label"])) else i + 1
        for i, day in enumerate(days)
    ]
    span = max(parsed) - min(parsed) if len(parsed) >= 2 else 0
    trip_nights = span if span > 0 else _parse_trip_nights(travel_dates)

    stay_starts: dict[str, int] = {}
    for i, day in enumerate(days):
        for product in day["products"]:
            attributes = product.get("attributes") or {}
            if (
                attributes.get("price_unit") == "per_night"
                and product["product_id"] not in stay_starts
            ):
                stay_starts[product["product_id"]] = parsed[i]
    group_starts = sorted(set(stay_starts.values()))
    last_day = max(parsed) if parsed else 0
    stay_nights: dict[str, int] = {}
    for index, start in enumerate(group_starts):
        structural = (
            group_starts[index + 1] - start if index + 1 < len(group_starts) else last_day - start
        )
        nights = (
            structural if structural > 0 else (trip_nights or 0) if len(group_starts) == 1 else 0
        )
        if nights > 0:
            stay_nights |= {pid: nights for pid, s in stay_starts.items() if s == start}
    return trip_nights, stay_nights, parsed, stay_starts


async def _enrich(payload: ItineraryPayload, context: EnrichmentContext) -> dict[str, Any]:
    enriched = payload.model_dump(exclude_none=True)
    days: list[dict[str, Any]] = []
    for day in payload.days:
        products = [
            context.state.seen_products[pid].model_dump(exclude_none=True)
            for pid in day.product_ids
            if pid in context.state.seen_products
        ]
        entry: dict[str, Any] = {"label": day.label, "products": products}
        if day.note:
            entry["note"] = day.note
        days.append(entry)
    enriched["days"] = days

    trip_nights, stay_nights, parsed_days, stay_start_days = _plan_structure(
        days, payload.travel_dates
    )
    note_trip_plan = getattr(context.backend, "note_trip_plan", None)
    if note_trip_plan is not None and (trip_nights or stay_nights):
        note_trip_plan(context.session.session_id, trip_nights=trip_nights, stay_nights=stay_nights)

    trip_start = _parse_trip_start(payload.travel_dates)
    if trip_start is not None and parsed_days:
        first_day = min(parsed_days)
        # A stay's cutoff counts from its check-in day wherever else the plan mentions it.
        for i, day in enumerate(days):
            for product in day["products"]:
                attributes = product.get("attributes")
                if not attributes or attributes.get("refundable") != "yes":
                    continue
                start_day = (
                    stay_start_days.get(product["product_id"], parsed_days[i])
                    if attributes.get("price_unit") == "per_night"
                    else parsed_days[i]
                )
                attributes["free_cancellation_until"] = cancellation_deadline(
                    product.get("category"), trip_start + timedelta(days=start_day - first_day)
                )
    return enriched


def _enrich_partial(data: dict[str, Any], state: ShoppingSessionState) -> dict[str, Any] | None:
    """The streamed prefix of a still-generating call, under the same provenance rule;
    the final ``ui`` event replaces it."""
    days: list[dict[str, Any]] = []
    for day in data.get("days") or []:
        if not isinstance(day, dict) or not day.get("label"):
            continue
        products = [
            state.seen_products[pid].model_dump(exclude_none=True)
            for pid in day.get("product_ids") or []
            if isinstance(pid, str) and pid in state.seen_products
        ]
        entry: dict[str, Any] = {"label": day["label"], "products": products}
        if day.get("note"):
            entry["note"] = day["note"]
        days.append(entry)
    if not days:
        return None
    payload: dict[str, Any] = {"title": data.get("title") or "", "days": days}
    if data.get("travel_dates"):
        payload["travel_dates"] = data["travel_dates"]
    return payload


def build_itinerary_extension() -> PresentationExtension:
    return PresentationExtension(
        name="present_itinerary",
        component="itinerary",
        description=(
            "Show a day-by-day itinerary for the trip being planned, with the stays, "
            "flights, and experiences attached to each day (e.g. 'Day 1 — Arrive in "
            "Lisbon'). Use when the user is planning a multi-day trip; pass product_ids "
            "from this session's search results — the UI fills in titles and prices "
            "from the catalog."
        ),
        input_schema=_INPUT_SCHEMA,
        payload_model=ItineraryPayload,
        enrich=_enrich,
        enrich_partial=_enrich_partial,
    )
