# merchant-agent/runtime-messages-api (package `merchant_agent_runtime`)

The merchant agent's turn loop on the Messages API. `MerchantAgent` builds the static
prompt and tool array once, and on each turn prefetches the merchant context and memory
facts, streams the model, executes tool calls concurrently through
`merchant_agent.executor`, and yields events for the portal to render. The four example
APIs are host applications around it (`examples/demo_common/merchant.py`).

| Module | Holds |
|---|---|
| `orchestrator.py` | `MerchantAgent`: constructor, `stream_turn`, `update_memory` |
| `analysis.py` | `build_analysis_delegate` and `AnalysisRunner`, the loop behind `run_analysis` |

## Use

```python
from pathlib import Path

from commerce_common.streaming import to_sse
from merchant_agent import MerchantAgentConfig, MerchantSessionContext, MerchantSessionState
from merchant_agent_runtime import MerchantAgent

agent = MerchantAgent(
    backend=your_backend,                       # your MerchantBackend
    skills_dir=Path("merchant-agent/skills"),
    config=MerchantAgentConfig(brand_name="Your Store"),
    memory_store=your_store,                    # optional; a commerce_common.memory.MemoryStore
    client=your_client,                         # optional; see docs/deployment.md
)

state = MerchantSessionState()                # keep per session: provenance and approval marks
session = MerchantSessionContext(session_id=sid, merchant_id=mid, operator=who)
async for event in agent.stream_turn(messages, session, state):
    send(to_sse(event))
await agent.update_memory(messages, session)  # after the reply; extraction runs on memory_model
```

`messages` is the conversation so far ending with the operator's message; the turn
appends its assistant messages, tool results, and any reminder in place, so the host
stores the list as is; `operator` is stamped on the changes the session stages. The event
types are listed in `commerce_common/streaming.py`; `ui` events carry validated, enriched
payloads, `ui_partial` events carry a component while its call streams, `change_update`
carries a change's whole record each time it moves (a successful `stage_*` call also sends
the preview card), and `progress` carries the analysis delegate's status lines while
`run_analysis` runs. An API or stream error propagates out of `stream_turn`; the host catches
it and emits an `error` event (see `examples/demo_common/host.py`).

## What the runtime adds to the executor

- When a rule in `merchant_agent.grounding` fires, the first round is pinned to that read
  tool with `tool_choice`; after `max_tool_iterations` rounds the last round runs without tools.
- Tool calls dispatch eagerly: a call executes the moment its content block closes, while
  the model writes the rest of the round (`eager_tool_dispatch`). Each model call carries a
  cache breakpoint on the newest persisted message (`rolling_conversation_cache`), placed on
  the outgoing request only; every call, the analysis delegate's included, sends thinking at
  `thinking_effort`. `eager_partial_frames` switches `ui_partial` frames from structural
  changes to every visible change; a call's `status` line goes out as the `tool_call`
  event's `label`.
- A change request (`change_requested`) that would end, on text or on chips, without a
  `stage_*` call gets `STAGING_FOLLOWTHROUGH_REMINDER` (`merchant_agent.gates`) appended
  once, and one more round.
- With `close_on_presentation` on, a round that `round_closes_turn`
  (`commerce_common/turn.py`) accepts ends the turn there, so `messages` can end on tool
  results.
- With `enable_analysis` set, `analysis.py` builds the `run_analysis` delegate; a run stops
  at `analysis_timeout_s`, and the executor allows `max_delegate_calls_per_turn` runs per turn.
- `extra_presentation_tools` and `extra_delegates` append a deployment's extensions;
  `agent.memory` is its `MemoryRuntime`, and a portal with its own memory routes reads
  and deletes through `agent.memory.store`.

The approval mark is host code writing `state.approved_change_ids`; that gate and the
others (fencing, provenance, guardrails, memory validation) live in `merchant_agent` and
`commerce_common`, and [`docs/safety.md`](../../docs/safety.md) lists them.

Credentials: the default client reads `ANTHROPIC_API_KEY` (or a token and base URL) from
the environment. Tests run without any: `pytest merchant-agent/runtime-messages-api/tests`
scripts the model with `commerce_common.testing.FakeClient`.
