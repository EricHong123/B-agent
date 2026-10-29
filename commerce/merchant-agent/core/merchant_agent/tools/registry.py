# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The merchant agent's tool contracts, in a fixed order. The list depends only on the
deployment config, so it is the same bytes on every request; whether a capability can
serve a call is decided in the executor. A description covers one tool; the staged-change
contract that spans tools lives in the prompt, and the operating flows in skills."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from commerce_common.delegation import DelegateExtension
from commerce_common.execution import LOAD_SKILL, with_status
from commerce_common.presentation import PresentationExtension

from ..analysis import build_analysis_tool_definition
from ..config import MerchantAgentConfig

_STATUS_READER = "the operator"

_SESSION_LISTING_ID = "listing_id that search_listings or get_listing returned this session."
_ISO_DATE = "ISO date (YYYY-MM-DD)."


def _listing_id(role: str = _SESSION_LISTING_ID) -> dict[str, Any]:
    return {"type": "string", "description": role}


def _change_id() -> dict[str, Any]:
    return {
        "type": "string",
        "description": "change_id staged this conversation or listed by get_pending_changes.",
    }


def _note(what: str) -> dict[str, Any]:
    return {"type": "string", "maxLength": 200, "description": what}


def _title(what: str) -> dict[str, Any]:
    return {"type": "string", "maxLength": 80, "description": f"Short heading for the {what}."}


def _listing_filters_schema() -> dict[str, Any]:
    return {
        "type": "object",
        "description": "Constraints the operator stated; with an empty query they scan everything.",
        "properties": {
            "status": {
                "type": "string",
                "enum": ["active", "paused", "draft", "out_of_stock"],
                "description": "Listing status to match.",
            },
            "category": {"type": "string", "description": "Catalog category name."},
            "max_stock": {
                "type": "integer",
                "minimum": 0,
                "description": "Only listings at or below this stock level.",
            },
            "content_quality": {
                "type": "string",
                "enum": ["good", "needs_work", "poor"],
                "description": "Content-quality flag to match; needs_work or poor for audits.",
            },
            "sort": {
                "type": "string",
                "enum": ["relevance", "sales_desc", "stock_asc", "price_desc", "price_asc"],
                "description": "Result order; relevance when omitted.",
            },
        },
        "additionalProperties": False,
    }


# Paths that send no per-request Merchant context block (the Agent SDK toolset and the MCP
# server) drop the reference to it from recall's description.
INLINE_CONTEXT_DESCRIPTIONS: dict[str, str] = {
    "recall_memories": (
        "Search the store's saved memory for facts (older rules, seasonal notes, past "
        "goals). Use only when something older or more specific would change your "
        "recommendation."
    ),
}


def build_tools(
    config: MerchantAgentConfig,
    skill_names: list[str],
    extra_presentation_tools: Sequence[PresentationExtension] = (),
    extra_delegates: Sequence[DelegateExtension] = (),
) -> list[dict[str, Any]]:
    """The tool list for one deployment: built-ins in a fixed order, less the systems the
    config switches off, run_analysis when ``config.enable_analysis`` is on, then the
    deployment's presentation extensions and delegates in the order given, then web
    search when enabled. Every tool but the presentation tools and web search takes the
    optional ``status`` line first."""

    # The turns with no other present_* call. With stage_shows_preview on, a fresh
    # staging's chips ride in the round after the stage call, beside its one sentence.
    chips_alone_cases = "a clarifying question, a listing read-back"
    if config.stages_changes:
        chips_alone_cases = "a guardrail explanation, " + chips_alone_cases
        if config.stage_shows_preview:
            chips_alone_cases += ", the sentence after a staging"

    tools: list[dict[str, Any]] = [
        {
            "name": LOAD_SKILL,
            "description": (
                "Load a skill's full instructions when the request matches its entry in "
                "the skill index; then follow them for the rest of the flow."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "skill_name": {
                        "type": "string",
                        "enum": sorted(skill_names),
                        "description": "Name of the skill as listed in the index.",
                    },
                },
                "required": ["skill_name"],
                "additionalProperties": False,
            },
        },
        # -- Performance reads ---------------------------------------------------
        {
            "name": "get_business_snapshot",
            "description": (
                "Headline figures for a period: sales, orders, traffic, conversion, average "
                "order value, the change against the prior period, and alert counts. Call it "
                "first for any question about how the business is doing."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": (
                            "Reporting period, e.g. last_7_days, last_30_days, or an ISO range."
                        ),
                    },
                },
                "additionalProperties": False,
            },
        },
        {
            "name": "query_metrics",
            "description": (
                "One metric over time, optionally narrowed to a segment (a category, a "
                "listing, a channel). Use after the snapshot for a trend, a breakdown, a "
                "comparable, or the explanation of a movement."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "metric": {
                        "type": "string",
                        "description": "Metric name as the snapshot or a series spells it.",
                    },
                    "period": {
                        "type": "string",
                        "description": "Reporting period, as for the snapshot; its default when omitted.",
                    },
                    "granularity": {
                        "type": "string",
                        "enum": ["day", "week", "month"],
                        "description": "Bucket size for the series; day when omitted.",
                    },
                    "segment": {
                        "type": "string",
                        "description": "Segment to narrow to; omit for the whole operation.",
                    },
                },
                "required": ["metric"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_campaign_performance",
            "description": (
                "Campaigns with budget, spend, revenue, and status; all of them, or one by "
                "campaign_id. Use before judging or changing any campaign."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "campaign_id": {
                        "type": "string",
                        "description": "One campaign to return; omit for all.",
                    },
                },
                "additionalProperties": False,
            },
        },
        # -- Catalog reads ---------------------------------------------------------
        {
            "name": "search_listings",
            "description": (
                "Search the listings; returns id, title, status, price, stock, and the "
                "content-quality flag. Use a specific query to find something, or an empty "
                "query with filters to sweep the whole catalog for an audit."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": 'Text to match, or "" to browse everything.',
                    },
                    "filters": _listing_filters_schema(),
                    "limit": {
                        "type": "integer",
                        "minimum": 1,
                        "maximum": config.max_search_results,
                        "description": "Maximum rows to return.",
                    },
                },
                "required": ["query"],
                "additionalProperties": False,
            },
        },
        {
            "name": "get_listing",
            "description": (
                "The full record for one listing: content, attributes, review snippets, "
                "sales, return rate, and for a listing with options, its variants with their "
                "ids, prices, and stock. Read it before reporting on, editing, repricing, or "
                "restocking a listing; a search row is an excerpt, not the record."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"listing_id": _listing_id("listing_id to fetch.")},
                "required": ["listing_id"],
                "additionalProperties": False,
            },
        },
        # -- Inventory and order health --------------------------------------------
        {
            "name": "get_inventory_alerts",
            "description": (
                "Current low-stock and slow-mover alerts with stock levels and recent sales. "
                "Use for the daily briefing and before staging a restock."
            ),
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "get_order_issues",
            "description": (
                "Open order exceptions: delays, return spikes, and buyer messages awaiting "
                "attention, each with a short excerpt."
            ),
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        {
            "name": "get_return_reasons",
            "description": (
                "Returns over a period, counted per listing and by reason code, with the "
                "stage each reason usually points at and a few buyer notes per listing. Use "
                "it for which listings are coming back and why; the counts and shares are "
                "computed, so quote them as returned."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "period": {
                        "type": "string",
                        "description": (
                            "Reporting period, as for the snapshot; last_30_days when omitted."
                        ),
                    },
                    "listing_id": _listing_id(
                        "One listing to narrow to, a family with its variants; omit for all."
                    ),
                },
                "additionalProperties": False,
            },
        },
        # -- Pricing reads -----------------------------------------------------------
        {
            "name": "get_pricing_context",
            "description": (
                "Price, cost and margin, allowed range, movement caps (max_price_delta_pct "
                "for permanent moves, max_promotion_discount_pct for promotions), and demand "
                "signal for one listing or variant; a listing with options adds a row per "
                "variant. Read it before proposing any price; a move is allowed only inside "
                "the range and both caps, and a refusal names each limit the move breaks."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"listing_id": _listing_id("listing_id or variant id to price.")},
                "required": ["listing_id"],
                "additionalProperties": False,
            },
        },
        # -- Approval queue ----------------------------------------------------------
        {
            "name": "get_pending_changes",
            "description": (
                "Changes staged and not yet applied or discarded. Check it before staging, "
                "so a change already waiting is pointed out instead of staged again."
            ),
            "input_schema": {"type": "object", "properties": {}, "additionalProperties": False},
        },
        # -- Staged writes -------------------------------------------------------------
        {
            "name": "stage_listing_update",
            "description": (
                "Stage edits to one listing's content or attributes (title, description, "
                "attributes, category). Returns the staged change; the live listing is "
                "untouched."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "listing_id": _listing_id(),
                    "fields": {
                        "type": "object",
                        "description": 'Field name to new value, e.g. {"title": "..."}.',
                        "additionalProperties": {"type": ["string", "number"]},
                    },
                    "note": _note("One sentence on why the edit is right; shown on the card."),
                },
                "required": ["listing_id", "fields"],
                "additionalProperties": False,
            },
        },
        {
            "name": "stage_price_update",
            "description": (
                "Stage a permanent price change for one or more listings or variants, priced "
                "from get_pricing_context; a listing with options is repriced by variant id, "
                "one item each. The staged change comes back with the backend's before and "
                "after margins and margin impact."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": config.max_items_per_change,
                        "description": "Listings or variants to reprice, one entry each.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "listing_id": _listing_id("listing_id, or a variant's id."),
                                "new_price": {
                                    "type": "number",
                                    "exclusiveMinimum": 0,
                                    "description": "New price in the listing's currency.",
                                },
                            },
                            "required": ["listing_id", "new_price"],
                            "additionalProperties": False,
                        },
                    },
                    "note": _note("One sentence on the goal and any assumption made."),
                },
                "required": ["items"],
                "additionalProperties": False,
            },
        },
        {
            "name": "stage_inventory_action",
            "description": (
                "Stage a restock, a pause, or a reactivation for one or more listings. A "
                "restock carries the quantity to add, names the variant on a listing with "
                "options, and is also how held-back stock (a hold, a block) goes on sale; a "
                "quantity past what is releasable comes back refused with the balances."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": config.max_items_per_change,
                        "description": "Listings or variants to act on, one entry each.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "listing_id": _listing_id("listing_id, or a variant's id."),
                                "action": {
                                    "type": "string",
                                    "enum": ["restock", "pause", "activate"],
                                    "description": "What to do with the listing.",
                                },
                                "quantity": {
                                    "type": "integer",
                                    "minimum": 0,
                                    "description": "Units to add; restock only.",
                                },
                            },
                            "required": ["listing_id", "action"],
                            "additionalProperties": False,
                        },
                    },
                    "note": _note("One sentence on the reasoning, figures from the alert."),
                },
                "required": ["items"],
                "additionalProperties": False,
            },
        },
        {
            "name": "stage_promotion",
            "description": (
                "Stage a date-bound price move for a set of listings; every promotion has "
                "an end date. Use it for any move limited to particular dates, a rate "
                "increase included."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "name": {
                        "type": "string",
                        "maxLength": 80,
                        "description": "Name the operator will recognize in the queue.",
                    },
                    "listing_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": config.max_items_per_change,
                        "minItems": 1,
                        "description": "Listings in scope, from a catalog read this session.",
                    },
                    "discount_pct": {
                        "type": "number",
                        "minimum": -90,
                        "maximum": 90,
                        "description": "Percent off for the window; negative raises the price.",
                    },
                    "starts": {"type": "string", "description": f"First day, {_ISO_DATE}"},
                    "ends": {"type": "string", "description": f"Last day, {_ISO_DATE}"},
                    "nights": {
                        "type": "array",
                        "items": {
                            "type": "string",
                            "enum": ["mon", "tue", "wed", "thu", "fri", "sat", "sun"],
                        },
                        "description": "Limit the move to these nights of the week.",
                    },
                },
                "required": ["name", "listing_ids", "discount_pct", "starts", "ends"],
                "additionalProperties": False,
            },
        },
        {
            "name": "stage_campaign",
            "description": (
                "Stage a campaign draft (name, objective, audience, budget, copy, dates), or "
                "a budget or copy change to an existing campaign_id."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "campaign_id": {
                        "type": "string",
                        "description": "Existing campaign to change; omit for a new draft.",
                    },
                    "name": {
                        "type": "string",
                        "maxLength": 80,
                        "description": "Campaign name.",
                    },
                    "objective": {
                        "type": "string",
                        "maxLength": 200,
                        "description": "The one measurable the campaign should move.",
                    },
                    "audience": {
                        "type": "string",
                        "maxLength": 300,
                        "description": "Who it should reach, written as intent.",
                    },
                    "budget": {
                        "type": "number",
                        "minimum": 0,
                        "description": "Total budget in the store's currency.",
                    },
                    "copy_text": {
                        "type": "string",
                        "maxLength": 600,
                        "description": "The draft copy, facts from the listing records.",
                    },
                    "starts": {"type": "string", "description": f"First day, {_ISO_DATE}"},
                    "ends": {"type": "string", "description": f"Last day, {_ISO_DATE}"},
                },
                "required": ["name"],
                "additionalProperties": False,
            },
        },
        {
            "name": "apply_change",
            "description": (
                "Apply one staged change the operator has approved on the approval surface "
                "your instructions name. The only call that touches live state."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"change_id": _change_id()},
                "required": ["change_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "discard_change",
            "description": (
                "Discard a staged change the operator decided against or moved on from, and "
                "say so; do not argue for applying it instead."
            ),
            "input_schema": {
                "type": "object",
                "properties": {"change_id": _change_id()},
                "required": ["change_id"],
                "additionalProperties": False,
            },
        },
        # -- Memory --------------------------------------------------------------------
        {
            "name": "save_memory",
            "description": (
                "Save a fact about the store or how to run it (brand voice, pricing rules, "
                "goals, seasonal patterns) when the operator asks you to remember it. Never "
                "save listing, review, message, or metric text."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "key": {
                        "type": "string",
                        "maxLength": 64,
                        "description": "Topic key; reuse an existing key to replace its value.",
                    },
                    "value": {
                        "type": "string",
                        "maxLength": 200,
                        "description": "The fact, worded to stand on its own later.",
                    },
                    "category": {
                        "type": "string",
                        "enum": ["preference", "constraint", "context"],
                        "description": "constraint for a rule to respect; else preference/context.",
                    },
                },
                "required": ["key", "value"],
                "additionalProperties": False,
            },
        },
        {
            "name": "recall_memories",
            "description": (
                "Search the store's saved facts that are not in the Merchant context block: "
                "brand voice, pricing rules, seasonal notes, stated goals. Use it when such a "
                "fact would change what you write or recommend."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "topic": {
                        "type": "string",
                        "maxLength": 100,
                        "description": "Topic to search for, in a few words.",
                    },
                },
                "required": ["topic"],
                "additionalProperties": False,
            },
        },
    ]
    presentation: list[dict[str, Any]] = [
        {
            "name": "present_metrics",
            "description": (
                "Show measures the tools returned as tiles and trend lines; the portal fills "
                "in the values. Name each pick as the tool spelled it, or as a campaign id "
                "plus one measure ('<campaign_id> spend', revenue, budget, or roas)."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": _title("card"),
                    "period": {
                        "type": "string",
                        "maxLength": 80,
                        "description": "Period the figures cover, as queried.",
                    },
                    "picks": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "description": "Measures to show, takeaway first.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "metric": {
                                    "type": "string",
                                    "maxLength": 60,
                                    "description": "Measure name as a tool returned it.",
                                },
                                "note": {
                                    "type": "string",
                                    "maxLength": 140,
                                    "description": "One clause on why this measure matters.",
                                },
                            },
                            "required": ["metric"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["picks"],
                "additionalProperties": False,
            },
        },
        {
            "name": "present_digest",
            "description": (
                "Show the needs-attention digest: alerts, order issues, metric movements, "
                "and pending changes, ranked, each with why it matters. Use it when the "
                "operator asks for a briefing or what needs attention; refer to items by "
                "their ids."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "title": _title("digest"),
                    "items": {
                        "type": "array",
                        "minItems": 1,
                        "maxItems": 8,
                        "description": "Entries in priority order.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "kind": {
                                    "type": "string",
                                    "enum": [
                                        "low_stock",
                                        "slow_mover",
                                        "order_issue",
                                        "metric",
                                        "pending_change",
                                        "note",
                                    ],
                                    "description": "Entry type; note for a closing summary line.",
                                },
                                "ref_id": {
                                    "type": "string",
                                    "maxLength": 64,
                                    "description": "Id of the listing, issue, or change concerned.",
                                },
                                "headline": {
                                    "type": "string",
                                    "maxLength": 120,
                                    "description": "What is wrong, with the payload's figure.",
                                },
                                "why_it_matters": {
                                    "type": "string",
                                    "maxLength": 160,
                                    "description": "Cost or deadline, and the next action.",
                                },
                            },
                            "required": ["kind", "headline"],
                            "additionalProperties": False,
                        },
                    },
                },
                "required": ["items"],
                "additionalProperties": False,
            },
        },
        {
            "name": "present_change_preview",
            "description": (
                "Show the before-and-after card for a change staged or returned by "
                "get_pending_changes earlier in the session; the portal fills in the diff, "
                "guardrail notes, and margin impact. A stage call shows this card itself; do "
                "not call it for a change staged this turn."
                if config.stage_shows_preview
                else "Show the before-and-after card for one staged change; the portal fills "
                "in the diff, guardrail notes, and margin impact. Show every staged change "
                "with it before anything is applied."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "change_id": _change_id(),
                    "headline": {
                        "type": "string",
                        "maxLength": 120,
                        "description": "What the change does, in one line.",
                    },
                    "note": _note("One sentence on why it is safe or worth making."),
                },
                "required": ["change_id"],
                "additionalProperties": False,
            },
        },
        {
            "name": "present_suggestions",
            "description": (
                "Give the turn its 1-4 chips; it ends the reply. Call it in the same round "
                "as the turn's last present_* call, without waiting for that call's result. "
                "Alone, after the text, only on a turn with no other present_* call "
                f"({chips_alone_cases})."
            ),
            "input_schema": {
                "type": "object",
                "properties": {
                    "suggestions": {
                        "type": "array",
                        "items": {"type": "string"},
                        "minItems": 1,
                        "maxItems": 4,
                        "description": (
                            "1-4 chips, each a brief imperative that takes the work a step "
                            "further; leave out anything this turn already showed."
                        ),
                    },
                },
                "required": ["suggestions"],
                "additionalProperties": False,
            },
        },
    ]

    absent = config.absent_tools()
    tools = [with_status(tool, _STATUS_READER) for tool in tools if tool["name"] not in absent]
    tools += [tool for tool in presentation if tool["name"] not in absent]

    if config.enable_analysis:
        tools.append(with_status(build_analysis_tool_definition(), _STATUS_READER))

    base_names = {tool["name"] for tool in tools}
    for extension in extra_presentation_tools:
        if extension.name in base_names:
            raise ValueError(
                f"presentation extension {extension.name!r} collides with a built-in tool"
            )
        base_names.add(extension.name)
        tools.append(extension.tool_definition())

    for delegate in extra_delegates:
        if delegate.name in base_names:
            raise ValueError(
                f"delegate extension {delegate.name!r} collides with a registered tool"
            )
        base_names.add(delegate.name)
        tools.append(with_status(delegate.tool_definition(), _STATUS_READER))

    if config.enable_web_search:
        tools.append(
            {
                # Pinned; newer web_search versions exist, so re-run evals before moving.
                "type": "web_search_20250305",
                "name": "web_search",
                "max_uses": 3,
            }
        )

    return tools
