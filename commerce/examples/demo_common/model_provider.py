# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Which model the example APIs call, read from the environment (and so from the ``.env``
files ``load_demo_env`` loads):

``MODEL_PROVIDER``   ``anthropic`` (default) or one of the OpenAI-compatible presets below
``MODEL_API_KEY``    the provider's key; each preset also reads its usual variable
``MODEL_BASE_URL``   overrides the preset's endpoint (required for ``openai-compatible``)
``MODEL_NAME``       the turn loop's model (required where the preset has none)
``MODEL_FAST_NAME``  memory extraction's model; defaults to ``MODEL_NAME``'s preset pair

``anthropic`` keeps the Anthropic SDK and its credential chain (``ANTHROPIC_API_KEY``);
``MODEL_BASE_URL`` points it at an Anthropic-compatible endpoint. Every other provider
runs through ``commerce_common.openai_compat``.

The web apps' model settings panel saves the same five values to
``.model-settings.json`` at the repo root (``DEMO_MODEL_SETTINGS_FILE`` moves it). While
that file exists its values replace the ``MODEL_*`` variables; a preset's usual key
variable still fills in a key the file leaves out. Every API process rereads the file
when it changes, and :class:`ModelClient` and :func:`apply_model_settings` carry a change
into the running agents without a restart.
"""

from __future__ import annotations

import dataclasses
import os
import weakref
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

from anthropic import AsyncAnthropic
from pydantic import BaseModel, Field

from commerce_common.openai_compat import OpenAICompatibleClient

REPO_ROOT = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class Preset:
    label: str
    base_url: str | None
    model: str | None
    fast_model: str | None
    key_env: str | None
    max_tokens_field: str = "max_tokens"
    key_required: bool = True


PRESETS: dict[str, Preset] = {
    "openai": Preset(
        "OpenAI",
        "https://api.openai.com/v1",
        "gpt-4.1",
        "gpt-4.1-mini",
        "OPENAI_API_KEY",
        max_tokens_field="max_completion_tokens",
    ),
    "deepseek": Preset(
        "DeepSeek",
        "https://api.deepseek.com/v1",
        "deepseek-chat",
        "deepseek-chat",
        "DEEPSEEK_API_KEY",
    ),
    "qwen": Preset(
        "Qwen (DashScope)",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "qwen-plus",
        "qwen-turbo",
        "DASHSCOPE_API_KEY",
    ),
    "moonshot": Preset(
        "Moonshot",
        "https://api.moonshot.cn/v1",
        "moonshot-v1-32k",
        "moonshot-v1-8k",
        "MOONSHOT_API_KEY",
    ),
    "zhipu": Preset(
        "Zhipu GLM",
        "https://open.bigmodel.cn/api/paas/v4",
        "glm-4-plus",
        "glm-4-flash",
        "ZHIPUAI_API_KEY",
    ),
    "ollama": Preset("Ollama", "http://localhost:11434/v1", None, None, None, key_required=False),
    "openai-compatible": Preset("OpenAI-compatible endpoint", None, None, None, None),
}


@dataclass(frozen=True)
class ModelProvider:
    """The resolved settings. ``key_hint`` names where the key goes, for error messages;
    ``source`` says whether they came from the settings panel or the environment."""

    name: str
    label: str
    api_key: str | None
    base_url: str | None
    model: str | None
    fast_model: str | None
    key_hint: str
    max_tokens_field: str = "max_tokens"
    key_required: bool = True
    source: Literal["page", "env"] = "env"

    @property
    def is_anthropic(self) -> bool:
        return self.name == "anthropic"

    def has_key(self) -> bool:
        if self.is_anthropic:
            return bool(
                self.api_key
                or os.environ.get("ANTHROPIC_API_KEY")
                or os.environ.get("ANTHROPIC_AUTH_TOKEN")
            )
        return bool(self.api_key) or not self.key_required


def env_value(name: str) -> str | None:
    """An environment variable, stripped, or None when unset or blank."""
    return (os.environ.get(name) or "").strip() or None


class ModelSettings(BaseModel):
    """What the settings panel saves: the five ``MODEL_*`` values, by their own names."""

    provider: str = "anthropic"
    api_key: str | None = Field(default=None, max_length=400)
    base_url: str | None = Field(default=None, max_length=400)
    model: str | None = Field(default=None, max_length=120)
    fast_model: str | None = Field(default=None, max_length=120)

    def cleaned(self) -> ModelSettings:
        values = {k: (v.strip() or None) if isinstance(v, str) else v for k, v in self}
        values["provider"] = (values["provider"] or "anthropic").lower()
        return ModelSettings(**values)


_FIELDS = {
    "MODEL_PROVIDER": "provider",
    "MODEL_API_KEY": "api_key",
    "MODEL_BASE_URL": "base_url",
    "MODEL_NAME": "model",
    "MODEL_FAST_NAME": "fast_model",
}
_saved: tuple[float, ModelSettings | None] | None = None


def settings_path() -> Path:
    return Path(os.environ.get("DEMO_MODEL_SETTINGS_FILE") or REPO_ROOT / ".model-settings.json")


def saved_settings() -> ModelSettings | None:
    """The panel's saved settings, or None while there are none; reread when the file
    changes, so a save in one API process reaches the others."""
    global _saved
    path = settings_path()
    try:
        stamp = path.stat().st_mtime
    except OSError:
        _saved = None
        return None
    if _saved is None or _saved[0] != stamp:
        try:
            settings = ModelSettings.model_validate_json(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            settings = None
        _saved = (stamp, settings.cleaned() if settings else None)
    return _saved[1]


def save_settings(settings: ModelSettings) -> ModelProvider:
    """Validate ``settings`` as :func:`resolve_provider` would read them, then write them
    readable by the owner only. Raises ``ValueError`` and writes nothing when they do not
    resolve."""
    settings = settings.cleaned()
    provider = resolve_provider(settings)
    path = settings_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + ".tmp")
    fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as handle:
        handle.write(settings.model_dump_json(indent=2))
    os.replace(temporary, path)
    return provider


def clear_settings() -> None:
    """Remove the panel's settings, so the ``MODEL_*`` variables apply again."""
    settings_path().unlink(missing_ok=True)


def resolve_provider(settings: ModelSettings | None = None) -> ModelProvider:
    """The provider ``settings`` name, else the panel's saved settings, else the
    environment's. Raises ``ValueError`` for an unknown provider or a missing endpoint or
    model, so the API fails at startup (or the panel refuses the save) rather than at chat."""
    settings = settings or saved_settings()
    source: Literal["page", "env"] = "page" if settings is not None else "env"

    def value(variable: str) -> str | None:
        if settings is not None:
            return getattr(settings, _FIELDS[variable])
        return env_value(variable)

    name = (value("MODEL_PROVIDER") or "anthropic").lower()
    if name == "anthropic":
        return ModelProvider(
            name=name,
            label="Anthropic",
            api_key=value("MODEL_API_KEY"),
            base_url=value("MODEL_BASE_URL"),
            model=value("MODEL_NAME"),
            fast_model=value("MODEL_FAST_NAME"),
            key_hint="ANTHROPIC_API_KEY (or MODEL_API_KEY)",
            source=source,
        )
    preset = PRESETS.get(name)
    if preset is None:
        known = ", ".join(["anthropic", *PRESETS])
        raise ValueError(f"MODEL_PROVIDER={name!r} is not one of: {known}")
    base_url = value("MODEL_BASE_URL") or preset.base_url
    model = value("MODEL_NAME") or preset.model
    if not base_url:
        raise ValueError(f"MODEL_PROVIDER={name} needs MODEL_BASE_URL")
    if not model:
        raise ValueError(f"MODEL_PROVIDER={name} needs MODEL_NAME")
    fast_model = value("MODEL_FAST_NAME") or (
        preset.fast_model if not value("MODEL_NAME") else model
    )
    key = value("MODEL_API_KEY") or (env_value(preset.key_env) if preset.key_env else None)
    hint = f"MODEL_API_KEY (or {preset.key_env})" if preset.key_env else "MODEL_API_KEY"
    return ModelProvider(
        name=name,
        label=preset.label,
        api_key=key,
        base_url=base_url,
        model=model,
        fast_model=fast_model,
        key_hint=hint,
        max_tokens_field=preset.max_tokens_field,
        key_required=preset.key_required,
        source=source,
    )


def provider_client(provider: ModelProvider, timeout: float = 120.0) -> Any:
    """A client for ``provider``: an ``AsyncAnthropic`` (its own credential chain when no
    key or endpoint is set) or the OpenAI-compatible client."""
    if provider.is_anthropic:
        return AsyncAnthropic(api_key=provider.api_key, base_url=provider.base_url, timeout=timeout)
    return OpenAICompatibleClient(
        base_url=provider.base_url or "",
        api_key=provider.api_key,
        timeout=timeout,
        max_tokens_field=provider.max_tokens_field,
        key_required=provider.key_required,
        provider_label=provider.label,
    )


class ModelClient:
    """The client the example agents take as ``client=``: ``messages`` belongs to a client
    for the provider in force, rebuilt when the settings change, so a save in the panel
    reaches the turn loop, memory extraction, and the analysis delegate alike."""

    def __init__(self, timeout: float = 120.0) -> None:
        self._timeout = timeout
        self._built: tuple[ModelProvider, Any] | None = None

    def current(self) -> Any:
        provider = resolve_provider()
        if self._built is None or self._built[0] != provider:
            self._built = (provider, provider_client(provider, self._timeout))
        return self._built[1]

    @property
    def messages(self) -> Any:
        return self.current().messages


def model_client(timeout: float = 120.0) -> ModelClient:
    """The client the example agents take as ``client=``."""
    return ModelClient(timeout)


# Each agent's model names when the settings name none: its config class's defaults.
_default_models: weakref.WeakKeyDictionary[Any, tuple[str, str]] = weakref.WeakKeyDictionary()


def _class_default(config: Any, name: str) -> str:
    field = type(config).model_fields[name]
    return field.default if isinstance(field.default, str) else getattr(config, name)


def apply_model_settings(agent: Any) -> None:
    """Bring an agent's model names in line with the settings in force, before a turn:
    the turn loop's ``config.model`` (the analysis delegate reads the same config) and
    memory extraction's ``memory_model``. A name the settings leave out falls back to the
    config class's default."""
    config = getattr(agent, "config", None)
    if config is None:
        return
    defaults = _default_models.setdefault(
        agent, (_class_default(config, "model"), _class_default(config, "memory_model"))
    )
    provider = resolve_provider()
    config.model = provider.model or defaults[0]
    config.memory_model = provider.fast_model or defaults[1]
    memory = getattr(agent, "memory", None)
    if memory is not None and memory.model != config.memory_model:
        agent.memory = dataclasses.replace(memory, model=config.memory_model)


def model_config_fields() -> dict[str, Any]:
    """The config fields a provider sets: the turn loop's model and the memory model,
    each only when the settings, the environment, or the preset names one."""
    provider = resolve_provider()
    fields: dict[str, Any] = {}
    if provider.model:
        fields["model"] = provider.model
    if provider.fast_model:
        fields["memory_model"] = provider.fast_model
    return fields
