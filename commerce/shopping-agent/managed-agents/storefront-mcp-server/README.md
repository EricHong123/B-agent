# storefront-mcp-server

The MCP server a hosted shopping agent calls: the storefront tools over a
`StorefrontBackend`, executed by `shopping_agent.executor` with one executor, and so one
provenance record, per connection. Each tool is listed under the registry's description and
input schema, so the hosted agent sees the same contract as the other two paths. It serves the retail example's mock storefront by
default.

```
hosted agent  ──MCP (streamable HTTP)──►  storefront_mcp_server.py  ──►  StorefrontBackend  ──►  your systems
```

| Tool | Kind |
|---|---|
| `search_products` | read; records provenance |
| `get_product_details` | read; records provenance |
| `get_cart` | read |
| `add_to_cart` | write; provenance-gated and capped |
| `update_cart_item` | write; provenance or cart membership; capped |
| `remove_from_cart` | write; provenance or cart membership |
| `get_preferences` | read; profile plus injected memory facts |
| `save_memory` | write; validated and filtered |
| `recall_memories` | read |
| `get_orders` | read; order items count as provenance |
| `get_order_status` | read |
| `search_policies` | read |
| `get_fulfillment_options` | read |

Presentation tools are custom tools in the manifest, executed by the host application, so
none are served here; there is no `load_skill`, because the platform loads skills itself.

## Run

```bash
python shopping-agent/managed-agents/storefront-mcp-server/storefront_mcp_server.py   # 127.0.0.1:8200/mcp
```

Environment: `STOREFRONT_MCP_HOST`, `STOREFRONT_MCP_PORT`, `STOREFRONT_MCP_USER_ID`,
`STOREFRONT_MCP_SESSION_ID`, `STOREFRONT_MCP_MEMORY_FILE`. The server refuses any host
other than loopback unless `STOREFRONT_MCP_UNSAFE_ALLOW_NO_AUTH=1` states that your
authenticating gateway is in front of it (`commerce_common.mcp_server`); during
development, reach it through an HTTPS tunnel that terminates on loopback and rewrites the
`Host` header to `127.0.0.1:<port>` (the server's DNS-rebinding check answers 421 otherwise).

## Your backend

```python
from storefront_mcp_server import build_server

server = build_server(backend=MyStorefrontBackend(), memory_store=MyMemoryStore())
server.run(transport="streamable-http")
```

`build_server` also takes a `ShoppingAgentConfig` (caps, memory settings) and a
`memory_write_filter`. What the executor enforces is listed in
[`docs/safety.md`](../../../docs/safety.md).

## Identity

The reference server acts for one customer named by `STOREFRONT_MCP_USER_ID`. A
production server derives the customer from the authenticated request, builds a
`ShoppingSessionContext` per connection from it, and keys the executor, cart, and memory
by that identity; a user id is never a tool argument. Put the server behind HTTPS with a
credential registered in a Managed Agents vault: one vault credential per customer session,
or a service credential plus a signed customer claim your gateway verifies on each request.

Tests: `pytest shopping-agent/managed-agents/storefront-mcp-server/tests` connects over an
in-memory MCP session and exercises the table above.
