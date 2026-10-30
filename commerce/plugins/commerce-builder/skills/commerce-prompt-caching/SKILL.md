---
name: commerce-prompt-caching
description: The reference agents' cache-stable request assembly, covering the static system and per-request context split, the fixed tool list, the rolling conversation breakpoint, which config fields are prompt bytes, and verification. Load when writing or reviewing a commerce agent's prompt assembly, when cache reads are zero, or when a turn's latency or cost is the question.
---

# Cache-stable request assembly

`commerce_common/` is `commerce-common/commerce_common/`, `shopping_agent/` is `shopping-agent/core/shopping_agent/`, and
`merchant_agent/` is `merchant-agent/core/merchant_agent/`.

## The three breakpoints

A request's cacheable prefix runs `tools`, then `system`, then the messages; a breakpoint ends a span the next call reads
back. The reference agents place three, all from `commerce_common/prompt_assembly.py`:

1. **The last tool**: `with_tool_cache_control(tools)`.
2. **The static system text**: `build_system_blocks(static, context)` marks it and appends the context block unmarked.
3. **The newest persisted message**: `build_request_messages(messages, rolling_breakpoint=...)` marks the last persisted
   block on the outgoing request only; the next call then reads the earlier rounds, search payloads included, from cache.

Everything per request goes in the context block, which the role's `build_dynamic_context(...)` renders once per turn.
In the static block or the tool list, those bytes would break the system or tool span on every request; in the context block they cost
one re-read of the conversation on a turn whose cart, page, or facts moved, and the rolling marker holds from that turn's
next round. The clock renders to the hour (`context_clock`), so a new minute moves nothing.

## The split as implemented

- `build_static_system(config, skills)` in each role's `prompt.py` renders identity, the most-turns rules, the fence
  notice, and the skill index from the config and the installed skills: the same bytes for the life of a deployment.
- `build_dynamic_context(...)` in the same module renders the per-request material inside the role's data fence: shopping
  takes preferences, memory facts, the cart, the page, the account block, and the time; merchant takes the store context,
  memory facts, and the time. Backend context blocks have their own size cap.
- `ShoppingAgent.__init__` and `MerchantAgent.__init__` (each role's `runtime-messages-api` `orchestrator.py`) build
  `_static_system` and `_tools` once per process; `stream_turn` renders the context block per turn and calls
  `build_request_messages` per model call.
- `build_tools` in each role's `tools/registry.py` emits the built-ins in a fixed order (the merchant builder adds `run_analysis` after them when enabled), the `load_skill` enum sorted,
  then extensions in the order given, then `web_search` when enabled; every registered tool ships on every request, and
  the executor decides on arrival whether a call can be served.
- The Agent SDK runtimes pass the same static text (plus `SKILL_TOOL_ADAPTER`) and the same contracts, and the SDK caches
  them; the hosted manifests carry the text as `system.md`, which `scripts/check.py` compares with the builder.

## When the rolling marker is skipped

Two rounds carry no marker. A bare first call (one message): a one-shot session would pay the write without a read, and
the second call's marker covers the first message anyway. A round whose `tool_choice` is other than `auto` (the
grounding-forced first iteration and the forced-text last one): `tool_choice` keys the messages span, so an entry written
under a forced round is unreadable by the auto rounds after it; the system and tool spans still hit. Both live in
`build_request_messages` and the loops' `rolling_breakpoint=` argument; `rolling_conversation_cache` turns the marker off
for debugging.

## When the conversation is compacted

When a turn's last call was given `compact_history_above_tokens` or more (its usage says; the default is the platform's
own tool-result-clearing default, a tenth of the window), the turn ends with `compact_history` in
`commerce_common/turn.py`, which replaces the oldest tool results in the stored conversation with a one-line marker
until the conversation is half its previous size. The next turn's first round rewrites the messages span once and later
rounds read the shorter one; `turn_complete.results_cleared` tells a host that appends its transcript to rewrite it. The
system and tool spans, the messages, and the write gates are unaffected; provenance lives on the session state.

## Config fields that are prompt bytes

The fields marked `(prompt)` in `commerce_common/config.py` and the role configs, plus `enable_analysis` and
`max_items_per_change`, which the merchant tool builder reads, render into the static text or the tool list; changing one is a redeploy and a miss on the next request:

| Config | Fields |
|---|---|
| `BaseAgentConfig` (`commerce_common/config.py`) | `brand_name`, `assistant_name`, `brand_voice`, `enable_web_search` |
| `ShoppingAgentConfig` (`shopping_agent/config.py`) | `domain_search_notes`, `enable_disclosures`, and the system switches `enable_cart`, `enable_orders`, `enable_policies`, `enable_fulfillment` |
| `MerchantAgentConfig` (`merchant_agent/config.py`) | `enable_analysis`, `require_host_approval`, `approval_surface`, `stage_shows_preview`, and the system switches `enable_listing_edits`, `enable_inventory`, `enable_pricing`, `enable_campaigns`; `max_items_per_change` and `max_search_results` set `maxItems` and `maximum` on tool schemas |

Skills, presentation extensions, and delegates are prompt bytes too. Gate lexicons, guardrail limits, memory settings,
the latency knobs (`eager_tool_dispatch`, `rolling_conversation_cache`, `eager_partial_frames`,
`close_on_presentation`), cart caps, and `compact_history_above_tokens` are not; `tests/test_role_registries.py`
asserts it for each.

## What breaks a hit

- Anything per request in the static block or the tool list: a name, a cart count, a page, a clock, a request id. The
  context block takes the first four; a request id belongs nowhere.
- A set or dict iterated into prompt text or a schema without sorting.
- `tools[]` membership decided per request (a flag read per request instead of once at construction).
- Rebuilding the static text or the tool list inside the turn instead of in the constructor.
- Persisting the rolling marker into the stored conversation, which then gains one marker per turn.
- Toggling a `(prompt)` field, a skill, or an extension on a running deployment; each is a redeploy.
- A prompt variant chosen per request instead of per deployment.
- A prefix under the model's minimum cacheable length, which writes nothing.
- A forced `tool_choice` (grounding first, `none` last) misses the messages span only; the loops skip the marker there.

## How to verify

- `turn_complete` carries `usage` (`usage_totals` in `commerce_common/turn.py`, the turn's calls summed) and
  `elapsed_ms`; every call also logs one line with the same counters and its own time (`log_model_call`, on
  `shopping_agent_runtime.orchestrator` and `merchant_agent_runtime.orchestrator`). Zero cache reads on the second turn
  of a conversation means the prefix changed. The counters worth charting per config version are cache reads as a
  share of input, `elapsed_ms`, rounds per turn, and blocked `tool_result` events by gate.
- `tests/test_role_registries.py` builds each role's prompt and tools twice and compares bytes, checks the cache marks,
  and checks that non-prompt settings change nothing; `commerce-common/tests/test_prompt_assembly.py` covers the block
  builders, the context clock, the rolling marker, and the skip cases; `tests/test_turn_loop.py` pins both loops to the
  same blocks, marker, and clean history. A deployment's tests carry the same three checks.
- In a deployed environment, run one three-turn conversation and read the second and third turns' usage; a proxy or retry
  layer that rewrites requests shows up here and nowhere else.
