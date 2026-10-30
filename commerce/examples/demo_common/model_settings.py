# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""The model settings routes the web apps' settings panel calls, on every example API:

``GET    /api/model-settings``        the provider in force, the presets, whether a key is set
``PUT    /api/model-settings``        save provider, endpoint, model names, and optionally a key
``DELETE /api/model-settings``        drop the saved settings; the ``.env`` values apply again
``POST   /api/model-settings/test``   one short model call under the settings in force
``POST   /api/model-settings/models`` the models a provider offers, for the panel's pickers

A key goes in and never comes back out: reads say only whether one is set and its last
four characters when the panel saved it. The settings live in ``model_provider``'s file
and apply to the next turn without a restart. The APIs answer only loopback host names
(``build_app``); ``DEMO_MODEL_SETTINGS=0`` makes the settings read-only, for a deployment
whose model is fixed by its environment.
"""

# The routes take FastAPI-resolved bodies, so annotations are evaluated eagerly (no
# ``from __future__ import annotations``).

import logging
import os
from typing import Any

import anthropic
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from commerce_common.openai_compat import ModelAuthenticationError, ModelProviderError

from .model_provider import (
    PRESETS,
    ModelProvider,
    ModelSettings,
    clear_settings,
    env_value,
    provider_client,
    resolve_provider,
    save_settings,
    saved_settings,
)

logger = logging.getLogger(__name__)

PREFIX = "/api/model-settings"


class SettingsUpdate(BaseModel):
    """A save from the panel. ``api_key`` left out (or null) keeps the key already saved;
    an empty string removes it."""

    provider: str = Field(min_length=1, max_length=40)
    api_key: str | None = Field(default=None, max_length=400)
    base_url: str | None = Field(default=None, max_length=400)
    model: str | None = Field(default=None, max_length=120)
    fast_model: str | None = Field(default=None, max_length=120)


class ModelListRequest(BaseModel):
    """What the panel holds when it asks for a provider's models. A key left out falls back
    to the one saved for that provider, then to the environment's."""

    provider: str = Field(min_length=1, max_length=40)
    api_key: str | None = Field(default=None, max_length=400)
    base_url: str | None = Field(default=None, max_length=400)


MAX_MODELS = 500
ANTHROPIC_API = "https://api.anthropic.com"


def listing_target(request: ModelListRequest) -> tuple[str, str, str | None]:
    """``(provider name, endpoint, key)`` to list models from. Raises ``ValueError`` for an
    unknown provider or one with no endpoint."""
    name = request.provider.strip().lower()
    saved = saved_settings()
    key = (request.api_key or "").strip() or None
    if key is None and saved is not None and saved.provider == name:
        key = saved.api_key
    in_env = (env_value("MODEL_PROVIDER") or "anthropic").lower() == name
    base_url = (request.base_url or "").strip() or None
    if name == "anthropic":
        key = (
            key
            or (env_value("MODEL_API_KEY") if in_env else None)
            or env_value("ANTHROPIC_API_KEY")
        )
        return name, (base_url or ANTHROPIC_API).rstrip("/"), key
    preset = PRESETS.get(name)
    if preset is None:
        raise ValueError("Choose a provider from the list.")
    key = (
        key
        or (env_value("MODEL_API_KEY") if in_env else None)
        or (env_value(preset.key_env) if preset.key_env else None)
    )
    endpoint = base_url or preset.base_url
    if not endpoint:
        raise ValueError("This provider needs an endpoint.")
    return name, endpoint.rstrip("/"), key


async def fetch_models(
    name: str, endpoint: str, key: str | None, transport: httpx.AsyncBaseTransport | None = None
) -> list[str]:
    """The model ids the provider's list endpoint returns, sorted: Anthropic's
    ``/v1/models``, or ``/models`` under an OpenAI-compatible base URL. Raises
    ``httpx.HTTPStatusError`` for a refusal and ``httpx.HTTPError`` when it cannot be reached."""
    if name == "anthropic":
        url = f"{endpoint}/v1/models?limit=1000"
        headers = {"x-api-key": key or "", "anthropic-version": "2023-06-01"}
    else:
        url = f"{endpoint}/models"
        headers = {"Authorization": f"Bearer {key}"} if key else {}
    async with httpx.AsyncClient(timeout=15.0, transport=transport) as client:
        response = await client.get(url, headers=headers)
        response.raise_for_status()
        body = response.json()
    rows = (body.get("data") or body.get("models") or []) if isinstance(body, dict) else body
    ids = {
        str(row.get("id") or row.get("name") or row.get("model"))
        for row in rows
        if isinstance(row, dict) and (row.get("id") or row.get("name") or row.get("model"))
    }
    return sorted(ids)[:MAX_MODELS]


def editable() -> bool:
    return os.environ.get("DEMO_MODEL_SETTINGS", "1") != "0"


def _presets() -> list[dict[str, Any]]:
    rows = [
        {
            "name": "anthropic",
            "label": "Anthropic",
            "base_url": None,
            "model": None,
            "fast_model": None,
            "key_required": True,
        }
    ]
    rows += [
        {
            "name": name,
            "label": preset.label,
            "base_url": preset.base_url,
            "model": preset.model,
            "fast_model": preset.fast_model,
            "key_required": preset.key_required,
        }
        for name, preset in PRESETS.items()
    ]
    return rows


def settings_payload() -> dict[str, Any]:
    """What the panel shows: never the key itself."""
    try:
        provider: ModelProvider | None = resolve_provider()
        problem = None
    except ValueError as error:
        provider, problem = None, str(error)
    saved = saved_settings()
    saved_key = saved.api_key if saved is not None else None
    return {
        "provider": provider.name if provider else None,
        "label": provider.label if provider else None,
        "base_url": provider.base_url if provider else None,
        "model": provider.model if provider else None,
        "fast_model": provider.fast_model if provider else None,
        # A key the provider does not need is reported as not set, beside key_required.
        "has_key": bool(
            provider and provider.has_key() and (provider.api_key or provider.is_anthropic)
        ),
        "key_required": provider.key_required if provider else True,
        "key_hint": provider.key_hint if provider else None,
        "key_preview": f"…{saved_key[-4:]}" if saved_key and len(saved_key) > 8 else None,
        "source": provider.source if provider else ("page" if saved else "env"),
        "problem": problem,
        "editable": editable(),
        "presets": _presets(),
    }


# resolve_provider names the environment variables; the panel names its own fields.
_PANEL_WORDING = {
    "needs MODEL_BASE_URL": "This provider needs an endpoint.",
    "needs MODEL_NAME": "This provider needs a model name.",
    "is not one of": "Choose a provider from the list.",
}


def _panel_wording(message: str) -> str:
    return next((text for marker, text in _PANEL_WORDING.items() if marker in message), message)


def _test_model(provider: ModelProvider) -> str:
    if provider.model:
        return provider.model
    from shopping_agent import ShoppingAgentConfig

    return ShoppingAgentConfig.model_fields["model"].default


def install_model_settings_routes(app: FastAPI) -> None:
    @app.get(PREFIX)
    async def read_settings() -> dict:
        return settings_payload()

    @app.put(PREFIX)
    async def write_settings(update: SettingsUpdate) -> dict:
        if not editable():
            raise HTTPException(status_code=403, detail="Model settings are read-only here")
        saved = saved_settings()
        key = update.api_key
        if key is None and saved is not None and saved.provider == update.provider.lower():
            key = saved.api_key
        settings = ModelSettings(
            provider=update.provider,
            api_key=key or None,
            base_url=update.base_url,
            model=update.model,
            fast_model=update.fast_model,
        )
        try:
            provider = save_settings(settings)
        except ValueError as error:
            raise HTTPException(status_code=422, detail=_panel_wording(str(error))) from error
        logger.info("model settings saved: %s, model %s", provider.label, provider.model)
        return settings_payload()

    @app.delete(PREFIX)
    async def reset_settings() -> dict:
        if not editable():
            raise HTTPException(status_code=403, detail="Model settings are read-only here")
        clear_settings()
        return settings_payload()

    @app.post(f"{PREFIX}/models")
    async def list_models(request: ModelListRequest) -> dict:
        """``ok`` with ``models``, or a ``code`` the panel words (``invalid``, ``no_key``,
        ``auth``, ``status``, ``unreachable``)."""
        try:
            name, endpoint, key = listing_target(request)
        except ValueError as error:
            return {"ok": False, "code": "invalid", "error": str(error)}
        label = "Anthropic" if name == "anthropic" else PRESETS[name].label
        key_required = name == "anthropic" or PRESETS[name].key_required
        if key_required and not key:
            return {"ok": False, "code": "no_key", "label": label}
        try:
            models = await fetch_models(name, endpoint, key)
        except httpx.HTTPStatusError as error:
            status = error.response.status_code
            code = "auth" if status in (401, 403) else "status"
            return {"ok": False, "code": code, "label": label, "status": status}
        except (httpx.HTTPError, ValueError):
            logger.warning("listing models from %s failed", label, exc_info=True)
            return {"ok": False, "code": "unreachable", "label": label}
        return {"ok": True, "label": label, "models": models}

    @app.post(f"{PREFIX}/test")
    async def test_settings() -> dict:
        """``ok`` with the model that answered, or a ``code`` the panel words in the page's
        language (``invalid``, ``no_key``, ``auth``, ``status``, ``unreachable``) plus an
        English ``error``."""
        try:
            provider = resolve_provider()
        except ValueError as error:
            return {"ok": False, "code": "invalid", "error": _panel_wording(str(error))}
        label = provider.label
        if not provider.has_key() and provider.key_required:
            return {
                "ok": False,
                "code": "no_key",
                "label": label,
                "error": f"No API key is set for {label}.",
            }
        model = _test_model(provider)
        failure: dict[str, Any] | None = None
        try:
            await provider_client(provider, timeout=30.0).messages.create(
                model=model,
                max_tokens=16,
                messages=[{"role": "user", "content": "Reply with the word ok."}],
            )
        except (anthropic.AuthenticationError, ModelAuthenticationError):
            failure = {"code": "auth", "error": f"{label} rejected the API key."}
        except (anthropic.APIStatusError, ModelProviderError) as error:
            status = getattr(error, "status_code", None) or getattr(error, "status", None)
            failure = {
                "code": "status",
                "status": status,
                "error": f"{label} returned an error ({status or 'no status'}); "
                "check the model name and endpoint.",
            }
        except Exception:  # a connection failure or anything else: the log keeps the detail
            logger.exception("model settings test failed")
            failure = {
                "code": "unreachable",
                "error": f"Could not reach {label}; check the endpoint.",
            }
        if failure is not None:
            return {"ok": False, "label": label, "model": model, **failure}
        return {"ok": True, "label": label, "model": model}
