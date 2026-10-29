# shopping-agent/managed-agents

The shopping agent as an Anthropic-hosted agent on the
[Managed Agents API](https://platform.claude.com/docs/en/managed-agents/overview) (beta).
The platform runs the loop and holds the session; the skills, prompt, and tool contracts
are the repo's; your commerce data stays behind an MCP server you host. The agent sees
what that server returns per call and nothing else.

```
your app  ──user.message──►  hosted agent (agent.yaml: model, system.md, skills)
          ◄──agent.message, agent.custom_tool_use──┘        │ MCP over HTTPS, credential from a vault
                                                            ▼
                                   your infrastructure: storefront-mcp-server -> StorefrontBackend
```

| Path | Contents |
|---|---|
| `shopping-agent/agent.yaml` | The manifest: 5 skills, 13 storefront tools, 7 presentation tools |
| `shopping-agent/system.md` | The system prompt, derived from `shopping_agent.prompt.build_static_system`; its header lists what differs |
| [`storefront-mcp-server/`](storefront-mcp-server/) | The reference MCP server over a `StorefrontBackend`; the part you replace |
| `../../scripts/deploy_managed_agent.sh` | Resolves the manifest (`commerce_common.manifest`) and posts it; dry run by default |

## Quick start

```bash
scripts/deploy_managed_agent.sh shopping-agent/managed-agents/shopping-agent     # print the /v1/agents body

python shopping-agent/managed-agents/storefront-mcp-server/storefront_mcp_server.py
# Serves 127.0.0.1:8200/mcp; reach it through an HTTPS tunnel or your gateway (see its README).

export ANTHROPIC_API_KEY=<API_KEY>
export STOREFRONT_MCP_URL=https://<YOUR_HOST>/mcp
scripts/deploy_managed_agent.sh shopping-agent/managed-agents/shopping-agent --live
```

The live deploy uploads the five skills, creates the agent, and prints its id. Sessions
need an environment and a vault holding the MCP server's credential; the platform matches
the vault entry to the manifest's server by URL.

```bash
H=(-H "content-type: application/json" -H "x-api-key: $ANTHROPIC_API_KEY"
   -H "anthropic-version: 2023-06-01" -H "anthropic-beta: managed-agents-2026-04-01")
curl -sS https://api.anthropic.com/v1/environments "${H[@]}" -d '{"name": "commerce",
  "config": {"type": "cloud", "networking": {"type": "limited", "allow_mcp_servers": true,
             "allowed_hosts": ["<YOUR_HOST>"]}}}'
curl -sS https://api.anthropic.com/v1/sessions "${H[@]}" -d '{"agent": "<AGENT_ID>",
  "environment_id": "<ENVIRONMENT_ID>", "vault_ids": ["<VAULT_ID>"]}'
```

Then post `user.message` events to the session and read its event stream.

## What your application handles

- `agent.message`: assistant text; render it as chat.
- `agent.custom_tool_use`: a presentation tool call. Validate the payload against
  `shopping_agent/tools/presentation.py`, fill in titles, prices, and order data by id from
  your own systems (`shopping_agent/enrichment.py` is the reference join), render it, and
  reply with a `user.custom_tool_result`. Every call, `present_suggestions` included, needs
  a reply or the session waits; here the model writes a closing line after the chips'
  result.
- `session.status_idle` with `stop_reason: requires_action`: a write is waiting for
  confirmation; show your UI and reply with a `user.tool_confirmation`.

The grounding rules in `shopping_agent/grounding.py` do not run on this path, because the
platform owns tool choice; the prompt rules cover those turns.

## Tool permissions

The MCP toolset is deny-by-default: a tool the server adds is unusable until it is enabled
in the manifest. Reads run without confirmation; writes pause the session (`always_ask`),
and the server enforces provenance and caps whichever policy the manifest sets.

- **Storefront tools** (from the `storefront` MCP server): `search_products`, `get_product_details`, `get_cart`, `add_to_cart`, `update_cart_item`, `remove_from_cart`, `get_preferences`, `save_memory`, `recall_memories`, `get_orders`, `get_order_status`, `search_policies`, `get_fulfillment_options`.
- **Presentation tools** (custom tools your app executes): `present_products`, `present_comparison`, `present_plan`, `present_guide`, `present_order_status`, `checkout`, `present_suggestions`.

Of the built-in agent tools only `read` is enabled; the platform loads skill bodies with it.

## Keeping the manifest in sync

The manifest references `../../skills/`, so skill edits reach the next deploy. `system.md`
is derived from `shopping_agent.prompt` and the custom tools in `agent.yaml` from
`shopping_agent.tools.registry`; `scripts/check.py` compares both, and the tool lists above,
with their sources. The MCP server reads its descriptions from the registry at startup.

What the server enforces is in [`docs/safety.md`](../../docs/safety.md); its README's
identity section is the change a production deployment makes.
