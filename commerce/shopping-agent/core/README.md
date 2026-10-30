# shopping-agent/core (package `shopping_agent`)

Everything the shopping agent's three paths agree on. The turn loops live in
`../runtime-messages-api/` and `../runtime-agent-sdk/`; the hosted path's server is in
`../managed-agents/`. A deployment implements `StorefrontBackend` and constructs a
`ShoppingAgentConfig`; the rest is consumed as is. [`docs/backends.md`](../../docs/backends.md) covers mapping a catalog
with options and variants onto `Product`.

| Module | Holds |
|---|---|
| `types.py` | Products (a family record's `options`, its `variants` with `option_values` and `variant_of`), cart, orders, policies, disclosures, `ShoppingSessionContext`, `ShoppingSessionState` |
| `backend.py` | `StorefrontBackend`: 11 required methods, plus `get_account_context`, `get_disclosure`, and `checkout_handoff`; `NotOffered` (one item or seller not served) and `Unavailable` (in the catalog, out of stock) |
| `config.py` | `ShoppingAgentConfig`: capabilities, the `enable_*` system switches, cart caps, grounding lexicons |
| `prompt.py` | `build_static_system` (cached) and `build_dynamic_context` (fenced, per request) |
| `tools/registry.py` | The tool contracts, in a fixed order |
| `tools/presentation.py` | Payload schemas for the built-in presentation tools |
| `enrichment.py` | The built-in components joined to session records; partial payloads while streaming |
| `gates.py` | Cart provenance, the options hold (a family is added as one of its variants), quantity caps, the per-session write lock |
| `grounding.py` | The policy, order, and catalog grounding rules |
| `serialization.py` | The payloads read tools return |
| `fencing.py`, `memory.py` | The `storefront_data` fence and the extraction prompt |
| `executor.py` | `ShoppingToolExecutor`: one handler per tool over the shared frame; subclassed and passed on as `executor_class` |

Tests: `pytest shopping-agent/core/tests`.
