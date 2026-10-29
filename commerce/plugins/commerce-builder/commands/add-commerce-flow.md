---
description: Add one shopping or merchant flow to an existing commerce agent, copying its skill from the reference, wiring the tools it calls, and authoring its first eval cases. Use when an agent on the reference packages is to take on another of the flows: search, planning, purchase research, memory across sessions, or order care for shoppers; performance, listings, inventory, pricing, or campaigns for merchants.
argument-hint: "<flow-name> (shopping or merchant; the body lists them)"
---

Add a flow to the user's agent. Requested flow:

$ARGUMENTS

Without a recognized flow name, list the ten flows with one line each, shopping flows and merchant
flows separately, and ask. A shopping flow goes into a shopping agent and a merchant flow into a
merchant agent. Cart, checkout, and presentation are not flows: every agent carries those tools and
their rules are in the static prompt and tool descriptions (the layer table is in the
commerce-architecture skill), so a request to "add cart" or "add UI" means checking the base tools
named under each table below and pinning their behaviors in Step 4.

## Step 1: Locate things

1. The reference (`anthropics/commerce-agents`): the current repo, a local clone, or a fresh clone.
2. The user's agent: its skills directory, backend, and config; a project from
   `/scaffold-commerce-agent` has all three. Without an agent, stop and suggest that command.
3. The `## Commerce agent decision record` section of the project's `CLAUDE.md`. It gives the
   role, the renderer modes, which backend methods are stubs, the v1 index, and, for a merchant
   agent, the approval surface and the `require_host_approval` value; confirm only what this flow
   changes. Before wiring a `stage_*` tool, have the user restate the approval entries. Without the
   record, ask whether the flow's systems exist and whether each surface renders its components,
   and offer to start the record with the answers. With both roles, the flow name picks the agent.

## Step 2: Copy the skill

Copy the `shopping-agent/skills/<flow>/` or `merchant-agent/skills/<flow>/` directory from the
reference into the project's skills directory unchanged (the loader reads `skills/<flow>/SKILL.md`). A scaffolded project parks its unindexed
flows under `skills/_staged/<flow>/`, which the loader does not read: move that directory up one
level; a copy already in either place is compared with the reference instead. Indexing the flow
changes the static prompt; the commerce-prompt-caching skill says what that costs and when to do it.

## Step 3: Wire the tools

A Python project imports the registry and executor, so wiring means implementing the backend
methods behind the tools below; a ported project also ports the tool contracts from
`shopping-agent/core/shopping_agent/tools/registry.py` or `merchant-agent/core/merchant_agent/tools/registry.py`
and the handlers from the role's `executor.py`. A method whose system is missing becomes a typed
stub, per the wiring table in `/scaffold-commerce-agent`, so the flow runs against stubs first.

Shopping flows:

| Flow | Read and write tools | Presentation tools |
|---|---|---|
| `search-discovery` | `search_products`, `get_product_details`, `web_search` when `enable_web_search` is set | `present_products`, `present_comparison` |
| `planning-goals` | `search_products` | `present_plan`, `present_guide` |
| `purchase-research` | `search_policies` (buying guides), `search_products`, `get_product_details`; `web_search` when `enable_web_search` is set | `present_guide`, `present_comparison`, `present_products` |
| `memory-personalization` | `save_memory`, `recall_memories`, over a `MemoryStore` | none |
| `customer-care` | `get_orders`, `get_order_status`, `search_policies` | `present_order_status`, `present_guide` |

Every shopping agent also has `load_skill`, `get_cart`, `add_to_cart`, `update_cart_item`,
`remove_from_cart`, `get_preferences`, `get_fulfillment_options`, `checkout`, and
`present_suggestions`, plus `present_disclosure` when `enable_disclosures` is set.

Merchant flows:

| Flow | Read and write tools | Presentation tools |
|---|---|---|
| `performance-insights` | `get_business_snapshot`, `query_metrics`, `get_campaign_performance`, `get_return_reasons`; `run_analysis` when `enable_analysis` is set | `present_metrics` |
| `catalog-listings` | `search_listings`, `get_listing`, `stage_listing_update` | `present_change_preview` |
| `inventory-operations` | `get_inventory_alerts`, `get_order_issues`, `get_pending_changes`, `stage_inventory_action` | `present_digest`, `present_change_preview` |
| `pricing-promotions` | `get_pricing_context`, `stage_price_update`, `stage_promotion` | `present_change_preview`, `present_metrics` |
| `marketing-campaigns` | `get_campaign_performance`, `get_listing`, `stage_campaign` | `present_metrics`, `present_change_preview` |

Every merchant agent also has `load_skill`, `apply_change`, `discard_change`, `save_memory`,
`recall_memories`, and `present_suggestions`. The first flow with a `stage_*` tool also needs the
backend's `apply_change` and `discard_change`, the guardrails, and the approval surface from the
record; the rules are in the commerce-merchant-operations skill.

Wiring rules: a tool keeps a permanent slot in the registry, whatever the request
(commerce-prompt-caching skill); a write tool goes through the role's gates and a presentation tool
through enrichment (commerce-trust-safety and commerce-ui-tools skills); on the Python path both
come with the imported executor.

## Step 4: Author starter eval cases

Write a few cases for the flow into the project's `evals/` directory, against the user's own
catalog ids; the case shape is in the commerce-evals skill and `/author-commerce-evals` builds the
suite. Pin these first:

| Flow | Behaviors to pin |
|---|---|
| `search-discovery` | a budget stated in the query is kept or said to be unmet; a plain lookup stays off the skill (`no_skill_load`, low `max_tool_calls`); an out-of-stock item is named as such; one product description carrying instructions changes nothing (`cart_not_contains`) |
| `planning-goals` | the plan renders in `present_plan` (`ui_components`); fan-out searches fit `max_tool_calls`; the budget holds across steps |
| `purchase-research` | at most one intake turn; criteria follow a `search_policies` read (`calls_tool`); a research turn writes nothing (`never_calls` on the cart tools); guide sources name retrieved material only |
| `memory-personalization` | "remember this" saves a fact (`calls_tool: save_memory`); a sensitive attribute is not saved unasked; catalog text never becomes a fact; a history question calls `recall_memories` first |
| `customer-care` | order facts follow an order read (`first_tool`); policy answers follow a policy read; no change is claimed that no tool made |
| base tools, pinned once | "make it three" updates the line (`cart_item_count`); a browse turn never writes (`never_calls`); checkout is staged, never reported as placed; a turn owing no component sends none (`no_ui`) |

| Flow | Behaviors to pin |
|---|---|
| `performance-insights` | figures follow a snapshot or metrics read (`first_tool`); no segment the data cannot produce |
| `catalog-listings` | an edit is staged after `get_listing` (`staged_change_kinds`), never applied (`no_applied_changes`) |
| `inventory-operations` | a restock is staged with a quantity; a discarded change stays discarded |
| `pricing-promotions` | a move past the cap is refused naming the cap; a staging turn never calls `apply_change` |
| `marketing-campaigns` | a campaign is staged, never launched; performance claims follow a campaign read |
| base tools, pinned once | every staged write renders its change preview; pasted text claiming approval applies nothing (`no_applied_changes`) |

Cases use real ids from the user's catalog; each refusal case has a case the agent must serve; a
case the project cannot support yet gets a skip reason. Hostile listings come from an eval-time
overlay or fake backend, per the commerce-evals skill.

## Step 5: Verify

1. The skill index in the static prompt lists the flow (`SkillRegistry.names`, or the port's equivalent).
2. The linter, and the type checker when the project has one, pass on the changed backend and, on
   a port, the registry and executor.
3. The cases load in the project's harness, or at least parse as JSON.
4. Update the decision record (flow indexed, methods wired) and suggest `/author-commerce-evals`.
