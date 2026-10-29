---
name: commerce-architecture
description: How the reference commerce agents of either role are structured, covering the loop, where each rule lives, skills, the backend interface, delegates, and model fields. Load when designing or reviewing the structure of a shopping or merchant agent.
---

# Commerce agent architecture

Paths are in the reference repo: `commerce_common/` is `commerce-common/commerce_common/`, `shopping_agent/` is
`shopping-agent/core/shopping_agent/`, `merchant_agent/` is `merchant-agent/core/merchant_agent/`, and the runtimes are
`shopping-agent/runtime-messages-api/shopping_agent_runtime/` and `merchant-agent/runtime-messages-api/merchant_agent_runtime/`.

## One loop

- One model owns the conversation. A turn is `ShoppingAgent.stream_turn` or `MerchantAgent.stream_turn` (each
  runtime's `orchestrator.py`): the model reads the cached prompt, calls tools (one round's calls run
  concurrently), and ends with text plus presentation calls. There is no router, classifier, or hand-off.
- Every call on every path runs through the role executor (`ShoppingToolExecutor` in `shopping_agent/executor.py`,
  `MerchantToolExecutor` in `merchant_agent/executor.py`) over `BaseToolExecutor` in `commerce_common/execution.py`.
  The Messages API runtime, the Agent SDK toolset, and the MCP server call the same `execute`, which never raises;
  after `max_tool_iterations` rounds (`commerce_common/config.py`) the runtime forces a round without tools.

## Where a rule lives

| A rule that applies | Lives in | Reference |
|---|---|---|
| While one call's arguments are being filled in | That tool's description | `build_tools` in each role's `tools/registry.py` |
| On most turns: cart and checkout, the staged-write contract, presentation grammar, tool order, trust rules | The static prompt | `build_static_system` in each role's `prompt.py` |
| On the minority of requests that need a multi-step procedure | A skill, loaded on demand | `shopping-agent/skills/`, `merchant-agent/skills/` |

A rule the core journey needs on most conversations moves a layer down. This table is the one statement of the layering.

## Skills

- A skill is a directory holding `SKILL.md`: frontmatter `name` and `description`, then the body (`parse_skill_md`
  in `commerce_common/skills.py`). The description names the request class; it carries no sample utterances.
- The static prompt carries the index alone (`SkillRegistry.index_block`, sorted by name) and `load_skill` returns
  one body (`_load_skill` in `commerce_common/execution.py`). On the Agent SDK, `ensure_project_skills` links the
  same directories into `.claude/skills/` and `SKILL_TOOL_ADAPTER` points the model at the SDK's `Skill` tool
  (`commerce_common/agent_sdk.py`); the hosted manifests list the directories under `skills[]` in `agent.yaml`.

## The backend interface

A deployment implements one abstract class per role; nothing else reaches its systems.

- `StorefrontBackend` (`shopping_agent/backend.py`): 11 abstract methods, catalog (2), cart (4), preferences (1),
  orders (2), policies (1), fulfillment (1); `get_account_context`, `get_disclosure`, and `checkout_handoff` have defaults. No method
  places an order or moves money; `checkout_handoff` names where payment happens (a hosted checkout URL, or one per seller) and the host renders it.
- `MerchantBackend` (`merchant_agent/backend.py`): 16 abstract methods, reads (8: performance 3, catalog 2,
  inventory and order health 2, pricing 1) and the change lifecycle (8: five `stage_*`, `get_pending_changes`,
  `apply_change`, `discard_change`); `execute_analysis_query`, `get_analysis_schema`, `get_merchant_context` have defaults.
- A product or listing sold by size, color, or tier is a family record carrying `options`, its variants each a
  record with `option_values` and `variant_of`; the cart and price or restock writes take a variant's id and the
  gates hold a family's. `docs/backends.md` has the mapping from common catalog models and what to return for a figure
  the platform cannot supply.
- Eligibility, pricing, inventory, and quantity rules are enforced in the backend; the gates check provenance and
  caps (commerce-trust-safety). Everything a backend returns is fenced before the model reads it.
- A system that is not wired yet is a method that fails (merchant methods raise `ChangeNotApplicable` from
  `merchant_agent/changes.py`); the tool stays registered, so prompt bytes do not change. A system the business
  does not have at all is absent: an `enable_*` switch on the role's config turned off, which removes its tools
  (`absent_tools()`), prompt lines, and grounding rule on all three paths, and the executor refuses those names;
  the skills that need it are parked under `skills/_staged/`, and the bytes are then fixed for that deployment. `NotOffered` (`shopping_agent/backend.py`) is the narrower signal:
  one item or seller the store does not serve while the system itself is on.
- `executor_class=` on `ShoppingAgent` / `MerchantAgent`, the SDK toolsets, and the MCP servers' `build_server`
  takes a subclass of the role's executor for a deployment's own `domain_error` mapping or result wording.

## Delegates

A second model call takes one shape: a `DelegateExtension` (`commerce_common/delegation.py`). It receives a brief
and the handles in `DelegationContext`, never the conversation or the executor; it returns one result validated
against `result_model`; it cannot write, present, or call a delegate; `_run_delegate` in `commerce_common/execution.py`
caps its calls per turn at `max_delegate_calls_per_turn`. `MerchantAgent` takes `extra_delegates`, and its
built-in instance is `run_analysis` (commerce-merchant-operations). `ShoppingAgent` registers none.

## Model fields

`model` runs the turn loop and `memory_model` the post-turn extraction (`BaseAgentConfig` in `commerce_common/config.py`);
`analysis_model` runs the delegate, and `None` means `model` (`MerchantAgentConfig` in `merchant_agent/config.py`). The
SDK runtimes copy `config.model` into the options; the manifests set `model:`. Choose the values with your own evals.

## Do not

- Vary `tools[]` or the static prompt by request (commerce-prompt-caching).
- Put a most-turns rule in a skill, or a one-tool rule in the prompt.
- Enforce a cap or a permission in prompt text alone; it belongs in the executor or the backend.
- Let the model author a price, a figure, or a term; components are joined from server records (commerce-ui-tools).
- Add a domain tool to a core package; a vertical adds UI through `PresentationExtension` and keeps the rest in its own code.
