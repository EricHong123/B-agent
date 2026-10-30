---
name: commerce-trust-safety
description: The rules the reference agents enforce in code for third-party content, writes, grounding, identity, and memory, each with its module, plus two adversarial-eval rules. Load when handling untrusted tool results, guarding a write tool, or scoping what an agent remembers.
---

# Trust and safety rules

`commerce_common/` is `commerce-common/commerce_common/`, `shopping_agent/` is `shopping-agent/core/shopping_agent/`, and
`merchant_agent/` is `merchant-agent/core/merchant_agent/`; `docs/safety.md` lists the same rules. A rule inside a tool
call holds on all three paths, which share one executor (commerce-architecture); rules 10 and 15 name the paths they run
on. Merchant staging, guardrails, approval, and marketplace posture are in commerce-merchant-operations.

## Fence third-party content

1. Every tool result from catalog, review, policy, order, metric, message, or web content goes through
   `Fence.fence_payload` (`commerce_common/fencing.py`): NFKC-normalized, invisible and control characters removed, fence
   markers, forged turn markers, and special tokens replaced, wrapped in the role's label, and cut at `max_fenced_chars`.
   The executor's `_fenced` applies it to every handler.
2. The label and the notice are per-role constants (`STOREFRONT_FENCE` in `shopping_agent/fencing.py`, `MERCHANT_FENCE` in
   `merchant_agent/fencing.py`); the notice appears once, in the static prompt, with nothing untrusted in it.
3. The per-request block (profile, cart, memory facts, page, store context) sits inside the same fence after the cache
   breakpoint (`build_dynamic_context` in each role's `prompt.py`); backend context blocks have their own cap.
4. A model-supplied result count is clamped to `max_search_results` (`clamp_limit` in `commerce_common/execution.py`).

## Gate writes on provenance and caps

5. A cart write accepts only ids in `ShoppingSessionState.seen_products`, filled by the session's catalog and order reads
   (`check_provenance` and `remember_order_items` in `shopping_agent/gates.py`); update and remove also accept a line
   already in the cart. Merchant staging accepts only ids in `seen_listings` and `read_listings`, apply and discard only
   ids in `seen_changes` (`merchant_agent/gates.py`; commerce-merchant-operations).
6. `max_quantity_per_item` caps the line after the write and `max_cart_lines` the cart, under a session lock
   (`gated_add_to_cart` in `shopping_agent/gates.py`; caps in `shopping_agent/config.py`). The lock is per process, so
   `StorefrontBackend` cart methods enforce them too; eligibility, pricing, and inventory are the backend's in both roles.
7. Nothing in either interface charges or places an order: `checkout` renders the cart (`enrich_checkout` in
   `shopping_agent/enrichment.py`) and the host completes it; post-purchase care is reads, with no cancel or refund tool.
8. Provenance lives on the session state (`ShoppingSessionState`, `MerchantSessionState`), saved with the session when
   the request or turn ends (`SessionStore` in `examples/demo_common/sessions.py`, a versioned state document beside the
   transcript), so a request on another process loads it. Each map keeps its newest `PROVENANCE_CAP` records (`remember`
   in `commerce_common/types.py`); a dropped id needs a fresh read.
9. A component is validated, its products, orders, metrics, or changes are joined from those records, and ids without
   provenance are dropped and reported (`run_presentation` in `commerce_common/presentation.py`; each role's
   `enrichment.py`; commerce-ui-tools).

## Ground the answers that are figures or terms

10. A terms question, an order question, or an unseen product id (`GROUNDING_RULES` in `shopping_agent/grounding.py`), or
    a performance question or an apply request with nothing staged (`merchant_agent/grounding.py`), starts from the
    matching read: `first_forced_tool` in `commerce_common/grounding.py` picks it, the Messages API runtimes force it with
    `tool_choice`, and the SDK runtimes prefetch it when the rule has a prefetch form (`ground` in
    `commerce_common/agent_sdk.py`; the terms rule has none); the hosted path has the prompt only.
11. The lexicons are config tuples (`policy_intent_terms`, `order_intent_terms`, `product_id_patterns`, `metrics_intent_terms`,
    and their cues); a deployment appends its own words, a gate flag turns a rule off, and neither changes prompt bytes.

## Hold identity on the server

12. Session start binds the authenticated principal to an unguessable session id; later requests carry only that id, and
    routes read the principal from the record (`SessionStore.start` and `session_dependency` in
    `examples/demo_common/sessions.py`). No request field or tool argument names a user, merchant, or operator; the MCP
    servers take the principal from their environment, a production server from its request.
13. Whether the principal owns a record (order, ticket, listing), and whether the step a call depends on has
    happened, is the backend's check against its store; an id having provenance does not make it theirs or ready.

## Bound what is remembered

14. Every fact on both write paths (`save_memory` and post-turn extraction) passes `validate_fact` in
    `commerce_common/memory.py`: key of at most 64 characters, value of at most 200, one of the three `MemoryCategory`
    values, and the `MemoryWriteFilter`, which refuses identifier-shaped values by default; `memory_blocked_patterns`
    adds patterns, and a filter with `checks` replaces it (`MemoryRuntime.build`).
15. Extraction reads the last exchange's user and assistant text (`transcript_text` in `commerce_common/turn.py`), and
    `extract_and_store` drops its batch when the subject was purged meanwhile; the Messages API runtimes run it
    (`update_memory`), the SDK host calls the runtime, and the hosted path writes through `save_memory` only.
16. `memory_retention_days` (`with_retention`), `MemoryStore.delete_fact`, `MemoryStore.clear`, and `enable_memory` hold
    on every path without changing prompt or tool bytes; the examples expose read and delete routes
    (`install_memory_routes` in `examples/demo_common/memory.py`), and `clear` belongs in account deletion.
17. The subject is the shopper's `user_id` or the operation's `merchant_id` (`memory_subject` in each role's `executor.py`).

## Refuse in the result, and keep the surface fixed

18. A held call returns a normal result naming its gate (`ToolOutcome.held` in `commerce_common/streaming.py`; the host's
    `tool_result` event carries `status: blocked`), a failure returns an error result, and `execute` never raises.
19. The tool list is a function of the config: `enable_web_search` (default off) adds the tool, the SDK runtimes allow-list
    the registered names, and the manifests enable tools one by one.
20. The reference MCP servers bind to loopback unless an environment variable states that an authenticating gateway is in
    front (`enforce_local_only_bind` in `commerce_common/mcp_server.py`).

## Two rules for adversarial evals

- Poisoned listings, reviews, and messages live in eval fixtures merged in for a run, outside demo and catalog data.
- Every refusal case has a should-serve counterpart in the same niche, so a suite catches over-refusal too (commerce-evals).
