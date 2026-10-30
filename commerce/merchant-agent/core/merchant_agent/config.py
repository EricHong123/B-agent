# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Per-deployment settings for the merchant agent; per-request values travel in
``MerchantSessionContext``. Sections continue ``BaseAgentConfig``'s: capabilities
(analysis), guardrails, approval, grounding gates."""

from __future__ import annotations

import re

from pydantic import Field, field_validator

from commerce_common.config import BaseAgentConfig, ThinkingEffort


class MerchantAgentConfig(BaseAgentConfig):
    assistant_name: str = "the merchant assistant"
    brand_voice: str = "plain and specific, numbers first"
    model: str = "claude-opus-5"
    thinking_effort: ThinkingEffort | None = "low"

    # -- The analysis delegate. `analysis_model` None means the main model; the hosted
    # code-execution tool needs the first-party API; with a backend that supports
    # queries, `analysis_sql_only` leaves the per-series read tools off its surface.
    enable_analysis: bool = False
    analysis_model: str | None = None
    analysis_use_code_execution: bool = True
    analysis_sql_only: bool = True
    max_analysis_iterations: int = Field(default=8, ge=1)
    analysis_max_tokens: int = Field(default=4096, ge=256)
    analysis_timeout_s: float = Field(default=120.0, gt=0)
    max_delegate_calls_per_turn: int = Field(default=2, ge=1)
    # Applied to every query result, whatever size the backend returns.
    max_analysis_rows: int = Field(default=200, ge=1)
    max_analysis_table_chars: int = Field(default=8_000, ge=500)
    analysis_query_timeout_s: float = Field(default=10.0, gt=0)

    # -- Systems the store operates. Metrics and the catalog reads are the floor; each
    # switch below, turned off, removes that system's read and stage tools on every path,
    # for a business that has no such system at all. With every write switched off, the
    # change queue (get_pending_changes, apply_change, discard_change, the preview card)
    # goes too. A system that exists and is not wired yet stays on: its backend method
    # raises ChangeNotApplicable and the tool says so.
    enable_listing_edits: bool = True
    enable_inventory: bool = True
    enable_pricing: bool = True
    enable_campaigns: bool = True

    # -- Guardrails, checked when a change is staged and again before it is applied.
    # `price_bearing_fields` and `listing_update_blocked_fields` are extended, never
    # replaced, when a domain prices under another name. `max_items_per_change` counts
    # the lines the operator will approve, so a promotion on a family counts once per
    # variant it expands to.
    max_items_per_change: int = Field(default=25, ge=1)
    max_price_delta_pct: float = Field(default=20.0, gt=0)
    max_promotion_discount_pct: float = Field(default=50.0, gt=0, le=90)
    max_restock_quantity: int = Field(default=500, ge=1)
    max_campaign_budget: float = Field(default=10_000.0, gt=0)
    max_listing_field_chars: int = Field(default=2000, ge=200)
    protected_fields: tuple[str, ...] = (
        "listing_id",
        "currency",
        "tax_category",
        "compliance_notes",
    )
    price_bearing_fields: tuple[str, ...] = ("price",)
    listing_update_blocked_fields: tuple[str, ...] = ("price", "stock")
    # Copy staged into a listing or a campaign goes live once approved; text matching one
    # of these case-insensitive patterns (absolute and superlative claims, guarantees,
    # medical efficacy, unsourced statistics) is refused with the phrase named. Extended,
    # never replaced, by a domain with its own regulated terms.
    blocked_claim_patterns: tuple[str, ...] = (
        r"\bbest in the (?:world|market|industry|country)\b",
        r"\bworld'?s (?:best|first|only)\b",
        r"\bnumber one\b|#\s?1\b|\bno\.\s?1\b",
        r"\b100\s?% (?:safe|effective|guaranteed|natural|satisfaction)\b",
        r"\bguaranteed (?:results|to)\b|\brisk[- ]free\b|\bnever fails\b",
        r"\bcures?\b|\b(?:prevents|treats|heals) (?:disease|illness|infection|pain)\b",
        r"\b(?:clinically|scientifically|medically) proven\b|\bdoctor[- ]recommended\b",
        r"\bstudies show\b|\b\d{2,3}\s?% of (?:customers|users|people|experts)\b",
        r"最(?:好|佳|优|强)|(?:全网|全国|行业|销量)第一|顶级|国家级|万能",
        r"根治|治愈|100\s?%\s?有效|零风险|无副作用",
    )

    # -- Approval (prompt). With `require_host_approval` on, apply_change succeeds only
    # for ids the host marked on MerchantSessionState.approved_change_ids; a deployment
    # that trusts the conversational flow opts out. `approval_surface` names the host's
    # affordance in refusals and prompt guidance. With `stage_shows_preview` on, a
    # successful stage_* call renders the change preview card itself (prompt and tool
    # text say so); a deployment whose executor events do not reach the operator, the
    # MCP server, turns it off and the model shows the change with present_change_preview.
    # A change left unapproved for `staged_change_ttl_minutes` expires: approving it then
    # is refused and it is never applied.
    @field_validator("blocked_claim_patterns")
    @classmethod
    def _patterns_compile(cls, value: tuple[str, ...]) -> tuple[str, ...]:
        for pattern in value:
            try:
                re.compile(pattern)
            except re.error as error:
                raise ValueError(f"blocked_claim_patterns: {pattern!r}: {error}") from error
        return value

    require_host_approval: bool = True
    approval_surface: str = "the host application's approval control"
    stage_shows_preview: bool = True
    staged_change_ttl_minutes: int = Field(default=1440, ge=1)

    # -- Grounding gates (the runtimes read them). Metrics: a performance term plus a
    # question cue forces get_business_snapshot. Follow-through: a change term (or a
    # money or percent literal) plus an imperative cue marks the turn as a change
    # request, and a turn that would end without a stage_* attempt, on text or on its
    # chips, gets one reminder first; the cues exclude approval verbs so approving
    # staged work never re-fires it. Queue: a
    # change request that also carries an apply phrase, with nothing staged this
    # session, forces get_pending_changes.
    metrics_grounding_gate: bool = True
    metrics_intent_terms: tuple[str, ...] = (
        "sales",
        "revenue",
        "orders",
        "traffic",
        "conversion",
        "aov",
        "average order value",
        "performance",
        "performing",
        "trend",
        "trending",
        "growth",
        "drop",
        "dropped",
        "spike",
        "returns rate",
        "return rate",
        "margin",
        "margins",
        "profit",
        "best seller",
        "best sellers",
        "slow mover",
        "slow movers",
        "sell-through",
        "campaign performance",
        "ad spend",
        "return on ad spend",
        "roas",
    )
    metrics_intent_cues: tuple[str, ...] = (
        "?",
        "how",
        "what",
        "why",
        "show me",
        "compare",
        "summarize",
        "summary",
        "report",
        "this week",
        "last week",
        "this month",
        "last month",
        "yesterday",
        "today",
        "vs",
        "versus",
    )
    staging_followthrough_gate: bool = True
    change_intent_terms: tuple[str, ...] = (
        "price",
        "prices",
        "pricing",
        "reprice",
        "markdown",
        "mark down",
        "discount",
        "promotion",
        "promo",
        "rate",
        "nightly rate",
        "restock",
        "listing",
        "listings",
        "title",
        "titles",
        "description",
        "descriptions",
        "category",
        "copy",
    )
    change_intent_cues: tuple[str, ...] = (
        "take",
        "drop",
        "cut",
        "set",
        "lower",
        "raise",
        "reduce",
        "increase",
        "bump",
        "change",
        "update",
        "move",
        "stage",
        "bring down",
        "knock",
        "append",
        "rewrite",
        "revise",
        "add",
        "fix",
    )
    queue_grounding_gate: bool = True
    apply_intent_phrases: tuple[str, ...] = (
        "apply",
        "put it through",
        "put through",
        "push it through",
        "push through",
    )

    @property
    def stages_changes(self) -> bool:
        """Whether any stage_* tool remains for this deployment."""
        return (
            self.enable_listing_edits
            or self.enable_inventory
            or self.enable_pricing
            or self.enable_campaigns
        )

    def absent_tools(self) -> frozenset[str]:
        """Names `build_tools` leaves out for the systems switched off above."""
        names: set[str] = set()
        if not self.enable_listing_edits:
            names.add("stage_listing_update")
        if not self.enable_inventory:
            names |= {
                "get_inventory_alerts",
                "get_order_issues",
                "get_return_reasons",
                "stage_inventory_action",
            }
        if not self.enable_pricing:
            names |= {"get_pricing_context", "stage_price_update", "stage_promotion"}
        if not self.enable_campaigns:
            names |= {"get_campaign_performance", "stage_campaign"}
        if not self.stages_changes:
            names |= {
                "get_pending_changes",
                "apply_change",
                "discard_change",
                "present_change_preview",
            }
        return frozenset(names)
