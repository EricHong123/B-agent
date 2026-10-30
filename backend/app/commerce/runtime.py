"""The commerce runtime: one model client, the two agents, their stores and configs.

The model client follows B-agent's own AI routing so the assistants call the same
provider the rest of the platform uses:

1. ``COMMERCE_MODEL_BASE_URL`` (or ``COMMERCE_MODEL_PROVIDER=openai-compatible``) names an
   OpenAI-compatible endpoint explicitly.
2. With the AI runtime set to OmniRoute, the assistants call OmniRoute's
   ``/v1/chat/completions`` with its key and the ``live_reply`` model alias.
3. ``COMMERCE_MODEL_PROVIDER=anthropic`` or an ``ANTHROPIC_API_KEY`` uses the Anthropic SDK.
4. Otherwise the direct provider B-agent is configured with (DashScope or OpenAI).

No key configured leaves a client that refuses every call, and the chat stream reports
a readable ``no_key`` error instead of failing the request.
"""

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, Optional

from anthropic import AsyncAnthropic

from commerce_common.openai_compat import OpenAICompatibleClient
from commerce_common.skills import SkillRegistry
from merchant_agent import MerchantAgentConfig, MerchantSessionState
from merchant_agent_runtime import MerchantAgent
from shopping_agent import ShoppingAgentConfig, ShoppingSessionState
from shopping_agent_runtime import ShoppingAgent

from app.commerce.merchant import BAgentMerchant
from app.commerce.operations import OperationsLog
from app.commerce.storefront import BAgentStorefront
from app.commerce.stores import SessionScope, SessionStore, SqlMemoryStore, default_scope
from app.config import Settings, settings


COMMERCE_ROOT = Path(os.environ.get("COMMERCE_ROOT") or Path(__file__).resolve().parents[3] / "commerce")
SHOPPING_SKILLS = COMMERCE_ROOT / "shopping-agent" / "skills"
MERCHANT_SKILLS = COMMERCE_ROOT / "merchant-agent" / "skills"

BUYER_SEARCH_NOTES = (
    "Products are sold B2B: every record states its minimum order quantity ('moq') and "
    "production 'lead_time'; search by material, certification, or origin through "
    "attributes. Quantities in the basket are units of the product's own 'unit'."
)


@dataclass(frozen=True)
class ModelChoice:
    provider: str
    client: Any
    model: Optional[str]
    fast_model: Optional[str]
    configured: bool


def _read_omniroute_key(config: Settings) -> str:
    for candidate in (config.AI_RUNTIME_SECRET_FILE, config.OMNIROUTE_API_KEY_FILE):
        if candidate and Path(candidate).is_file():
            value = Path(candidate).read_text(encoding="utf-8").strip()
            if value:
                return value
    return config.OMNIROUTE_API_KEY.strip()


def resolve_model(config: Settings = settings, ai_runtime: Optional[Dict[str, Any]] = None) -> ModelChoice:
    """``ai_runtime`` is ``AIRuntimeService.get_config()`` as a dict, when the caller has a
    database session to read it; the environment is used otherwise."""
    runtime = ai_runtime or {
        "backend": config.LLM_BACKEND,
        "base_url": config.OMNIROUTE_BASE_URL,
        "model_aliases": config.omniroute_model_aliases(),
        "timeout_seconds": config.OMNIROUTE_TIMEOUT_SECONDS,
    }
    name = config.COMMERCE_MODEL_NAME or None
    fast = config.COMMERCE_MODEL_FAST_NAME or name
    explicit_key = config.COMMERCE_MODEL_API_KEY or None

    if config.COMMERCE_MODEL_PROVIDER == "openai-compatible" or config.COMMERCE_MODEL_BASE_URL:
        base = config.COMMERCE_MODEL_BASE_URL or config.OPENAI_API_BASE or "https://api.openai.com/v1"
        return ModelChoice(
            "openai-compatible",
            OpenAICompatibleClient(base_url=base, api_key=explicit_key, provider_label="the commerce model endpoint"),
            name,
            fast,
            bool(explicit_key),
        )
    if config.COMMERCE_MODEL_PROVIDER == "anthropic" or (
        config.COMMERCE_MODEL_PROVIDER == "auto"
        and runtime.get("backend") != "omniroute"
        and os.environ.get("ANTHROPIC_API_KEY")
    ):
        key = explicit_key or os.environ.get("ANTHROPIC_API_KEY")
        return ModelChoice("anthropic", AsyncAnthropic(api_key=key), name, fast or None, bool(key))
    if runtime.get("backend") == "omniroute":
        aliases = runtime.get("model_aliases") or {}
        model = name or aliases.get("live_reply") or aliases.get("message_draft")
        key = explicit_key or _read_omniroute_key(config)
        return ModelChoice(
            "omniroute",
            OpenAICompatibleClient(
                base_url=str(runtime.get("base_url", "")).rstrip("/") + "/v1",
                api_key=key or None,
                timeout=float(runtime.get("timeout_seconds") or 60.0),
                provider_label="OmniRoute",
            ),
            model,
            fast or aliases.get("summarization") or model,
            bool(key and model),
        )
    provider = (config.AI_PROVIDER or "tongyi").lower()
    if provider == "openai":
        key = explicit_key or config.OPENAI_API_KEY or None
        return ModelChoice(
            "openai",
            OpenAICompatibleClient(
                base_url=config.OPENAI_API_BASE or "https://api.openai.com/v1",
                api_key=key,
                max_tokens_field="max_completion_tokens",
                provider_label="OpenAI",
            ),
            name or "gpt-4.1",
            fast or "gpt-4.1-mini",
            bool(key),
        )
    key = explicit_key or config.TONGYI_API_KEY or config.QWEN_API_KEY or None
    return ModelChoice(
        "qwen",
        OpenAICompatibleClient(base_url=config.TONGYI_API_BASE, api_key=key, provider_label="DashScope"),
        name or "qwen-plus",
        fast or "qwen-turbo",
        bool(key),
    )


ANTHROPIC_DEFAULTS = {"buyer": "claude-sonnet-5-5", "operations": "claude-opus-5-5"}
ANTHROPIC_FAST_DEFAULT = "claude-haiku-5-5"


def _model_fields(choice: ModelChoice, role: str) -> Dict[str, Any]:
    model, fast = choice.model, choice.fast_model
    if choice.provider == "anthropic":
        model = model or ANTHROPIC_DEFAULTS[role]
        fast = fast or ANTHROPIC_FAST_DEFAULT
    fields: Dict[str, Any] = {}
    if model:
        fields["model"] = model
    if fast:
        fields["memory_model"] = fast
    return fields


def shopping_config(choice: ModelChoice, config: Settings = settings) -> ShoppingAgentConfig:
    return ShoppingAgentConfig(
        **_model_fields(choice, "buyer"),
        brand_name=config.COMMERCE_BRAND_NAME,
        assistant_name=f"{config.COMMERCE_BRAND_NAME} buyer assistant",
        brand_voice="professional, precise about trade terms, and brief",
        domain_search_notes=BUYER_SEARCH_NOTES,
        enable_disclosures=True,
        max_quantity_per_item=1_000_000,
        max_cart_lines=50,
    )


def merchant_config(choice: ModelChoice, config: Settings = settings) -> MerchantAgentConfig:
    return MerchantAgentConfig(
        **_model_fields(choice, "operations"),
        brand_name=config.COMMERCE_BRAND_NAME,
        assistant_name=f"{config.COMMERCE_BRAND_NAME} operations assistant",
        approval_surface="the Approve button on the change preview card in the console",
        require_host_approval=True,
        enable_analysis=config.COMMERCE_ANALYSIS_ENABLED,
        analysis_use_code_execution=False,
        max_restock_quantity=100_000,
        max_campaign_budget=50_000.0,
    )


class CommerceRuntime:
    """Everything a commerce route needs, built once per process (or per test)."""

    def __init__(
        self,
        *,
        scope: SessionScope = default_scope,
        choice: Optional[ModelChoice] = None,
        config: Settings = settings,
    ) -> None:
        self.scope = scope
        self.choice = choice or resolve_model(config)
        self.memory_store = SqlMemoryStore(scope)
        self.storefront = BAgentStorefront(scope)
        shopping = shopping_config(self.choice, config)
        merchant = merchant_config(self.choice, config)
        self.merchant = BAgentMerchant(scope, merchant, reporting_currency=config.COMMERCE_REPORTING_CURRENCY)
        self.shopping_agent = ShoppingAgent(
            backend=self.storefront,
            skills=SkillRegistry.from_dir(SHOPPING_SKILLS),
            config=shopping,
            memory_store=self.memory_store,
            client=self.choice.client,
        )
        self.merchant_agent = MerchantAgent(
            backend=self.merchant,
            skills=SkillRegistry.from_dir(MERCHANT_SKILLS),
            config=merchant,
            memory_store=self.memory_store,
            client=self.choice.client,
        )
        self.buyer_sessions: SessionStore[ShoppingSessionState] = SessionStore(scope, "buyer", ShoppingSessionState)
        self.merchant_sessions: SessionStore[MerchantSessionState] = SessionStore(scope, "merchant", MerchantSessionState)
        self.buyer_log = OperationsLog(scope, role="buyer")
        self.merchant_log = OperationsLog(scope, role="merchant")

    def status(self) -> Dict[str, Any]:
        return {
            "provider": self.choice.provider,
            "model": self.shopping_agent.config.model,
            "merchant_model": self.merchant_agent.config.model,
            "model_configured": self.choice.configured,
            "buyer_skills": self.shopping_agent.skills.names,
            "operations_skills": self.merchant_agent.skills.names,
        }


_runtime: Optional[CommerceRuntime] = None


def get_commerce_runtime() -> CommerceRuntime:
    """The process runtime; tests override this dependency with their own."""
    global _runtime
    if _runtime is None:
        _runtime = CommerceRuntime()
    return _runtime


def reset_commerce_runtime() -> None:
    """Drop the cached runtime so the next request picks up changed AI settings."""
    global _runtime
    _runtime = None
