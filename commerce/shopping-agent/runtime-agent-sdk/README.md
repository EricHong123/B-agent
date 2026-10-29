# shopping-agent/runtime-agent-sdk (package `shopping_agent_sdk`)

The shopping agent on the [Claude Agent SDK](https://pypi.org/project/claude-agent-sdk/).
The SDK runs the loop, caching, and skill loading; this package supplies the same static
prompt, skills, tool contracts, and executor as `../runtime-messages-api/`, and a console.
Choose it when your host consumes a finished turn and the SDK's loop is what you build on.

```
                 Claude Code CLI, started by the SDK
                 loop · caching · Skill tool reading .claude/skills/<flow>/SKILL.md
                            │  mcp__storefront__* calls
                            ▼
   your process   shopping_tools.py: in-process MCP server over ShoppingToolExecutor
                  agent.py: make_options() builds the options; run_turn() grounds and collects
                  StorefrontBackend: MockRetail by default; yours in production
```

## Setup

`scripts/install.sh` installs this package with its dependencies;
`claude-agent-sdk` bundles the CLI it starts. Credentials: `ANTHROPIC_API_KEY`, or an
already authenticated Claude Code installation. Other platforms: `docs/deployment.md`.

## Run

```bash
python shopping-agent/runtime-agent-sdk/main.py                       # chat with the mock store
python shopping-agent/runtime-agent-sdk/main.py --once "a light tent for two under $250"
```

The console prints the reply, each presentation payload as JSON, the tools called, and
the cost. In code:

```python
from claude_agent_sdk import ClaudeSDKClient
from shopping_agent_sdk import make_options, run_turn

options, toolset = make_options(backend=MyStorefrontBackend())   # backend defaults to the mock
async with ClaudeSDKClient(options=options) as client:
    result = await run_turn(client, "I need a tent for two people", toolset=toolset)
    result.text          # the reply
    result.ui            # [{"component": ..., "payload": ...}] to render
    result.tool_calls    # tool names in call order
```

`make_options` also takes `config`, `session_id`, `user_id`, `max_turns`, and `skills_dir` (a
project's own skills directory in place of `../skills`). The toolset it returns
holds the session's provenance state and an in-memory `MemoryStore`; a host with durable
memory constructs `ShoppingToolset(memory_store=...)` itself and builds the options the way
`agent.py` does.

## What is reused

- Skills: `ensure_project_skills` links `../skills/*` into this directory's gitignored
  `.claude/skills/`, and the options allow the `Skill` tool for those names. The static
  prompt from `shopping_agent.prompt` carries the same index, plus `SKILL_TOOL_ADAPTER`
  (`commerce_common/agent_sdk.py`), which points the model at `Skill` instead of `load_skill`.
- Tools: `shopping_tools.py` registers every contract in `shopping_agent.tools.registry`
  except `load_skill`, descriptions and schemas included, and executes each call through
  `ShoppingToolExecutor`. The options allow-list those names under `permission_mode="dontAsk"`
  and mount no built-in tool besides `Skill`.
- Backend: any `StorefrontBackend`, passed to `make_options`.

## What differs from the Messages API runtime

- **UI arrives after the turn.** Presentation payloads are collected on the toolset and
  returned in `result.ui`; there is no partial-card stream.
- **Turn close is a hook.** A post-tool-batch hook ends the turn on a closing component; on
  an older CLI the model writes a closing line instead.
- **Grounding is host-side.** `run_turn` runs the reads the order and catalog grounding rules
  require and appends the results to the message; the terms rule stays a prompt rule.
- **No Session context block.** The profile, saved memory, and cart arrive in the
  `get_preferences` result, and two tool descriptions are adapted to say so.
- **Not applied here.** Memory extraction (call `toolset.memory`), `thinking_effort` (set
  `options.effort`), and `enable_web_search` (add the CLI's web tool).
- **No stray context.** `make_options` stops the CLI from loading any `CLAUDE.md` above the
  working directory.
- **Platform selection.** The CLI's environment; see [`docs/deployment.md`](../../docs/deployment.md).

## Tests

`pytest shopping-agent/runtime-agent-sdk/tests` calls the registered tools in-process and
needs no credentials; the suite also compares the registered tool surface with
`shopping_agent.tools.registry`, so this package cannot drift behind the core.
