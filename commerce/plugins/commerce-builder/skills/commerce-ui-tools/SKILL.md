---
name: commerce-ui-tools
description: The reference presentation-tool contract, covering server-side enrichment, suggestion chips, the event stream, progressive rendering, both roles' built-in components, and adding a vertical component. Load when building or reviewing how a commerce agent's output reaches a frontend.
---

# Presentation tools

Paths are in the reference repo: `commerce_common/` is `commerce-common/commerce_common/`, `shopping_agent/` is
`shopping-agent/core/shopping_agent/`, `merchant_agent/` is `merchant-agent/core/merchant_agent/`.

## The contract

- A component is a tool. The model's arguments carry its judgment: which ids, in what order, the reason or the
  note for each, what to compare on. The server joins every fact (title, price, image, metric value, change
  record) from records tools returned this session, so the frontend never renders a model-authored value.
- One spec per component: `PresentationComponent` in `commerce_common/presentation.py` names the tool, the
  `component` string the host renders, the `payload_model` that validates the arguments (each role's
  `tools/presentation.py`), and the `enrich` hook (each role's `enrichment.py`, collected in `PRESENTATION_COMPONENTS`).
- `run_presentation` in `commerce_common/presentation.py` is the one runner: validate, enrich, emit the `ui` event.
  The model reads the executor's `displayed_text` plus the hook's notes; the enriched payload goes to the host only.
- An enrich hook drops ids without provenance and appends a note naming them; with nothing left it raises
  `PresentationRefused`, which comes back as a held call when it names a gate and as an error otherwise.
- Shopping joins from `ShoppingSessionState.seen_products`, the cart, or an order read; merchant joins from
  `MerchantSessionState.latest_snapshot`, `seen_series`, `seen_campaigns`, `seen_analyses`, `seen_listings`, and `seen_changes`.
  `enrich_change_preview` also removes model text whose currency or weekday disagrees with the change record.
- Composition rules (which component ends a turn, text carries the reasoning, cards carry the data) are static
  prompt material; each component's when-to-use line is its tool description (commerce-architecture's layer table).

## Suggestions

- `present_suggestions` is the one tool that carries the turn's chips, up to four; the model calls it in the same
  round as the turn's last component, or after its text when the turn has none, and a tapped chip is sent as the next
  user message. No other payload, built-in or extension, carries chips.
- `sanitize_suggestion_chips` in `commerce_common/fencing.py` runs on `PresentSuggestionsPayload`: invisible and control
  characters out, whitespace collapsed, empties dropped, 80 characters each, four at most. The payload fails when no
  chip survives sanitizing.
- A round of clean presentation calls that includes `present_suggestions` ends the turn (`round_closes_turn` in
  `commerce_common/turn.py`, `close_on_presentation` in the config): the Messages API loop stops there, and the Agent
  SDK runtimes stop through a `PostToolBatch` hook (`close_on_presentation_hook` in `commerce_common/agent_sdk.py`).
  Under host approval the merchant prompt says no chip approves or applies.

## Streaming

The event list is the docstring of `commerce_common/streaming.py`; `to_sse` frames each event and a host ignores
types it does not know. `ui` carries one enriched component, `ui_partial` the same while its call still streams,
`cart_update` the whole cart after a cart write, and `change_update` a change record after it moved. `outcome_events`
in `commerce_common/turn.py` stamps each `ui` event with its call id as `stream_id` and follows it with the
`tool_result`, whose `status` is `ok`, `error`, or `blocked`. Every tool that is not a presentation tool may take a
`status` argument first (`with_status` in `commerce_common/execution.py`): a few words for the person waiting, which
the executor drops before the call runs and the runtime emits as the `tool_call` event's `label`; the web layer shows
it as the activity line. The MCP servers build their tools without it. The Agent SDK runtimes run the same executor but return the payloads together in `result.ui`
after the turn.

## Progressive rendering

A spec with an `enrich_partial` hook is rendered while its arguments arrive: the request marks its tool
`eager_input_streaming` (`with_eager_input` in `commerce_common/prompt_assembly.py`), the orchestrator parses the
buffer with `parse_partial_json` (a string still being written is left out with its key), calls `enrich_partial`
(`commerce_common/presentation.py`), and yields `ui_partial` whenever `partial_signature` changes (`StreamedRound.frame`
in `commerce_common/turn.py`; every visible change with `eager_partial_frames` on the config); the final `ui` event
carries the same `stream_id` and replaces it. Input that streams as text that is not JSON comes back to the model as
an error result and the round goes on (`StreamedRound`). Partial
hooks are synchronous and join from session state only (`partial_products`, `partial_comparison`, `partial_plan`,
`partial_guide` in `shopping_agent/enrichment.py`; `partial_metrics`, `partial_digest`, `partial_change_preview` in
`merchant_agent/enrichment.py`).

## Built-in components

- Shopping (`shopping_agent/enrichment.py`): `present_products`, `present_comparison`, `present_plan`, `present_guide`,
  `present_order_status`, `checkout` (renders the cart; charges nothing), `present_suggestions`, and `present_disclosure`,
  registered only with `enable_disclosures` and filled from `StorefrontBackend.get_disclosure`.
- Merchant (`merchant_agent/enrichment.py`): `present_metrics`, `present_digest`, `present_change_preview`, `present_suggestions`.

## Adding a vertical component

- Build a `PresentationExtension` (`commerce_common/presentation.py`): the tool description and `input_schema` the
  model sees, the `payload_model` that validates the same shape, the `component` name, and the enrich hook.
- Pass it as `extra_presentation_tools` to `ShoppingAgent` or `MerchantAgent` (`examples/travel/api/main.py`); on
  the Agent SDK and MCP paths, subclass the toolset or pass `executor_class=` so the executor receives it as
  `extensions`. `build_tools` rejects a name that collides with a built-in,
  and the extension's bytes join the cached tool list (commerce-prompt-caching).
- The seven in the repo: `examples/travel/api/itinerary.py`, `examples/travel/api/occupancy.py`,
  `examples/telecom/api/plan_matrix.py`, `examples/telecom/api/plan_mix.py`, `examples/entertainment/api/venue_map.py`,
  `examples/entertainment/api/hold_view.py`, `examples/entertainment/api/event_pacing.py`. Each keeps its types and
  its card in the vertical; nothing is added to a core package.
