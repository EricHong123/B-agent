# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Where a platform plugs in on both roles: the runtimes' client and the SDK options' environment."""

from __future__ import annotations

import dataclasses

import pytest
from anthropic import (
    AsyncAnthropic,
    AsyncAnthropicBedrock,
    AsyncAnthropicBedrockMantle,
    AsyncAnthropicFoundry,
    AsyncAnthropicVertex,
)
from claude_agent_sdk import ClaudeAgentOptions

import merchant_agent_sdk
import shopping_agent_sdk
from merchant_agent_runtime import MerchantAgent
from shopping_agent_runtime import ShoppingAgent

AGENTS = {"shopping": ShoppingAgent, "merchant": MerchantAgent}
SDKS = {"shopping": shopping_agent_sdk, "merchant": merchant_agent_sdk}

# Placeholder credentials: constructing a client performs no I/O.
CLIENTS = {
    "direct-anthropic-api": (
        lambda: AsyncAnthropic(api_key="stub-key"),
        "claude-sonnet-5",
        "api.anthropic.com",
    ),
    "gcp-vertex": (
        # access_token= sidesteps Application Default Credentials for the stub.
        lambda: AsyncAnthropicVertex(
            project_id="stub-project", region="us-east5", access_token="stub-token"
        ),
        "claude-sonnet-5",
        "aiplatform.googleapis.com",
    ),
    "aws-bedrock-mantle": (
        # The Mantle endpoint serves its own anthropic.-prefixed model ids; the stub keeps the prefix.
        lambda: AsyncAnthropicBedrockMantle(
            aws_region="us-east-1", aws_access_key="stub", aws_secret_key="stub"
        ),
        "anthropic.stub-model-for-tests",
        "bedrock-mantle.us-east-1.api.aws",
    ),
    "aws-bedrock-invoke": (
        # The Invoke API takes cross-region inference-profile ids.
        lambda: AsyncAnthropicBedrock(
            aws_region="us-east-1", aws_access_key="stub", aws_secret_key="stub"
        ),
        "us.anthropic.claude-sonnet-5",
        "bedrock-runtime.us-east-1.amazonaws.com",
    ),
    "microsoft-foundry": (
        # The model is a deployment name in the resource; the default names are first-party ids.
        lambda: AsyncAnthropicFoundry(resource="stub-resource", api_key="stub-key"),
        "claude-sonnet-5",
        "stub-resource.services.ai.azure.com",
    ),
    "in-house-gateway": (
        lambda: AsyncAnthropic(
            base_url="https://llm-gateway.internal.example", auth_token="stub-token"
        ),
        "claude-sonnet-5",
        "llm-gateway.internal.example",
    ),
}

ENVIRONMENTS = {
    "aws-bedrock-invoke": (
        {"CLAUDE_CODE_USE_BEDROCK": "1", "AWS_REGION": "us-east-1"},
        "us.anthropic.claude-sonnet-5",
    ),
    "aws-bedrock-mantle": (
        {"CLAUDE_CODE_USE_MANTLE": "1", "AWS_REGION": "us-east-1"},
        "anthropic.stub-model-for-tests",
    ),
    "gcp-vertex": (
        {
            "CLAUDE_CODE_USE_VERTEX": "1",
            "ANTHROPIC_VERTEX_PROJECT_ID": "stub-project",
            "CLOUD_ML_REGION": "us-east5",
        },
        None,  # first-party model ids pass through unchanged
    ),
    "microsoft-foundry": (
        {
            "CLAUDE_CODE_USE_FOUNDRY": "1",
            "ANTHROPIC_FOUNDRY_RESOURCE": "stub-resource",
            "ANTHROPIC_FOUNDRY_API_KEY": "stub-key",
        },
        None,  # deployment names default to first-party ids
    ),
    "in-house-gateway": (
        {
            "ANTHROPIC_BASE_URL": "https://llm-gateway.internal.example",
            "ANTHROPIC_AUTH_TOKEN": "stub-token",
        },
        None,
    ),
}


@pytest.fixture(params=list(AGENTS))
def role(request) -> str:
    return request.param


@pytest.mark.parametrize("platform", list(CLIENTS))
def test_runtime_binds_the_injected_client_and_the_configured_model(
    role, backend, skills, config, platform
):
    make_client, model, endpoint = CLIENTS[platform]
    client = make_client()
    agent = AGENTS[role](
        backend=backend,
        skills=skills,
        config=config.model_copy(update={"model": model}),
        client=client,
    )
    assert agent.client is client
    assert callable(agent.client.messages.stream) and callable(agent.client.messages.create)
    assert endpoint in str(client.base_url)
    assert agent.config.model == model


def test_sdk_options_expose_env_and_model():
    assert {"env", "model"} <= {field.name for field in dataclasses.fields(ClaudeAgentOptions)}


@pytest.mark.parametrize("platform", list(ENVIRONMENTS))
def test_sdk_options_carry_the_platform_environment(role, platform):
    env, model = ENVIRONMENTS[platform]
    options, _ = SDKS[role].make_options()
    options.env.update(env)
    if model is not None:
        options.model = model
    assert env.items() <= options.env.items()
    assert options.env["CLAUDE_CODE_DISABLE_CLAUDE_MDS"] == "1"
    assert options.model == (model or SDKS[role].default_config().model)
    assert options.system_prompt and options.allowed_tools
