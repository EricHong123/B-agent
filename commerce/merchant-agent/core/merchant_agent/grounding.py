# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The merchant agent's grounding rules, in precedence order: a performance question
starts from get_business_snapshot, and an apply request with nothing staged this
session starts from get_pending_changes. :func:`change_requested` is the follow-through
gate's detector; the runtimes remind once when such a turn ends without a stage_* call.
"""

from __future__ import annotations

from typing import Any

from commerce_common.grounding import GroundingRule, matches_terms_and_cues

from .config import MerchantAgentConfig
from .types import MerchantSessionState


def change_requested(config: MerchantAgentConfig, text: str) -> bool:
    return (
        config.stages_changes
        and config.staging_followthrough_gate
        and matches_terms_and_cues(
            text, config.change_intent_terms, config.change_intent_cues, numeric_literals=True
        )
    )


def _metrics(
    config: MerchantAgentConfig, text: str, _: MerchantSessionState
) -> dict[str, Any] | None:
    fires = config.metrics_grounding_gate and matches_terms_and_cues(
        text, config.metrics_intent_terms, config.metrics_intent_cues
    )
    return {} if fires else None


def _queue(
    config: MerchantAgentConfig, text: str, state: MerchantSessionState
) -> dict[str, Any] | None:
    # The apply phrases match as substrings, so an inflection such as "applying" counts;
    # the terms and cues match whole words.
    lowered = text.lower()
    fires = (
        config.queue_grounding_gate
        and not state.seen_changes
        and change_requested(config, text)
        and any(phrase in lowered for phrase in config.apply_intent_phrases)
    )
    return {} if fires else None


GROUNDING_RULES: tuple[GroundingRule, ...] = (
    GroundingRule(
        "metrics",
        "get_business_snapshot",
        _metrics,
        prefetch_intro=lambda _: (
            "Business snapshot for this turn, fetched by the host (the same data a "
            "get_business_snapshot call returns):"
        ),
    ),
    GroundingRule(
        "queue",
        "get_pending_changes",
        _queue,
        prefetch_intro=lambda _: (
            "Pending approval queue for this turn, fetched by the host (the same data a "
            "get_pending_changes call returns):"
        ),
    ),
)
