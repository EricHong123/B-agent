# ADR 0004: Vendor the commerce agents and host them behind B-agent adapters

- Status: Accepted for implementation
- Date: 2026-10-29

## Context

B-agent needed a buyer-facing assistant (sourcing, comparison, trade-term answers, an RFQ
basket, order questions) and a back-office assistant (performance insights, listing
upkeep, inventory, pricing and promotions, campaigns). The commerce-agents reference
(Apache-2.0) already defines both roles: prompts, five skills each, tool contracts,
fencing, provenance gates, versioned-terms gating, staged writes with guardrails, expiry,
drift checks and host approval, an operations log, and two evaluations. It runs on the
Messages API, the Agent SDK and Managed Agents, with four consumer verticals as examples.

Rewriting those mechanisms on B-agent's own Agent Runtime would take several releases and
would drift from a suite of more than a thousand tests.

## Decision

- Vendor the reference unchanged under `commerce/` at a recorded commit, with its license,
  tests, verticals, runtimes and Claude Code plugin. `commerce/` is never edited in place;
  a new upstream commit replaces it whole and its own CI job keeps it green.
- Install its five library packages (`commerce-common`, the shopping and merchant cores
  and their Messages API runtimes) into the backend from the local paths, together, so the
  exact sibling pins never resolve against the public package index.
- Implement `StorefrontBackend` and `MerchantBackend` in `backend/app/commerce/` over
  B-agent's tables: a B2B catalog with variants, MOQ and lead time; versioned trade terms;
  campaigns and promotions; fulfillment orders; and a durable staged-change ledger with
  the reference's guardrail, expiry and drift semantics.
- The buyer basket is a request for quotation. Submitting it creates an opportunity and a
  draft quotation in the fulfillment pipeline; nothing is priced, sent or charged without
  the existing quotation gates.
- Buyers reach the assistant through revocable portal invites (`X-Buyer-Token`) or through
  a signed-in rep acting for a named customer. Operations sessions are staff-only, and a
  staged change is applied only from the console by an operator or admin.
- The model client follows B-agent's AI routing (explicit commerce endpoint, OmniRoute,
  Anthropic, or the configured direct provider) through the reference's
  OpenAI-compatible client.
- Operations records use the reference's record format in `commerce_operation_events`, so
  `commerce/scripts/metrics_report.py` computes the same metrics; the go-live and
  constraint evaluations run unchanged against a `bagent` vertical.

## Consequences

- The assistants keep every gate the reference enforces in code, on any model.
- Commerce turns bypass `LLMService`'s invocation audit and OmniRoute's post-response
  provider check; OmniRoute's own allow-list still applies. Bringing commerce turns under
  `LLMService` is follow-up work.
- The Agent SDK and Managed Agents runtimes, the MCP servers and the verticals run from
  `commerce/` against their own mock backends, not against B-agent data.
- Upgrading the reference is a directory replacement plus the adapter contract tests in
  `backend/tests/test_commerce_*.py`.
