# merchant-agent/runtime-agent-sdk (package `merchant_agent_sdk`)

The merchant agent on the [Claude Agent SDK](https://pypi.org/project/claude-agent-sdk/).
The SDK runs the loop, caching, and skill loading; this package supplies the same static
prompt, skills, tool contracts, and executor as `../runtime-messages-api/`, and an
approving console. Choose it when your host consumes a finished turn and the SDK's loop is
what you build on.

```
                 Claude Code CLI, started by the SDK
                 loop · caching · Skill tool reading .claude/skills/<flow>/SKILL.md
                            │  mcp__merchant__* calls
                            ▼
   your process   merchant_tools.py: in-process MCP server over MerchantToolExecutor
                  agent.py: make_options() builds the options; run_turn() grounds, reminds, collects
                  MerchantBackend: MockRetailMerchant by default; yours in production
```

## Setup

`scripts/install.sh` installs this package with its dependencies;
`claude-agent-sdk` bundles the CLI it starts. Credentials: `ANTHROPIC_API_KEY`, or an
already authenticated Claude Code installation. Other platforms: `docs/deployment.md`.

## Run

```bash
python merchant-agent/runtime-agent-sdk/main.py                        # chat with the mock store
python merchant-agent/runtime-agent-sdk/main.py --once "how did last week go"
```

The console prints the reply, each presentation payload as JSON, the tools called, and
the cost. In interactive mode it is the approval host: after each turn it asks `y/N` for
every change the turn staged, and `apply_change` succeeds only for a change approved at
that prompt. `--no-host-approval` sets `require_host_approval=False`, so an approval typed
into the chat applies the change; `--once` has no prompt to ask on, so what it stages
stays staged. In code:

```python
from claude_agent_sdk import ClaudeSDKClient
from merchant_agent_sdk import make_options, run_turn

options, toolset = make_options(backend=MyMerchantBackend())     # backend defaults to the mock
async with ClaudeSDKClient(options=options) as client:
    result = await run_turn(client, "Mark down the slow movers", toolset=toolset)
    result.text          # the reply
    result.ui            # [{"component": ..., "payload": ...}] to render
    result.tool_calls    # tool names in call order
    for change in toolset.pending_host_approvals():              # staged, no mark yet
        if operator_approved(change):                            # your surface
            toolset.host_approve(change.change_id)               # then ask the agent to apply it
            ...
            toolset.host_clear(change.change_id)                 # and clear the mark once that turn returns
```

`make_options` also takes `config`, `session_id`, `merchant_id`, `operator`, `max_turns`, and
`skills_dir` (a project's own skills directory in place of `../skills`); `operator` is what the
backend stamps on the changes this conversation stages. The toolset it returns holds the
session's provenance state, the approval marks, and an in-memory `MemoryStore`; a host with
durable memory constructs `MerchantToolset(memory_store=...)` itself and builds the options the
way `agent.py` does.

## What is reused

- Skills: `ensure_project_skills` links `../skills/*` into this directory's gitignored
  `.claude/skills/`, and the options allow the `Skill` tool for those names. The static
  prompt from `merchant_agent.prompt` carries the same index, plus `SKILL_TOOL_ADAPTER`
  (`commerce_common/agent_sdk.py`), which points the model at `Skill` instead of `load_skill`.
- Tools: `merchant_tools.py` registers every contract in `merchant_agent.tools.registry`
  except `load_skill` and `run_analysis`, descriptions and schemas included, and executes
  each call through `MerchantToolExecutor`. The options allow-list those names under
  `permission_mode="dontAsk"` and mount no built-in tool besides `Skill` (plus `Task`, the
  delegation transport, when analysis is enabled).
- Backend: any `MerchantBackend`, passed to `make_options`.

## What differs from the Messages API runtime

- **UI arrives after the turn.** Presentation payloads, including a staged change's preview
  card, are returned in `result.ui`; staged changes are read from
  `toolset.pending_host_approvals()` rather than a stream event.
- **Turn close is a hook.** A post-tool-batch hook ends the turn on a closing component; on
  an older CLI the model writes a closing line instead.
- **Grounding is host-side.** `run_turn` runs the reads the metrics and queue grounding rules
  require and appends the results to the message.
- **Staging reminder is a second pass.** When a change request ends with nothing staged,
  `run_turn` sends the follow-through reminder and merges the result.
- **Analysis is a subagent.** With `enable_analysis` on, `run-analysis` runs over the read
  tools in its own context; the analysis budgets on the config do not apply to it.
- **No Merchant context block.** Store context arrives in tool results (`get_business_snapshot`,
  `recall_memories`), and one tool description is adapted to say so.
- **Not applied here.** Memory extraction (call `toolset.memory`) and `thinking_effort` (set
  `options.effort`).
- **No stray context.** `make_options` stops the CLI from loading any `CLAUDE.md` above the
  working directory.
- **Platform selection.** The CLI's environment; see [`docs/deployment.md`](../../docs/deployment.md).

## Tests

`pytest merchant-agent/runtime-agent-sdk/tests` calls the registered tools in-process
with a scripted client and needs no credentials; the suite also compares the registered
tool surface with `merchant_agent.tools.registry` and the subagent's tools with
`ANALYSIS_READ_TOOLS`, so this package cannot drift behind the core.
