# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

from __future__ import annotations

import pytest
from anthropic import AsyncAnthropic

from commerce_common.openai_compat import OpenAICompatibleClient
from demo_common.host import chat_error_text, reply_language
from demo_common.model_provider import (
    ModelSettings,
    apply_model_settings,
    clear_settings,
    model_client,
    model_config_fields,
    resolve_provider,
    save_settings,
    settings_path,
)

VARIABLES = (
    "MODEL_PROVIDER",
    "MODEL_API_KEY",
    "MODEL_BASE_URL",
    "MODEL_NAME",
    "MODEL_FAST_NAME",
    "DEEPSEEK_API_KEY",
    "ANTHROPIC_API_KEY",
)


@pytest.fixture(autouse=True)
def clean_env(monkeypatch, tmp_path):
    for name in VARIABLES:
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEMO_MODEL_SETTINGS_FILE", str(tmp_path / "model-settings.json"))


def test_anthropic_is_the_default_on_the_sdks_own_credential_chain():
    provider = resolve_provider()
    assert provider.is_anthropic and not provider.has_key() and provider.source == "env"
    assert isinstance(model_client().current(), AsyncAnthropic)
    assert model_config_fields() == {}


def test_a_preset_supplies_endpoint_models_and_its_usual_key(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "deepseek")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "k")
    provider = resolve_provider()
    assert provider.has_key() and provider.base_url.startswith("https://api.deepseek.com")
    assert isinstance(model_client().current(), OpenAICompatibleClient)
    assert model_config_fields() == {"model": "deepseek-chat", "memory_model": "deepseek-chat"}


def test_saved_settings_replace_the_environment_until_cleared(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("MODEL_NAME", "from-env")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "preset-key")
    client = model_client()
    first = client.current()
    save_settings(ModelSettings(provider="deepseek", model=" reasoner "))
    provider = resolve_provider()
    assert provider.source == "page" and provider.name == "deepseek"
    assert provider.model == "reasoner" and provider.api_key == "preset-key"
    assert client.current() is not first and client.current() is client.current()
    assert oct(settings_path().stat().st_mode & 0o777) == "0o600"
    with pytest.raises(ValueError, match="is not one of"):
        save_settings(ModelSettings(provider="nope"))
    assert resolve_provider().name == "deepseek"
    clear_settings()
    assert resolve_provider().model == "from-env" and resolve_provider().source == "env"


def test_a_running_agent_takes_the_saved_model_names_on_its_next_turn():
    from commerce_common.testing import FakeClient
    from shopping_agent import ShoppingAgentConfig
    from shopping_agent_runtime import ShoppingAgent

    agent = ShoppingAgent(backend=None, config=ShoppingAgentConfig(), client=FakeClient([]))
    default = ShoppingAgentConfig().model
    save_settings(ModelSettings(provider="ollama", model="local-big", fast_model="local-small"))
    apply_model_settings(agent)
    assert agent.config.model == "local-big" and agent.memory.model == "local-small"
    clear_settings()
    apply_model_settings(agent)
    assert agent.config.model == default


def test_model_name_overrides_both_models_unless_a_fast_one_is_named(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "openai")
    monkeypatch.setenv("MODEL_NAME", "big")
    assert model_config_fields() == {"model": "big", "memory_model": "big"}
    monkeypatch.setenv("MODEL_FAST_NAME", "small")
    assert model_config_fields()["memory_model"] == "small"
    assert resolve_provider().max_tokens_field == "max_completion_tokens"


@pytest.mark.parametrize(
    ("env", "message"),
    [
        ({"MODEL_PROVIDER": "nope"}, "is not one of"),
        ({"MODEL_PROVIDER": "openai-compatible"}, "needs MODEL_BASE_URL"),
        ({"MODEL_PROVIDER": "ollama"}, "needs MODEL_NAME"),
    ],
)
def test_incomplete_settings_fail_at_startup(monkeypatch, env, message):
    for name, value in env.items():
        monkeypatch.setenv(name, value)
    with pytest.raises(ValueError, match=message):
        resolve_provider()


def test_chat_errors_name_the_provider_in_the_requested_language(monkeypatch):
    monkeypatch.setenv("MODEL_PROVIDER", "deepseek")
    provider = resolve_provider()
    english = chat_error_text("no_key", "en", provider, "examples/retail/.env")
    chinese = chat_error_text("no_key", "zh", provider, "examples/retail/.env")
    assert "DeepSeek" in english and "DEEPSEEK_API_KEY" in english
    assert "DeepSeek" in chinese and "密钥" in chinese
    assert reply_language("zh") == "Simplified Chinese" and reply_language(None) is None


def test_the_reply_language_reaches_both_context_blocks():
    from merchant_agent.prompt import build_dynamic_context as merchant_context
    from shopping_agent.prompt import build_dynamic_context as shopping_context

    shopping = shopping_context(
        preferences=None, memory_facts=[], cart=None, page=None, reply_language="Simplified Chinese"
    )
    merchant = merchant_context(
        merchant_context=None, memory_facts=[], reply_language="Simplified Chinese"
    )
    assert '"reply_language": "Simplified Chinese"' in shopping
    assert '"reply_language": "Simplified Chinese"' in merchant
    assert "reply_language" not in shopping_context(
        preferences=None, memory_facts=[], cart=None, page=None
    )


@pytest.fixture
def settings_api():
    from fastapi.testclient import TestClient

    from demo_common.host import build_app

    return TestClient(build_app("test"), base_url="http://localhost")


def test_the_settings_routes_take_a_key_and_never_return_it(settings_api, monkeypatch):
    secret = "k-" + "9" * 20 + "WXYZ"
    read = settings_api.get("/api/model-settings").json()
    assert read["provider"] == "anthropic" and read["source"] == "env" and read["editable"]
    assert {row["name"] for row in read["presets"]} >= {"anthropic", "deepseek", "ollama"}
    saved = settings_api.put(
        "/api/model-settings", json={"provider": "deepseek", "api_key": secret}
    ).json()
    assert saved["source"] == "page" and saved["has_key"] and saved["key_preview"] == "…WXYZ"
    assert secret not in settings_api.get("/api/model-settings").text
    # A save that leaves the key out keeps it; an empty key removes it.
    kept = settings_api.put("/api/model-settings", json={"provider": "deepseek", "model": "m2"})
    assert kept.json()["has_key"] and kept.json()["model"] == "m2"
    cleared = settings_api.put("/api/model-settings", json={"provider": "deepseek", "api_key": ""})
    assert not cleared.json()["has_key"]
    bad = settings_api.put("/api/model-settings", json={"provider": "openai-compatible"})
    assert bad.status_code == 422 and bad.json()["detail"] == "This provider needs an endpoint."
    test = settings_api.post("/api/model-settings/test").json()
    assert not test["ok"] and test["code"] == "no_key" and "No API key" in test["error"]
    keyless = settings_api.put("/api/model-settings", json={"provider": "ollama", "model": "m"})
    assert not keyless.json()["has_key"] and not keyless.json()["key_required"]
    assert settings_api.delete("/api/model-settings").json()["source"] == "env"
    monkeypatch.setenv("DEMO_MODEL_SETTINGS", "0")
    assert settings_api.put("/api/model-settings", json={"provider": "ollama"}).status_code == 403
    assert not settings_api.get("/api/model-settings").json()["editable"]


async def test_models_come_from_the_providers_list_endpoint():
    import httpx

    from demo_common.model_settings import fetch_models

    seen = []

    def reply(request: httpx.Request) -> httpx.Response:
        seen.append((str(request.url), dict(request.headers)))
        if request.url.host == "api.anthropic.com":
            return httpx.Response(200, json={"data": [{"id": "model-b"}, {"id": "model-a"}]})
        return httpx.Response(
            200, json={"data": [{"id": "chat"}, {"id": "reasoner"}, {"id": "chat"}]}
        )

    transport = httpx.MockTransport(reply)
    assert await fetch_models("deepseek", "https://api.example.test/v1", "k1", transport) == [
        "chat",
        "reasoner",
    ]
    assert seen[0][0] == "https://api.example.test/v1/models"
    assert seen[0][1]["authorization"] == "Bearer k1"
    assert await fetch_models("anthropic", "https://api.anthropic.com", "k2", transport) == [
        "model-a",
        "model-b",
    ]
    assert seen[1][1]["x-api-key"] == "k2"


def test_the_models_route_uses_the_typed_key_then_the_saved_or_env_one(settings_api, monkeypatch):
    import demo_common.model_settings as routes

    calls = []

    async def fake_fetch(name, endpoint, key, transport=None):
        calls.append((name, endpoint, key))
        return ["m-1", "m-2"]

    monkeypatch.setattr(routes, "fetch_models", fake_fetch)
    typed = settings_api.post(
        "/api/model-settings/models", json={"provider": "deepseek", "api_key": "typed"}
    )
    assert typed.json() == {"ok": True, "label": "DeepSeek", "models": ["m-1", "m-2"]}
    assert calls[-1] == ("deepseek", "https://api.deepseek.com/v1", "typed")
    missing = settings_api.post("/api/model-settings/models", json={"provider": "deepseek"}).json()
    assert missing == {"ok": False, "code": "no_key", "label": "DeepSeek"}
    monkeypatch.setenv("DEEPSEEK_API_KEY", "from-env")
    settings_api.post("/api/model-settings/models", json={"provider": "deepseek"})
    assert calls[-1][2] == "from-env"
    local = settings_api.post(
        "/api/model-settings/models",
        json={"provider": "ollama", "base_url": "http://localhost:9/v1/"},
    )
    assert local.json()["ok"] and calls[-1] == ("ollama", "http://localhost:9/v1", None)
    assert (
        settings_api.post("/api/model-settings/models", json={"provider": "nope"}).json()["code"]
        == "invalid"
    )


def test_a_refused_or_unreachable_listing_comes_back_as_a_code(settings_api, monkeypatch):
    import httpx

    import demo_common.model_settings as routes

    async def refused(name, endpoint, key, transport=None):
        request = httpx.Request("GET", endpoint)
        raise httpx.HTTPStatusError(
            "no", request=request, response=httpx.Response(401, request=request)
        )

    monkeypatch.setattr(routes, "fetch_models", refused)
    body = {"provider": "openai", "api_key": "k"}
    assert settings_api.post("/api/model-settings/models", json=body).json()["code"] == "auth"

    async def down(name, endpoint, key, transport=None):
        raise httpx.ConnectError("refused")

    monkeypatch.setattr(routes, "fetch_models", down)
    assert (
        settings_api.post("/api/model-settings/models", json=body).json()["code"] == "unreachable"
    )
