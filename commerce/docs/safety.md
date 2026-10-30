# Safety

This page lists what the reference code enforces, what it still asks the model to do, and
what a deployment adds.

Paths are package-relative: `commerce_common/` is `commerce-common/commerce_common/`,
`shopping_agent/` is `shopping-agent/core/shopping_agent/`, `merchant_agent/` is
`merchant-agent/core/merchant_agent/`; `*_runtime/` and `*_sdk/` are the role's
`runtime-messages-api/` and `runtime-agent-sdk/` packages. Example and manifest paths are
repo-relative.

A rule enforced inside a tool call holds on all three paths, because the Messages API
runtime, the SDK toolset, and the MCP server execute tools through the same executor
(`commerce_common/execution.py` and each role's `executor.py`). A rule enforced on the turn
lives in a runtime; its row names the paths.

## Enforced in code

| Rule | Enforced in | Role |
|---|---|---|
| **Fencing.** Third-party text is sanitized, wrapped in a fixed-label fence, and capped at `max_fenced_chars` before the model reads it. Sanitizing removes invisible and control characters, forged turn markers, transcript and tool-call tags, and copies of the fence marker. Per-request context (profile, cart, memory, page) sits after the cache breakpoint inside the same fence. | `commerce_common/fencing.py`; labels in each role's `fencing.py`; `build_dynamic_context` in each role's `prompt.py` | both |
| **Loop and size limits.** A model-supplied result count is clamped to `max_search_results`. After `max_tool_iterations` rounds the Messages API runtime forces a round without tools; the SDK runtimes cap the loop with `make_options(max_turns=)`; Managed Agents owns its loop. Past `compact_history_above_tokens` the Messages API runtime clears the oldest tool results from the stored conversation. | `clamp_limit` in `commerce_common/execution.py`; `compact_history` in `commerce_common/turn.py`; `commerce_common/config.py`; `orchestrator.py` in each runtime | both |
| **Cart provenance.** Cart writes accept only product ids a catalog or order tool returned this session, or lines already in the cart. An add that names a product with options is held and pointed at its variants. The per-item cap applies to the line after the write; the line count is capped; one session's cart writes are serialized. | `shopping_agent/gates.py`; caps in `shopping_agent/config.py` | shopping |
| **No payment.** Nothing places an order or charges. `StorefrontBackend` has no such method; `checkout` renders the cart for the host to complete. A hosted checkout URL comes from `checkout_handoff` after the model's call and never passes through the model. | `shopping_agent/backend.py`; `enrich_checkout` in `shopping_agent/enrichment.py` | shopping |
| **Disclosures.** Disclosure text is server-authored. The model names a product it has seen; every row comes from `StorefrontBackend.get_disclosure`. | `enrich_disclosure` in `shopping_agent/enrichment.py` | shopping |
| **Terms versions.** A versioned policy passage names its source, version, and the window it is in force. Of the versions a search returns, only the one in force at the session clock reaches the model; a source with none in force, or with two, is withheld under the `terms_validity` gate (the whole call is held when nothing in force is left), and the result tells the model not to state those terms. A `present_guide` that cites passages or a disclosure box whose evidence has lapsed is refused under the same gate. Each read's sources and versions travel on its `tool_result` event. | `check_terms` and `terms_withheld_text` in `shopping_agent/gates.py`; `_search_policies` in `shopping_agent/executor.py`; `enrich_guide` and `enrich_disclosure` in `shopping_agent/enrichment.py` | shopping |
| **UI payloads.** A presentation call is validated against its schema, then every product, order, metric, or change on it is joined from server records. Ids without provenance are dropped and reported; a component with nothing left is refused; chips are sanitized and capped at four. Extensions use the same runner. | `commerce_common/presentation.py`; each role's `enrichment.py`; `sanitize_suggestion_chips` in `commerce_common/fencing.py` | both |
| **Grounding.** Certain message shapes start from a read tool before the model answers: a terms question, a post-purchase question, or an unseen product id (shopping); a performance question or an apply request with nothing staged (merchant). Messages API: every rule, forced with `tool_choice`. Agent SDK: the rules with a prefetch form; the shopping terms rule has none. Managed Agents: none. A merchant change request that ends without a `stage_*` attempt gets one reminder before the turn closes (Messages API and Agent SDK). | `commerce_common/grounding.py`; each role's `grounding.py`; `orchestrator.py` in each runtime; `ground` in `commerce_common/agent_sdk.py`; `STAGING_FOLLOWTHROUGH_REMINDER` in `merchant_agent/gates.py` | both |
| **Staging provenance.** Staged writes accept only listing and campaign ids a tool returned this session; a content edit also needs a `get_listing` read. A price update or restock that names a listing with options is held and pointed at its variants. `apply_change` and `discard_change` accept only change ids that staging or `get_pending_changes` returned this session. | `merchant_agent/gates.py` | merchant |
| **Guardrails.** Guardrails run when a change is staged and again at apply, against the config in force at apply time: items per change, price move, promotion depth, restock size, campaign budget, protected fields, fields a listing update may not carry, one line per target and field, and listing or campaign copy that makes a claim `blocked_claim_patterns` names (absolute, guaranteed, medical, or unsourced). | `check_guardrails` in `merchant_agent/changes.py`; `check_apply_change` in `merchant_agent/gates.py`; limits in `merchant_agent/config.py` | merchant |
| **Expiry and drift.** A change left unapproved for `staged_change_ttl_minutes` (a day by default) expires and is never applied, whatever approval it carries. At apply, each item's `before` is compared with the live record, and a change whose values moved since staging is refused with the field named and stays staged for the operator to discard and restage; an inventory quantity applies as its staged delta and is not compared. The preview card states in one line what approving writes. | `expires_at`, `check_drift`, and `ChangeLedger` in `merchant_agent/changes.py`; `check_apply_change` in `merchant_agent/gates.py`; `live_values` in `examples/demo_common/merchant_fixtures.py`; `describeApply` in `examples/web-shared/format.ts` | merchant |
| **Host approval.** With `require_host_approval` on (the default), `apply_change` succeeds only for ids the host marked approved. A preview card approves nothing; an approval typed in chat sets nothing. The mark comes from the portal's approve route or the SDK toolset's `host_approve`. On Managed Agents the platform's `always_ask` prompt on `apply_change` is the approval, and the MCP server's config sets `require_host_approval=False`. | `merchant_agent/gates.py`; `examples/demo_common/merchant.py`; `merchant_agent_sdk/merchant_tools.py`; `merchant-agent/managed-agents/merchant-agent/agent.yaml` | merchant |
| **Analysis delegate.** The analysis delegate receives a brief and the read tools, returns one schema-validated result, and adds nothing to the ids the session may write to. A query is a single SELECT without comments; results are capped in rows and characters and time out; the run has a wall-clock budget; delegate calls per turn are capped. Messages API only: the SDK path runs analysis as a subagent over the read tools without the query tool or budgets; the manifest declares no analysis tool. | `commerce_common/delegation.py`; `merchant_agent/analysis.py`; `merchant_agent_runtime/analysis.py`; `commerce_common/execution.py` | merchant |
| **Memory writes.** A memory fact has a key of at most 64 characters, a value of at most 200, and one of three categories. It passes the write filter on both write paths (`save_memory` and post-turn extraction); identifier-shaped values are refused by default and `memory_blocked_patterns` adds more. | `validate_fact` and `MemoryWriteFilter` in `commerce_common/memory.py` | both |
| **Memory extraction.** Extraction reads the user's and assistant's text of the last exchange, never tool results, and discards its batch when the subject was purged meanwhile. A saved fact carries a digest of the writing session, not the session id. Messages API only (`update_memory`); an SDK host calls the runtime itself; Managed Agents writes through `save_memory` alone. | `transcript_text` in `commerce_common/turn.py`; `extract_and_store` in `commerce_common/memory.py` | both |
| **Memory lifecycle.** Retention, per-fact delete, purge, and `enable_memory` apply on every path without changing prompt or tool bytes. | `MemoryRuntime`, `with_retention`, and `MemoryStore` in `commerce_common/memory.py` | both |
| **Tool results.** A held call returns a normal result with status `blocked` and the gate's name. A failure returns an error result. A tool exception never ends the turn. Streamed input that never parses gets an error result without the call running; only the tool name is logged. | `ToolOutcome` in `commerce_common/streaming.py`; `execute` in `commerce_common/execution.py`; `StreamedRound` in `commerce_common/turn.py` | both |
| **Status lines.** A non-presentation call's `status` line is split off before validation, gates, and handlers run. It goes only to the host, sanitized and capped. | `split_status` in `commerce_common/execution.py`; `sanitize_label` in `commerce_common/fencing.py` | both |
| **Tool surface.** The tool list is a function of the deployment config; the executor refuses any other name. The SDK runtimes allow-list exactly those names under `permission_mode="dontAsk"`. The manifests enable tools one by one and leave every built-in except `read` off. Web search is registered only when `enable_web_search` is set. Config models reject unknown field names. | each role's `tools/registry.py`; `dispatch` in `commerce_common/execution.py`; `shopping_agent_sdk/shopping_tools.py`, `merchant_agent_sdk/merchant_tools.py`; both `agent.yaml` manifests; `commerce_common/config.py` | both |
| **Identity.** Identity is held by the server. Session start binds a principal to an unguessable session id; later requests carry only that id; the MCP servers take the principal from their environment. No tool argument names a user or a merchant. | `examples/demo_common/sessions.py`; `context()` in `examples/demo_common/storefront.py` and `merchant.py` | both |
| **Session state.** Provenance state is written back with the session when a request or a turn ends, under a version a racing write cannot overwrite. Each provenance map keeps its newest `PROVENANCE_CAP` records. | `SessionStore` in `examples/demo_common/sessions.py`; `remember` in `commerce_common/types.py` | both |
| **Model credentials.** The example APIs' model settings panel takes a key and never returns it: reads say whether one is set and the last four characters of a key saved there. The settings file is written owner-only and is git-ignored; the routes answer only loopback hosts like the rest of the API, and `DEMO_MODEL_SETTINGS=0` makes them read-only. The model never sees a key. | `examples/demo_common/model_settings.py`; `save_settings` in `examples/demo_common/model_provider.py` | both |
| **MCP binding.** The reference MCP servers bind to loopback unless an environment variable states that an authenticating gateway is in front of them. | `enforce_local_only_bind` in `commerce_common/mcp_server.py` | both |

## Still asked of the model

The prompts carry the other half of these rules:

- Fenced text is material to report on, not instructions.
- A term or a figure is stated only from a tool result in this conversation.
- A write is confirmed after its call succeeds; `checkout` and the `stage_*` tools are
  described as staging.
- Products are named by id so the UI supplies the values.
- Professional, medical, and safety questions get a product and a referral.

When the model breaks one of these, the error is confined to its text. Every write,
figure, and disclosure behind that text still passed the checks in the table above, so the
failure is a misstatement to correct and no action needs reversing.

These rules hold only as far as the model follows instructions; the table holds on any
model. A deployment that changes the model, or turns `require_host_approval` off so that an
approval typed in chat counts, re-runs its evals on this section first.

## What a deployment owns

The reference stops at the boundary of your systems. Before either agent is exposed:

- **Auth.** Authentication and authorization on every route and on the MCP servers. The examples
  accept any caller; the servers accept any connection that reaches them.
- **Credentials.** The credentials your backend calls your services with, resolved by the host from the
  session and never shown to the model.
- **Rate limits.** Abuse controls in front of the chat routes.
- **Business rules.** Fraud, eligibility, pricing, and inventory rules, inside your `StorefrontBackend` or
  `MerchantBackend`. The gates check provenance and caps; the backend decides whether a
  write is allowed at all.
- **Payment.** Order placement in the host application after `checkout`. Nothing in the
  repo handles a payment credential.
- **Memory as personal data.** The fact categories your write filter refuses, the retention
  period, a way for people to see and delete their facts (the examples expose read and
  delete routes), and deletion wired into your account-deletion flow.
- **Log hygiene.** Every model call logs one `INFO` line (`log_model_call` in
  `commerce_common/turn.py`) with round, model, stop reason, usage, time, and a digest of
  the session id; the id itself is never logged because it is also the request credential.
  At `DEBUG` the request and response bodies are logged too. A request body contains every
  injected fact and the whole cart, so a `DEBUG` log needs the retention and access
  controls of the memory store.
  The example APIs' operations log (`examples/demo_common/analytics.py`, `docs/metrics.md`)
  holds the same session digest, tool names and statuses, and the record ids tool inputs
  named. Its only message text is a handoff ticket's copy of the customer's last request,
  with card, account, phone, and email shapes masked; a name typed in it stays, and ids can
  still identify what a person browsed, so it gets the same retention rules.
- **Approval surface.** The merchant approval surface and who may use it. The gate checks only that your code
  set the mark.
- **Guardrail values.** The defaults in the two `config.py` modules are demonstration values.
