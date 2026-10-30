# merchant-agent/core (package `merchant_agent`)

Everything the merchant agent's three paths agree on. The turn loops live in
`../runtime-messages-api/` and `../runtime-agent-sdk/`; the hosted path's server is in
`../managed-agents/`. A deployment implements `MerchantBackend` and constructs a
`MerchantAgentConfig`; the rest is consumed as is. [`docs/backends.md`](../../docs/backends.md) covers listings with
variants and what to return for a figure the platform cannot supply.

| Module | Holds |
|---|---|
| `types.py` | Listings (a family's `options`, its `variants` with `option_values` and `variant_of`), snapshots and series (a figure the store cannot supply is `None` with a `note`), `DataLimitation`, alerts, issues, returns (`ReturnReason`, `ReturnLog`, `ReturnsSummary`), pricing context, campaigns, drafts, `StagedChange`, `MerchantSessionContext`, `MerchantSessionState` |
| `backend.py` | `MerchantBackend`: 8 reads, 5 `stage_*` methods, and `get_pending_changes`, `apply_change`, `discard_change`; optional `get_returns`, `execute_analysis_query`, `get_analysis_schema`, `get_merchant_context` |
| `config.py` | `MerchantAgentConfig`: analysis settings and budgets, the `enable_*` system switches, guardrail limits, approval, `stage_shows_preview`, `staged_change_ttl_minutes`, grounding lexicons |
| `prompt.py` | `build_static_system` (cached) and `build_dynamic_context` (fenced, per request) |
| `tools/registry.py` | The tool contracts, in a fixed order; `run_analysis` is added when `enable_analysis` is set |
| `tools/presentation.py` | Payload schemas for the three built-in presentation tools (chips are in `commerce_common`) |
| `enrichment.py` | Metric picks resolved to session values, digest items joined to records, the preview built from the staged record; partial payloads while streaming |
| `changes.py` | `check_guardrails`, run at staging and again at apply; `expires_at` and `check_drift`, run at apply; and the in-memory `ChangeLedger` |
| `gates.py` | Listing and campaign provenance, the options hold (a family listing is priced and restocked per variant), the apply and discard gates, the follow-through reminder text |
| `grounding.py` | The metrics and queue grounding rules and the `change_requested` detector |
| `returns.py` | `summarize_returns`: a `ReturnLog` counted per listing and by reason, each reason's stage (`REASON_STAGES`), clipped buyer notes |
| `serialization.py` | Tool-result payloads: search header, listing record with variant rows, pricing context, alerts |
| `analysis.py` | The `run_analysis` contract: the delegate's prompt and tools, `check_analysis_sql`, `cap_analysis_table`, the metrics payload derived from an `AnalysisResult` |
| `fencing.py`, `memory.py` | The `merchant_data` fence and the extraction prompt |
| `executor.py` | `MerchantToolExecutor`: one handler per tool over the shared frame; subclassed and passed on as `executor_class`; `build_memory` |

Tests: `pytest merchant-agent/core/tests`.
