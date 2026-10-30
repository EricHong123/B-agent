# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""``present_plan_comparison``: the side-by-side plan matrix. The model names the plans,
the dimensions, and the judgment (fit notes, a recommendation); every cell is filled here
from the catalog records the session has seen."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from commerce_common.presentation import EnrichmentContext, PresentationExtension

# Row labels by attribute key; an unknown key is labelled from the key itself.
_DIMENSION_LABELS: dict[str, str] = {
    "data_allowance_gb": "High-speed data",
    "hotspot_gb": "Hotspot data",
    "video_quality": "Video streaming",
    "intl_roaming": "International roaming",
    "contract_term": "Contract",
    "network_priority": "Network priority",
    "deprioritization_threshold_gb": "Full speed up to",
    "streaming_perk": "Streaming perk",
    "price_guarantee": "Price guarantee",
    "speed_tier": "Speed",
    "typical_download_mbps": "Typical download",
    "typical_latency_ms": "Typical latency",
    "data_cap": "Data cap",
    "equipment_fee": "Equipment fee",
    "install": "Installation",
}

_UNITS: dict[str, str] = {
    "data_allowance_gb": "GB",
    "hotspot_gb": "GB",
    "deprioritization_threshold_gb": "GB",
    "typical_download_mbps": "Mbps",
    "typical_latency_ms": "ms",
}

# Dimensions as the model tends to phrase them, mapped to attribute keys.
_ALIASES: dict[str, str] = {
    "data": "data_allowance_gb",
    "high_speed_data": "data_allowance_gb",
    "data_allowance": "data_allowance_gb",
    "allowance": "data_allowance_gb",
    "hotspot": "hotspot_gb",
    "hotspot_data": "hotspot_gb",
    "tethering": "hotspot_gb",
    "video": "video_quality",
    "video_streaming": "video_quality",
    "streaming": "streaming_perk",
    "streaming_perks": "streaming_perk",
    "perks": "streaming_perk",
    "roaming": "intl_roaming",
    "international": "intl_roaming",
    "international_roaming": "intl_roaming",
    "premium_data": "deprioritization_threshold_gb",
    "deprioritization": "deprioritization_threshold_gb",
    "priority": "network_priority",
    "contract": "contract_term",
    "price_lock": "price_guarantee",
    "guarantee": "price_guarantee",
    "speed": "speed_tier",
    "download": "typical_download_mbps",
    "latency": "typical_latency_ms",
    "equipment": "equipment_fee",
    "installation": "install",
}


def _normalize_key(raw: str) -> str:
    key = raw.strip().lower().replace("-", "_").replace(" ", "_")
    return _ALIASES.get(key, key)


class PlanAnnotation(BaseModel):
    plan_id: str
    best_for: str | None = Field(default=None, max_length=80)


class PlanMatrixPayload(BaseModel):
    title: str | None = Field(default=None, max_length=80)
    plan_ids: list[str] = Field(min_length=2, max_length=4)
    dimension_keys: list[str] = Field(default_factory=list, max_length=6)
    annotations: list[PlanAnnotation] = Field(default_factory=list, max_length=4)
    recommended_plan_id: str | None = None


# The JSON schema the model sees; the payload model above is what the executor enforces.
_INPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "title": {"type": "string", "maxLength": 80},
        "plan_ids": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 2,
            "maxItems": 4,
        },
        "dimension_keys": {
            "type": "array",
            "items": {"type": "string"},
            "maxItems": 6,
            "description": (
                "Attribute keys to compare, exactly as they appear in search results. "
                "Mobile plans: data_allowance_gb, hotspot_gb, video_quality, "
                "intl_roaming, network_priority, deprioritization_threshold_gb, "
                "streaming_perk, price_guarantee, contract_term. Home internet: "
                "speed_tier, typical_download_mbps, typical_latency_ms, data_cap, "
                "equipment_fee, install. Price is always shown — don't list it."
            ),
        },
        "annotations": {
            "type": "array",
            "maxItems": 4,
            "items": {
                "type": "object",
                "properties": {
                    "plan_id": {"type": "string"},
                    "best_for": {"type": "string", "maxLength": 80},
                },
                "required": ["plan_id"],
                "additionalProperties": False,
            },
        },
        "recommended_plan_id": {"type": "string"},
    },
    "required": ["plan_ids"],
    "additionalProperties": False,
}


def _format_value(key: str, raw: str | None) -> str:
    if raw is None or raw == "":
        return "—"
    value = raw.strip()
    unit = _UNITS.get(key)
    if unit and value.replace(".", "", 1).isdigit():
        if value in {"0", "0.0"}:
            return "None" if key == "hotspot_gb" else f"0 {unit}"
        return f"{value} {unit}"
    if value.lower() == "unlimited":
        return "Unlimited"
    if value.lower() == "none":
        return "—"
    return value


async def _enrich(payload: PlanMatrixPayload, context: EnrichmentContext) -> dict[str, Any]:
    plans = [
        context.state.seen_products[pid]
        for pid in payload.plan_ids
        if pid in context.state.seen_products
    ]
    if len(plans) < 2:
        raise ValueError(
            "A plan matrix needs at least 2 plan_ids that came from this session's "
            "catalog results. Search for plans first and pick from the results."
        )
    surviving_ids = {p.product_id for p in plans}

    rows: list[dict[str, Any]] = [
        {
            "key": "price",
            "label": "Price",
            "values": [
                f"${plan.price:g}/mo"
                if plan.attributes.get("price_unit") == "per_month"
                else f"${plan.price:g}"
                for plan in plans
            ],
        }
    ]
    seen_keys: set[str] = set()
    for raw_key in payload.dimension_keys:
        key = _normalize_key(raw_key)
        if key in {"price", "price_unit", "price_qualifier"} or key in seen_keys:
            continue
        seen_keys.add(key)
        values = [_format_value(key, plan.attributes.get(key)) for plan in plans]
        if all(value == "—" for value in values):
            continue
        rows.append(
            {
                "key": key,
                "label": _DIMENSION_LABELS.get(key, key.replace("_", " ").capitalize()),
                "values": values,
            }
        )

    annotations = [
        a.model_dump(exclude_none=True) for a in payload.annotations if a.plan_id in surviving_ids
    ]
    recommended = (
        payload.recommended_plan_id if payload.recommended_plan_id in surviving_ids else None
    )

    enriched: dict[str, Any] = {
        "plans": [plan.model_dump(exclude_none=True) for plan in plans],
        "rows": rows,
        "annotations": annotations,
    }
    if payload.title:
        enriched["title"] = payload.title
    if recommended:
        enriched["recommended_plan_id"] = recommended

    # A subscriber's own plan and usage let the columns show a price delta against
    # today's bill and a usage band; a prospect has neither.
    account = await context.backend.get_account_context(context.session) or {}
    current = account.get("current_plan")
    if isinstance(current, dict) and current.get("price_per_month") is not None:
        enriched["current_plan"] = {
            key: current.get(key)
            for key in ("product_id", "name", "price_per_month", "data_allowance_gb")
        }
    usage = account.get("recent_usage")
    if isinstance(usage, dict):
        enriched["account_usage"] = usage
    return enriched


def build_plan_matrix_extension() -> PresentationExtension:
    return PresentationExtension(
        name="present_plan_comparison",
        component="plan_matrix",
        description=(
            "Show a side-by-side feature matrix of 2-4 service plans (mobile or home "
            "internet). Use for plan-vs-plan decisions; for devices use "
            "present_comparison instead. Pass plan product_ids from this session's "
            "search results and the attribute keys to compare — the UI fills in every "
            "price and feature value from the catalog. You may add a short 'best for' "
            "note per plan and recommend one."
        ),
        input_schema=_INPUT_SCHEMA,
        payload_model=PlanMatrixPayload,
        enrich=_enrich,
    )
