---
description: Map a shopping or merchant agent the user already runs or is building, compare it with the reference row by row, and convert the rows the user picks. Use when an existing commerce agent, assistant, or chatbot is to be reviewed, or its latency, cost, UI, or safety brought in line, rather than a new one started.
argument-hint: "[where the agent's code is, and what prompted the review, if known]"
---

Review the user's commerce agent against the `anthropics/commerce-agents` reference. The user said:

$ARGUMENTS

Steps 1 to 3 map the agent, write the decision record, and produce the conversion table; a review
alone ends there. Step 4 converts the rows the user picks. Without an agent to read, stop and
suggest `/scaffold-commerce-agent`.

## Step 1: Map the agent

The reference is the current repo when `shopping-agent/core/shopping_agent/backend.py` exists,
else a clone; the agent is the path in $ARGUMENTS, else the code that builds the model request.
Fill in one line per row below with the file and line that shows it; comparing is Step 3.

| Row | What to find |
|---|---|
| Loop | Who owns a conversation: one model, a router in front, or a hand-off; what state crosses a hop |
| Rules | Where each rule lives: system text, per-request template, retrieved document, or tool description; how a procedure reaches the model |
| Tools | The list; what each returns, reshaped or passed through; whether any places an order, charges, or applies a change |
| Request | Which of system text, tools, and messages vary within a conversation; where the cache marks are; what turn two's usage reports |
| Content | What catalog, review, policy, message, memory, or web text reaches the model; what is done to it first |
| Writes | What id a write accepts and what caps it; on a merchant agent, who applies a change and how the code knows |
| Figures | What ties a policy answer, an order fact, or a metric to a read: a prompt sentence or code |
| UI | How a component reaches the frontend: parsed text, structured output, or a tool call; who fills its values |
| Sessions | Where the principal is bound; what a request carries; what is kept between requests and where; what is remembered across sessions and what filters it |
| Evals | What runs before a prompt or tool change ships, and what it grades |

Present the map in chat before going on.

## Step 2: Write the record

Write the map into the project's `CLAUDE.md` under `## Commerce agent decision record`, with the
fields `/scaffold-commerce-agent` writes: role, language, path and shell, systems behind each
backend method, identity and credentials, sessions, marketplace posture, surfaces and renderer
modes, checkout handoff (shopping), approval surface and `require_host_approval` (merchant),
flows covered, memory. `/add-commerce-flow` and `/author-commerce-evals` read it. Record the auth
mechanism, never a credential.

## Step 3: The conversion table

One line per map row, from the table below plus what the change touches in this agent; a row that
already matches says so. The patterns:

| Found | Reference | Skill; module |
|---|---|---|
| A router or one agent per domain | One model per conversation; procedures as skills | commerce-architecture; `stream_turn` in the role's `orchestrator.py`, `SkillRegistry` in `commerce_common/skills.py`, the role's `skills/` |
| A most-turns rule in a skill; one tool's rule in the prompt | Each rule at the layer matching how often it applies | commerce-architecture, the layer table; `build_static_system` in the role's `prompt.py`, `build_tools` in `tools/registry.py` |
| Thin tools; results passed through | One method per system, typed results; nothing charges | commerce-architecture; the role's `backend.py`, `tools/registry.py` |
| System text or tools built per request; no cache reads on turn two | Static text and tools built once per process; a context block; three cache marks | commerce-prompt-caching; `commerce_common/prompt_assembly.py`, `build_dynamic_context` in the role's `prompt.py`, the byte test in `tests/test_role_registries.py` |
| Third-party text read as-is | Sanitized, fenced, capped | commerce-trust-safety 1–4; `Fence` in `commerce_common/fencing.py`, the role's `fencing.py` |
| A write takes any id; caps in prompt text | Seen ids, caps, and a lock in code; held calls name the gate | commerce-trust-safety 5–9 and 18; the role's `gates.py`, the state model in `types.py` |
| Grounding by instruction | The read forced in code on the first round | commerce-trust-safety 10–11; `commerce_common/grounding.py`, the role's `grounding.py` |
| Components parsed out of text | A tool per component, filled on the server, one `ui` event each | commerce-ui-tools; `commerce_common/presentation.py`, the role's `enrichment.py` and `tools/presentation.py`, `examples/web-shared/protocol.ts` |
| A user id in the request; state rebuilt per request | Principal bound at session start; state saved with the session | commerce-trust-safety 8 and 12; `examples/demo_common/sessions.py` |
| Facts remembered without a filter | Schema-validated facts through one write filter | commerce-trust-safety 14–17; `commerce_common/memory.py` |
| Merchant writes applied by the model | Staged; guardrails; applied on the host's mark | commerce-merchant-operations; `merchant_agent/changes.py`, `merchant_agent/gates.py` |
| No suite, or whole-conversation cases | Constructed state, one turn, code graders, a replay gate | commerce-evals; `/author-commerce-evals` |

Order the rows: the evals row comes first when it applies, since it measures the rest; the request
row comes early, because it is config and assembly code and shows in the next turn's usage; the
loop row is the largest and comes last. Present the table and stop; ask which rows to convert.

## Step 4: Convert a row

Before the first code row, the agent's existing service calls become a `StorefrontBackend` or
`MerchantBackend` subclass; that lets the rows land one at a time. On Python a row's module is imported from the
reference package and the agent's own retired; in another language it is ported under the same
name, as `/scaffold-commerce-agent` lays out. Skills are copied unchanged. After each row the eval
suite runs, turn two shows cache reads (commerce-prompt-caching says where), and the record is
updated. A flow the agent lacks is `/add-commerce-flow`.
