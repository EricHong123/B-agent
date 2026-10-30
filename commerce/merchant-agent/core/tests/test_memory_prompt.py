# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

from merchant_agent.memory import MERCHANT_MEMORY_EXTRACTION_PROMPT


def test_prompt_keeps_customers_and_session_results_out_of_memory():
    for phrase in (
        "identifiable customer, guest, subscriber, or employee",
        "a figure this session computed",
    ):
        assert phrase in MERCHANT_MEMORY_EXTRACTION_PROMPT
