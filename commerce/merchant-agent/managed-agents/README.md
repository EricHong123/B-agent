# merchant-agent/managed-agents

The merchant agent as an Anthropic-hosted agent on the
[Managed Agents API](https://platform.claude.com/docs/en/managed-agents/overview) (beta).
The platform runs the loop and holds the session; the skills, prompt, and tool contracts
are the repo's; your back-office systems stay behind an MCP server you host, which
stages every change and applies one only when the platform's approval prompt has been
answered. The agent sees what that server returns per call and nothing else.

```
your portal  ──user.message──►  hosted agent (agent.yaml: model, system.md, skills)
             ◄──agent.message, agent.custom_tool_use, requires_action──┘   │ MCP over HTTPS, credential from a vault
                                                                          ▼
                                    your infrastructure: merchant-mcp-server -> MerchantBackend
```

| Path | Contents |
|---|---|
| `merchant-agent/agent.yaml` | The manifest: 5 skills, 19 merchant tools, 4 presentation tools |
| `merchant-agent/system.md` | The system prompt, derived from `merchant_agent.prompt.build_static_system`; its header lists what differs |
| [`merchant-mcp-server/`](merchant-mcp-server/) | The reference MCP server over a `MerchantBackend`; the part you replace |
| [`scheduled-digest/`](scheduled-digest/) | A headless digest run on the Messages API runtime, for a job scheduler |
| `../../scripts/deploy_managed_agent.sh` | Resolves the manifest (`commerce_common.manifest`) and posts it; dry run by default |

## Quick start

```bash
scripts/deploy_managed_agent.sh merchant-agent/managed-agents/merchant-agent     # print the /v1/agents body

python merchant-agent/managed-agents/merchant-mcp-server/merchant_mcp_server.py
# Serves 127.0.0.1:8201/mcp; reach it through an HTTPS tunnel or your gateway (see its README).

export ANTHROPIC_API_KEY=<API_KEY>
export MERCHANT_MCP_URL=https://<YOUR_HOST>/mcp
scripts/deploy_managed_agent.sh merchant-agent/managed-agents/merchant-agent --live
```

The live deploy uploads the five skills, creates the agent, and prints its id. Sessions
need an environment and a vault holding the MCP server's credential; the platform matches
the vault entry to the manifest's server by URL.

```bash
H=(-H "content-type: application/json" -H "x-api-key: $ANTHROPIC_API_KEY"
   -H "anthropic-version: 2023-06-01" -H "anthropic-beta: managed-agents-2026-04-01")
curl -sS https://api.anthropic.com/v1/environments "${H[@]}" -d '{"name": "back-office",
  "config": {"type": "cloud", "networking": {"type": "limited", "allow_mcp_servers": true,
             "allowed_hosts": ["<YOUR_HOST>"]}}}'
curl -sS https://api.anthropic.com/v1/sessions "${H[@]}" -d '{"agent": "<AGENT_ID>",
  "environment_id": "<ENVIRONMENT_ID>", "vault_ids": ["<VAULT_ID>"]}'
```

Then post `user.message` events to the session and read its event stream.

## What your portal handles

- `agent.message`: assistant text; render it as chat.
- `agent.custom_tool_use`: a presentation tool call. Validate the payload against
  `merchant_agent/tools/presentation.py`, fill in metric values, alert records, and the
  change diff by id from your own systems (`merchant_agent/enrichment.py` is the
  reference join), render it, and reply with a `user.custom_tool_result`. Every call,
  `present_suggestions` included, needs a reply or the session waits; here the model
  writes a closing line after the chips' result, and previews a staged change with
  `present_change_preview`.
- `session.status_idle` with `stop_reason: requires_action`: an `always_ask` tool is
  waiting. For `apply_change`, the change is already on a preview card; the operator's
  answer there becomes your `user.tool_confirmation`, and the server applies the change
  when it arrives. `save_memory` pauses the same way, so dispatch on the tool name.

The grounding rules in `merchant_agent/grounding.py` and the staging follow-through
reminder in `merchant_agent/gates.py` do not run on this path, because the platform owns
tool choice and the turn; the prompt rules cover those turns.

## Tool permissions

The MCP toolset is deny-by-default: a tool the server adds is unusable until it is enabled
in the manifest. Reads and the `stage_*` tools run without confirmation, because staging
records a proposal and changes nothing live; `discard_change` runs the same way.
`apply_change` and `save_memory` are `always_ask`, and the pause on `apply_change` is
this path's approval surface: the server's `default_config` sets `require_host_approval=False`,
and a config you pass to `build_server` has to set it too, or every apply is held. The
provenance and guardrail checks run on every stage and apply either way.

- **Merchant tools** (from the `merchant` MCP server): `get_business_snapshot`, `query_metrics`, `get_campaign_performance`, `search_listings`, `get_listing`, `get_inventory_alerts`, `get_order_issues`, `get_return_reasons`, `get_pricing_context`, `get_pending_changes`, `recall_memories`, `stage_listing_update`, `stage_price_update`, `stage_inventory_action`, `stage_promotion`, `stage_campaign`, `discard_change`, `save_memory`, `apply_change`.
- **Presentation tools** (custom tools your portal executes): `present_metrics`, `present_digest`, `present_change_preview`, `present_suggestions`.

Of the built-in agent tools only `read` is enabled; the platform loads skill bodies with it.
`run_analysis` is not on this path: the manifest declares no such tool, and `system.md`
carries no analysis rule.

## Keeping the manifest in sync

The manifest references `../../skills/`, so skill edits reach the next deploy. `system.md`
is derived from `merchant_agent.prompt` and the custom tools in `agent.yaml` from
`merchant_agent.tools.registry`; `scripts/check.py` compares both, and the tool lists above,
with their sources. The MCP server reads its descriptions from the registry at startup.

What the server enforces is in [`docs/safety.md`](../../docs/safety.md); its README's
identity section is the change a production deployment makes.
