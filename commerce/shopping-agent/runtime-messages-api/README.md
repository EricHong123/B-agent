# shopping-agent/runtime-messages-api (package `shopping_agent_runtime`)

The shopping agent's turn loop on the Messages API. `ShoppingAgent` builds the static
prompt and tool array once, and on each turn prefetches the profile, cart, and memory
facts, streams the model, executes tool calls concurrently through
`shopping_agent.executor`, and yields events for the host to render. The four example
APIs are host applications around it (`examples/demo_common/storefront.py`).

| Module | Holds |
|---|---|
| `orchestrator.py` | `ShoppingAgent`: constructor, `stream_turn`, `update_memory` |

## Use

```python
from pathlib import Path

from commerce_common.streaming import to_sse
from shopping_agent import ShoppingAgentConfig, ShoppingSessionContext, ShoppingSessionState
from shopping_agent_runtime import ShoppingAgent

agent = ShoppingAgent(
    backend=your_backend,                       # your StorefrontBackend
    skills_dir=Path("shopping-agent/skills"),
    config=ShoppingAgentConfig(brand_name="Your Store"),
    memory_store=your_store,                    # optional; a commerce_common.memory.MemoryStore
    client=your_client,                         # optional; see docs/deployment.md
)

state = ShoppingSessionState()                # keep per session: provenance and cart state
session = ShoppingSessionContext(session_id=sid, user_id=uid)
async for event in agent.stream_turn(messages, session, state):
    send(to_sse(event))
await agent.update_memory(messages, session)  # after the reply; extraction runs on memory_model
```

`messages` is the conversation so far ending with the user's message; the turn appends
its assistant messages and tool results in place, so the host stores the list as is. The
event types are listed in `commerce_common/streaming.py`; `ui` events carry validated,
enriched payloads, `ui_partial` events carry the same component while its call is still
streaming, and `cart_update` carries the whole cart after a write. An API or
stream error propagates out of `stream_turn`; the host catches it and emits an `error` event
(see `examples/demo_common/host.py`).

## What the runtime adds to the executor

- When a rule in `shopping_agent.grounding` fires, the first round is pinned to that read
  tool with `tool_choice`; after `max_tool_iterations` rounds the last round runs without tools.
- Tool calls dispatch eagerly: a call executes the moment its content block closes, while
  the model writes the rest of the round (`eager_tool_dispatch`). Each model call carries a
  cache breakpoint on the newest persisted message (`rolling_conversation_cache`), placed on
  the outgoing request only, and sends thinking at `thinking_effort`. `eager_partial_frames`
  switches `ui_partial` frames from structural changes to every visible change; a call's
  `status` line goes out as the `tool_call` event's `label`.
- With `close_on_presentation` on, a round that `round_closes_turn`
  (`commerce_common/turn.py`) accepts ends the turn there, so `messages` can end on tool
  results.
- `extra_presentation_tools` appends a deployment's `PresentationExtension`s to the tool array.
- `agent.memory` is the deployment's `MemoryRuntime`; a host with its own memory routes
  reads and deletes through `agent.memory.store`.

The gates themselves (fencing, provenance, caps, memory validation) are in
`shopping_agent` and `commerce_common`; [`docs/safety.md`](../../docs/safety.md) lists them.

Credentials: the default client reads `ANTHROPIC_API_KEY` (or a token and base URL) from
the environment. Tests run without any: `pytest shopping-agent/runtime-messages-api/tests`
scripts the model with `commerce_common.testing.FakeClient`.
