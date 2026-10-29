# merchant-mcp-server

The MCP server a hosted merchant agent calls: the merchant tools over a
`MerchantBackend`, executed by `merchant_agent.executor` with one executor, and so one
provenance record, per connection. Each tool is listed under the registry's description and
input schema, so the hosted agent sees the same contract as the other two paths. It serves the retail example's mock merchant by
default.

```
hosted agent  ──MCP (streamable HTTP)──►  merchant_mcp_server.py  ──►  MerchantBackend  ──►  your systems
```

| Tool | Kind |
|---|---|
| `get_business_snapshot` | read; records the values `present_metrics` resolves |
| `query_metrics` | read; likewise |
| `get_campaign_performance` | read; records campaign provenance |
| `search_listings` | read; records listing provenance |
| `get_listing` | read; records provenance and the full-record read an edit needs |
| `get_inventory_alerts` | read |
| `get_order_issues` | read |
| `get_return_reasons` | read; counts computed in `merchant_agent.returns` |
| `get_pricing_context` | read |
| `get_pending_changes` | read; records change provenance |
| `recall_memories` | read |
| `stage_listing_update` | staged write; provenance plus a `get_listing` read; guardrails |
| `stage_price_update` | staged write; provenance; guardrails |
| `stage_inventory_action` | staged write; provenance; guardrails |
| `stage_promotion` | staged write; provenance; depth cap; guardrails |
| `stage_campaign` | staged write; provenance when it names a campaign; guardrails |
| `discard_change` | write; change provenance |
| `save_memory` | write; validated and filtered; `always_ask` |
| `apply_change` | live write; change provenance; guardrails re-checked; `always_ask` |

Guardrails run when the backend stages (`ChangeLedger`, `merchant_agent.changes`) and in
`check_apply_change` (`merchant_agent.gates`). Presentation tools are custom tools in the
manifest, executed by the portal, so none are served here and `stage_shows_preview` is off;
there is no `load_skill`, because the platform loads skills itself, and no `run_analysis`.

## Run

```bash
python merchant-agent/managed-agents/merchant-mcp-server/merchant_mcp_server.py   # 127.0.0.1:8201/mcp
```

Environment: `MERCHANT_MCP_HOST`, `MERCHANT_MCP_PORT`, `MERCHANT_MCP_MERCHANT_ID`,
`MERCHANT_MCP_OPERATOR`, `MERCHANT_MCP_SESSION_ID`, `MERCHANT_MCP_MEMORY_FILE`. The server
refuses any host other than loopback unless `MERCHANT_MCP_UNSAFE_ALLOW_NO_AUTH=1` states
that your authenticating gateway is in front of it (`commerce_common.mcp_server`); during
development, reach it through an HTTPS tunnel that terminates on loopback and rewrites the
`Host` header to `127.0.0.1:<port>` (the server's DNS-rebinding check answers 421 otherwise).

## Your backend

```python
from merchant_mcp_server import build_server

server = build_server(backend=MyMerchantBackend(), memory_store=MyMemoryStore())
server.run(transport="streamable-http")
```

`build_server` also takes a `MerchantAgentConfig` (used as given; apply re-checks its
guardrail limits, so keep them the ones the backend stages under) and a
`memory_write_filter`. `default_config` sets `require_host_approval=False`, because on
this path the approval is the platform's `always_ask` prompt on `apply_change`; a config
you pass is used as given, so set `require_host_approval=False` in it too, or every apply
is held (the server prints a notice at startup). What the executor enforces is listed in
[`docs/safety.md`](../../../docs/safety.md).

## Identity

The reference server acts for one store and one operator, `MERCHANT_MCP_MERCHANT_ID` and
`MERCHANT_MCP_OPERATOR`; the operator is what the ledger stamps on every change. A
production server derives both from the authenticated request, builds a
`MerchantSessionContext` per connection from them, and keys the executor, the ledger, and
memory by that identity; neither is ever a tool argument. Put the server behind HTTPS
with a credential registered in a Managed Agents vault.

Tests: `pytest merchant-agent/managed-agents/merchant-mcp-server/tests` connects over an
in-memory MCP session and exercises the table above.
