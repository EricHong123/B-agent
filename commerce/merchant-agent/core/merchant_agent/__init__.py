# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The merchant agent's shared library. This root exports what an adopter's backend and
host code use: the domain types, ``MerchantBackend``, the config, the change ledger, and
the analysis-query check. The prompt, tool contracts, gates, and enrichment live in the
submodules.
"""

from .analysis import check_analysis_sql
from .backend import MerchantBackend
from .changes import ChangeLedger, ChangeNotApplicable, GuardrailViolation
from .config import MerchantAgentConfig
from .types import (
    ActorKind,
    AlertCounts,
    AnalysisFigure,
    AnalysisResult,
    AnalysisTable,
    BusinessSnapshot,
    Campaign,
    CampaignDraft,
    ChangeItem,
    ChangeKind,
    ChangeStatus,
    DataLimitation,
    InventoryActionItem,
    InventoryAlert,
    Listing,
    ListingDetails,
    ListingFilters,
    MerchantSessionContext,
    MerchantSessionState,
    MetricPoint,
    MetricSeries,
    OrderIssue,
    PriceUpdateItem,
    PricingContext,
    PromotionDraft,
    ReturnLog,
    ReturnReason,
    ReturnRecord,
    ReturnsSummary,
    StagedChange,
)

__all__ = [
    "ActorKind",
    "AlertCounts",
    "AnalysisFigure",
    "AnalysisResult",
    "AnalysisTable",
    "BusinessSnapshot",
    "Campaign",
    "CampaignDraft",
    "ChangeItem",
    "ChangeKind",
    "ChangeLedger",
    "ChangeNotApplicable",
    "ChangeStatus",
    "DataLimitation",
    "GuardrailViolation",
    "InventoryActionItem",
    "InventoryAlert",
    "Listing",
    "ListingDetails",
    "ListingFilters",
    "MerchantAgentConfig",
    "MerchantBackend",
    "MerchantSessionContext",
    "MerchantSessionState",
    "MetricPoint",
    "MetricSeries",
    "OrderIssue",
    "PriceUpdateItem",
    "PricingContext",
    "PromotionDraft",
    "ReturnLog",
    "ReturnReason",
    "ReturnRecord",
    "ReturnsSummary",
    "StagedChange",
    "check_analysis_sql",
]
