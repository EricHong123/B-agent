---
name: commerce-merchant-operations
description: The reference merchant agent, covering its flows, staged changes and host approval, metrics grounding, the analysis delegate, store memory, components, and marketplace rules. Load when building or reviewing an agent for the operators of a store, property, subscriber base, or venue.
---

# Merchant agent

Paths are in the reference repo: `merchant_agent/` is `merchant-agent/core/merchant_agent/`, `merchant_agent_runtime/`
is `merchant-agent/runtime-messages-api/merchant_agent_runtime/`, `merchant_agent_sdk/` is
`merchant-agent/runtime-agent-sdk/merchant_agent_sdk/`, `commerce_common/` is `commerce-common/commerce_common/`.

## What it does

The merchant agent works with an operator inside their back office over one `MerchantBackend` (`merchant_agent/backend.py`).
Its five flows are the skills in `merchant-agent/skills/`: performance-insights, catalog-listings, inventory-operations,
pricing-promotions, marketing-campaigns. The mechanisms in `commerce_common/` are shared; the prompt, tools, gates, and
executor are its own, and every tool result comes back inside `MERCHANT_FENCE` (`merchant_agent/fencing.py`).

## The staged-change contract

1. Every write is a `stage_*` tool (`stage_listing_update`, `stage_price_update`, `stage_inventory_action`, `stage_promotion`,
   `stage_campaign`). Each returns the staged record and a note, emits a `change_update` event, and, with
   `stage_shows_preview` on (the default, `merchant_agent/config.py`), emits the `change_preview` card through the runner
   `present_change_preview` uses (`MerchantToolExecutor`, `merchant_agent/executor.py`). The MCP server turns it off
   because its executor events do not reach the operator, so the hosted agent calls `present_change_preview`; that tool
   also shows an earlier change again. Live state is untouched until `apply_change`, which performs the platform write.
2. Staging accepts only listing and campaign ids that tools returned this session, and a content edit also needs a
   `get_listing` read; `apply_change` and `discard_change` accept only change ids that staging or `get_pending_changes`
   returned (`merchant_agent/gates.py`). Showing the preview card marks nothing approved.
3. `check_guardrails` in `merchant_agent/changes.py` runs when a change is staged (`ChangeLedger.stage`, or your backend's
   equivalent) and again in `check_apply_change` (`merchant_agent/gates.py`) under the config in force at apply time.
   The limits are `max_items_per_change`, `max_price_delta_pct`, `max_promotion_discount_pct`, `max_restock_quantity`,
   `max_campaign_budget`, and `max_listing_field_chars` in `merchant_agent/config.py`; the defaults are demonstration values.
4. `protected_fields` can never be staged, `price_bearing_fields` are the fields the price cap reads, and
   `listing_update_blocked_fields` may not ride a free-form listing update. A domain that prices under another name
   (a nightly rate, a monthly fee, a tier price) appends to these tuples and never replaces them.
   `blocked_claim_patterns` refuses listing and campaign copy that makes an absolute, guaranteed, medical, or unsourced
   claim; a regulated domain appends its own terms the same way.
5. `require_host_approval` defaults to `True`: `apply_change` succeeds only for an id in `MerchantSessionState.approved_change_ids`,
   which only host code writes. The three surfaces in the repo are the portal's `/changes/{change_id}/apply` route
   (`examples/demo_common/merchant.py`), `MerchantToolset.host_approve` (`merchant_agent_sdk/merchant_tools.py`, prompted
   per change by `merchant-agent/runtime-agent-sdk/main.py`), and `always_ask` on `apply_change` in the hosted manifest;
   there the MCP server's config sets `require_host_approval=False` (its `default_config` does; a config you pass
   must too, or every apply is held). An approval typed into the chat sets nothing.
6. `require_host_approval` and `approval_surface` render into the static prompt and into refusals, so they are set per
   deployment and a change to either is a redeploy (commerce-prompt-caching). Name the real surface in `approval_surface`.
7. A change kind a system does not support raises `ChangeNotApplicable` (`merchant_agent/changes.py`) and the executor
   relays it; the tool stays registered. Applied and discarded changes stay queryable as the audit trail, each stamped
   with the operator from `MerchantSessionContext.operator`, which a production host derives from its authentication.

## Grounding and follow-through

- A performance question forces `get_business_snapshot`, and a change request carrying an apply phrase with nothing
  staged this session forces `get_pending_changes` (`GROUNDING_RULES` in `merchant_agent/grounding.py`; lexicons and
  flags in `merchant_agent/config.py`, appended to and never replaced).
- A turn that matched `change_requested` and ended on bare text, with no `stage_*` attempt and no `present_suggestions`
  close, gets `STAGING_FOLLOWTHROUGH_REMINDER` once, as a user message (`merchant_agent/gates.py`; applied in
  `merchant_agent_runtime/orchestrator.py` and `merchant_agent_sdk/agent.py`); the reminder text is excluded from memory extraction.
- `present_metrics` joins each pick from the snapshot, a queried series, a campaign, or a recorded analysis and drops the
  rest with a note (`resolve_metrics` in `merchant_agent/enrichment.py`), so a card never carries a model-authored figure.

## The analysis delegate

- `enable_analysis` (default off) registers `run_analysis`, a `DelegateExtension` built by `build_analysis_delegate` in
  `merchant_agent_runtime/analysis.py`. The delegate's tools are a submit tool, a progress tool, the `ANALYSIS_READ_TOOLS`
  (`merchant_agent/analysis.py`), and a query tool when the backend implements `MerchantBackend.execute_analysis_query`
  (`analysis_sql_only` then leaves the per-series reads off). It holds no staging tool; its result is recorded in
  `seen_analyses` and rendered as its own metrics card.
- `check_analysis_sql` refuses anything other than one SELECT without comments before the backend runs it; the backend owns
  the read-only role and merchant scoping; `analysis_query_timeout_s` and `cap_analysis_table` (`max_analysis_rows`,
  `max_analysis_table_chars`) bound each query, and `analysis_timeout_s`, `max_analysis_iterations`, and
  `max_delegate_calls_per_turn` bound the run.
- `analysis_use_code_execution` mounts the hosted sandbox and works on the Anthropic API only (including a Foundry deployment hosted on Anthropic); the query method works
  everywhere (`docs/deployment.md`). On the Agent SDK the same contract is a subagent whose tools are exactly the read
  tools (`build_analysis_agent` in `merchant_agent_sdk/agent.py`).
- A scheduled digest is one headless turn of the same agent (`merchant-agent/managed-agents/scheduled-digest/run_morning_digest.py`).

## Memory and components

- Memory is keyed by `merchant_id` (`memory_subject` in `merchant_agent/executor.py`); the extraction prompt in
  `merchant_agent/memory.py` admits what the operator stated about running the operation and excludes anything from
  listings, reviews, buyer messages, or metrics and anything about an identifiable customer. The write filter,
  retention, delete, purge, and `enable_memory` are the shared rules (commerce-trust-safety).
- The built-in components (`merchant_agent/enrichment.py`) are `present_metrics`, `present_digest`, `present_change_preview`,
  and `present_suggestions`; under host approval the prompt says no chip approves or applies. A vertical adds its own
  (`present_occupancy_calendar`, `present_plan_mix`, `present_event_pacing` in the examples) as extensions (commerce-ui-tools).

## Marketplaces

- Many sellers' content goes through the one fence; there is no per-seller label and no seller whose text escapes it.
  In a shopping deployment the seller is a search dimension (`SearchFilters.attributes`) that the components show, and
  `search_policies` results state whose terms they are when platform and seller terms differ.
- Provenance and caps are per session, so a session can stage against the listings its own tools returned and no others.
- Buyer and seller messages reach the model as fenced material; a message that says a change is approved sets no mark.
- The memory subject is the operator's own business, keyed by its `merchant_id`; a shopper's facts are keyed by the shopper.
