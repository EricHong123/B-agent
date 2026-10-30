# Deployment platforms

The code calls the Anthropic API by default. Each runtime path has one place where a
deployment points it at GCP Vertex AI, AWS Bedrock, Microsoft Foundry, or an in-house
gateway instead. Everything here applies to both roles; the examples use the shopping
names, and `MerchantAgent`, `merchant_agent_sdk`, and `merchant-agent/managed-agents/`
substitute one for one.

## Support matrix

| Path | Anthropic API | GCP Vertex AI | AWS Bedrock | Microsoft Foundry | In-house gateway |
|---|---|---|---|---|---|
| Messages API runtimes | Yes | Yes | Yes | Yes | Yes |
| Agent SDK runtimes | Yes | Yes | Yes | Yes | Yes |
| Managed Agents | Yes | No | No¹ | No | Yes² |
| Merchant analysis, hosted code execution | Yes | No | No | Yes³ | No |
| Merchant analysis, `execute_analysis_query` | Yes | Yes | Yes | Yes | Yes |

How each path selects the platform:

| Path | Where set | Anthropic API | GCP Vertex AI | AWS Bedrock | Microsoft Foundry | In-house gateway |
|---|---|---|---|---|---|---|
| Messages API runtimes | `client=` on the agent | default | `AsyncAnthropicVertex` | `AsyncAnthropicBedrockMantle` or `AsyncAnthropicBedrock` | `AsyncAnthropicFoundry` | `AsyncAnthropic(base_url=..., auth_token=...)` |
| Agent SDK runtimes | `options.env` | default | `CLAUDE_CODE_USE_VERTEX=1` | `CLAUDE_CODE_USE_BEDROCK=1` or `CLAUDE_CODE_USE_MANTLE=1` | `CLAUDE_CODE_USE_FOUNDRY=1` | `ANTHROPIC_BASE_URL` |
| Managed Agents | `ANTHROPIC_API_URL` for the deploy script | default | — | — | — | `ANTHROPIC_API_URL` |

¹ See the AWS note below. ² Through a pass-through proxy for the deploy script and session endpoints; see
"Managed Agents: the endpoint". ³ Foundry deployments hosted on Anthropic
only.

The two analysis rows apply to merchant deployments with `enable_analysis` on. Hosted code
execution (`analysis_use_code_execution`) mounts the `code_execution_20260120` server tool,
which the Anthropic API serves; a Foundry deployment hosted on Anthropic also serves it.
`MerchantBackend.execute_analysis_query` runs in your infrastructure and returns an
ordinary tool result, so it works everywhere. The retail example uses the query method and
mounts the sandbox only when `MERCHANT_ANALYSIS_CODE_EXECUTION=1` is set.

AWS note: Managed Agents runs on Anthropic-operated infrastructure, so it has no Vertex,
Bedrock, or Foundry variant. On AWS it is available through
[Claude Platform on AWS](https://platform.claude.com/docs/en/build-with-claude/claude-platform-on-aws),
which serves the same `/v1` endpoints with AWS authentication, an `anthropic-workspace-id`
header, and first-party model ids. The deploy script sends neither; follow the platform
guide for that route.

## Model ids

The model is a string in the config. Each role config has `model` and `memory_model`; the
merchant config adds `analysis_model`. The SDK runtimes copy the model into their options,
and the manifests set it in `agent.yaml`. Nothing else reads the string, so a platform move
is a config change. Id grammar differs by platform; confirm against your
platform's catalog.

| Field | Repo default | Anthropic API, gateways | GCP Vertex AI | AWS Bedrock (Mantle) | AWS Bedrock (Invoke API) | Microsoft Foundry |
|---|---|---|---|---|---|---|
| Shopping `model` | `claude-sonnet-5` | `claude-sonnet-5` | `claude-sonnet-5` | `anthropic.<SERVED_MODEL>` | `<INFERENCE_PROFILE_ID>` | `claude-sonnet-5` |
| Merchant `model` | `claude-opus-5` | `claude-opus-5` | `claude-opus-5` | `anthropic.<SERVED_MODEL>` | `<INFERENCE_PROFILE_ID>` | `claude-opus-5` |
| `memory_model` | `claude-haiku-4-5-20251001` | `claude-haiku-4-5-20251001` | `claude-haiku-4-5@20251001` | `anthropic.<SERVED_MODEL>` | `<INFERENCE_PROFILE_ID>` | `claude-haiku-4-5` |

- Vertex writes dated snapshots with `@`.
- Bedrock has two endpoints. Mantle speaks the Messages API and takes dateless
  `anthropic.` ids from its own lineup; the Invoke API takes inference-profile ids from your account's catalog
  (region-prefixed, dated, `-v1:0` suffixed).
- Foundry takes the name of a deployment in your resource; the values above are the
  defaults, which match the dateless first-party ids.
- Managed Agents takes first-party ids.
- All three model fields go through the same client, so all three must exist on the
  platform it targets.

## Messages API runtimes: the `client` argument

`ShoppingAgent` and `MerchantAgent` take an optional `client`. Without one they construct
`AsyncAnthropic`, which reads `ANTHROPIC_API_KEY`, `ANTHROPIC_AUTH_TOKEN`, and
`ANTHROPIC_BASE_URL` from the environment; exporting the last two points the example APIs
at a gateway. With one, every call uses it: the turn loop (`messages.stream`), memory
extraction, and the analysis delegate (`messages.create`). Any async client in the
`anthropic` package fits. The parameter is annotated `AsyncAnthropic`, so a type checker
needs a `cast` for the platform classes.

```python
from pathlib import Path

from anthropic import (
    AsyncAnthropic,
    AsyncAnthropicBedrockMantle,
    AsyncAnthropicFoundry,
    AsyncAnthropicVertex,
)
from shopping_agent import ShoppingAgentConfig
from shopping_agent_runtime import ShoppingAgent

common = dict(backend=your_backend, skills_dir=Path("shopping-agent/skills"))

# GCP Vertex AI: pip install "anthropic[vertex]"; Application Default Credentials.
agent = ShoppingAgent(
    **common,
    config=ShoppingAgentConfig(memory_model="claude-haiku-4-5@20251001"),
    client=AsyncAnthropicVertex(project_id="your-project", region="global"),
)

# AWS Bedrock, Mantle endpoint: the standard AWS credential chain.
agent = ShoppingAgent(
    **common,
    config=ShoppingAgentConfig(
        model="anthropic.your-served-model", memory_model="anthropic.claude-haiku-4-5"
    ),
    client=AsyncAnthropicBedrockMantle(aws_region="us-east-1"),
)

# Microsoft Foundry: an Azure API key, or azure_ad_token_provider= for Entra ID.
agent = ShoppingAgent(
    **common,
    config=ShoppingAgentConfig(memory_model="claude-haiku-4-5"),
    client=AsyncAnthropicFoundry(resource="your-resource", api_key="your-azure-key"),
)

# In-house gateway: it must serve /v1/messages with SSE streaming.
agent = ShoppingAgent(
    **common,
    client=AsyncAnthropic(base_url="https://llm-gateway.internal.example", auth_token="your-token"),
)
```

Endpoints that serve OpenAI-compatible Chat Completions instead of `/v1/messages` take
`commerce_common.openai_compat.OpenAICompatibleClient`. It translates each request (tools
to functions, `tool_use` and `tool_result` blocks to tool calls and `tool` messages) and
streams the reply back as Messages API events, so eager dispatch, partial frames, and the
salvage of unparsable tool input behave as on the first-party API. Cache breakpoints,
thinking, and server tools (web search, code execution) do not carry over, and the
model ids are the endpoint's own.

```python
from commerce_common.openai_compat import OpenAICompatibleClient

agent = ShoppingAgent(
    **common,
    config=ShoppingAgentConfig(model="deepseek-chat", memory_model="deepseek-chat"),
    client=OpenAICompatibleClient(base_url="https://api.deepseek.com/v1", api_key="your-key"),
)
```

The example APIs build this client from `MODEL_PROVIDER` and its companions
(`examples/demo_common/model_provider.py`, `.env.example`): presets for OpenAI, DeepSeek,
Qwen (DashScope), Moonshot, Zhipu GLM, and Ollama, and `openai-compatible` for any other
endpoint. The web apps' model settings panel writes the same values to `.model-settings.json`
through `/api/model-settings` (`examples/demo_common/model_settings.py`); a deployment whose
model is fixed by its environment sets `DEMO_MODEL_SETTINGS=0`, which makes those routes
read-only.

The packages declare `anthropic>=0.91`, the release that adds `AsyncAnthropicBedrockMantle`,
the newest of the client classes above.

## Agent SDK runtimes: the CLI environment

The SDK runtimes construct no HTTP client. `claude-agent-sdk` starts the Claude Code CLI,
and the CLI selects the platform from its environment. `make_options()` returns
`(options, toolset)`; add the platform variables to `options.env` before opening the client.
The SDK overlays `env` on the inherited environment, so only the platform variables need
listing.

```python
from claude_agent_sdk import ClaudeSDKClient
from shopping_agent_sdk import make_options

options, toolset = make_options()
options.env.update({"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "us-east-1"})
options.model = "us.anthropic.claude-sonnet-5"
async with ClaudeSDKClient(options=options) as client:
    ...
```

| Target | Required | Credentials | Model ids | Optional |
|---|---|---|---|---|
| AWS Bedrock, Invoke API | `CLAUDE_CODE_USE_BEDROCK=1` | AWS standard chain | inference-profile ids | `ANTHROPIC_BEDROCK_BASE_URL` |
| AWS Bedrock, Mantle | `CLAUDE_CODE_USE_MANTLE=1` | AWS standard chain | `anthropic.` ids | `ANTHROPIC_BEDROCK_MANTLE_BASE_URL`, `CLAUDE_CODE_SKIP_MANTLE_AUTH`⁴ |
| GCP Vertex AI | `CLAUDE_CODE_USE_VERTEX=1`, `ANTHROPIC_VERTEX_PROJECT_ID`, `CLOUD_ML_REGION` | Application Default Credentials | `@`-dated ids | `ANTHROPIC_VERTEX_BASE_URL` |
| Microsoft Foundry | `CLAUDE_CODE_USE_FOUNDRY=1`, `ANTHROPIC_FOUNDRY_RESOURCE` or `ANTHROPIC_FOUNDRY_BASE_URL` | `ANTHROPIC_FOUNDRY_API_KEY`, or Entra ID via the Azure default chain | deployment names | `ANTHROPIC_DEFAULT_SONNET_MODEL`, `ANTHROPIC_DEFAULT_OPUS_MODEL`⁵ |
| In-house gateway | `ANTHROPIC_BASE_URL` | `ANTHROPIC_AUTH_TOKEN` or `ANTHROPIC_API_KEY` | first-party ids | `ANTHROPIC_CUSTOM_HEADERS` |

⁴ Set to `1` when a gateway signs the requests. ⁵ Pin the deployment names the CLI uses
for its Sonnet and Opus calls.

Set `ANTHROPIC_DEFAULT_HAIKU_MODEL` when the platform needs its own id for the CLI's
small-model calls. These variables belong to Claude Code; its documentation is the
reference.

## Managed Agents: the endpoint

`scripts/deploy_managed_agent.sh` reads `ANTHROPIC_API_KEY` and posts to `ANTHROPIC_API_URL`
(default `https://api.anthropic.com`; the other two paths read `ANTHROPIC_BASE_URL`). A gateway at that address must proxy `/v1/skills` (multipart),
`/v1/agents`, and, for your host application, `/v1/environments`, `/v1/sessions`, and the
session event stream, with the `anthropic-beta` headers intact. A gateway that fronts only
`/v1/messages` does not serve this path.

```bash
# Dry run against a gateway (the default); add --live to deploy.
ANTHROPIC_API_URL=https://llm-gateway.internal.example \
  scripts/deploy_managed_agent.sh shopping-agent/managed-agents/shopping-agent
```

## What the tests cover

`tests/test_platform_seams.py` constructs each platform client with placeholder credentials
and checks that both Messages API runtimes bind it, and that each environment above reaches
`ClaudeAgentOptions` in both SDK runtimes. `scripts/verify_all.py` runs both deploy dry
runs. No test holds cloud credentials, so no live platform conversation runs here; run one
on your platform before relying on it. To drive either agent with no credentials at all,
script the model with `commerce_common.testing.FakeClient`.
