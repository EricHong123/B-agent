# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The extraction prompt the merchant runtimes hand to ``commerce_common.memory``: what
the assistant may remember about one operation between sessions, keyed by merchant id."""

from __future__ import annotations

from commerce_common.memory import MEMORY_EXTRACTION_TEMPLATE

MERCHANT_MEMORY_EXTRACTION_PROMPT = MEMORY_EXTRACTION_TEMPLATE.format(
    keeper="an assistant",
    subject="one operation (a store, a property, a subscriber base, a venue)",
    occasions="sessions with its operator",
    speaker="the operator",
    qualifies=(
        "something the operator stated about the operation or how they want it run: the voice "
        "their listings are written in, a margin they will not go under, a rate floor for "
        "certain dates, a plan they do not discount, a target, a seasonal pattern, a "
        "supplier's lead time, how they like the briefing laid out."
    ),
    standalone_example=(
        '"not under 30" tells a future reader nothing, while "wants every listing to clear a '
        '30 percent margin" tells them everything'
    ),
    live_key_rule=(
        'Keep the operation\'s one live goal as a single fact under the key "current_goal", '
        "naming what the operator is driving toward and by when; a new goal replaces it."
    ),
    excluded=(
        "anything that came from listings, reviews, buyer or guest messages, metrics, or "
        "search results; a figure this session computed; the mechanics of this session; your "
        "own guesses; and anything about an identifiable customer, guest, subscriber, or "
        "employee."
    ),
)
