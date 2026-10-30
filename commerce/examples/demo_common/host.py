# Copyright 2026 Anthropic PBC
# SPDX-License-Identifier: Apache-2.0

"""Process-level plumbing both roles of a demo API share: credential loading, the app
with its host and CORS middleware, background tasks, the loopback guard, and the SSE
response one chat turn streams."""

from __future__ import annotations

import asyncio
import logging
import os
from collections.abc import AsyncIterator, Awaitable, Callable, Coroutine, Sequence
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Any, Literal, Protocol

import anthropic
from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from starlette.background import BackgroundTask
from starlette.middleware.trustedhost import TrustedHostMiddleware

from commerce_common.openai_compat import ModelAuthenticationError, ModelProviderError
from commerce_common.streaming import AgentEvent, to_sse
from commerce_common.turn import session_tag
from shopping_agent import Cart, Order, ProductDetails, ShoppingSessionContext

from .analytics import OperationsLog
from .model_provider import ModelProvider, apply_model_settings, resolve_provider
from .model_settings import install_model_settings_routes
from .sessions import SessionConflictError, SessionRecord, SessionStore

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]

# The web apps' two languages; a chat request names one and the agent replies in it.
Locale = Literal["en", "zh"]
REPLY_LANGUAGES: dict[str, str] = {"en": "English", "zh": "Simplified Chinese"}

# The error events a chat turn can end with, in each language. ``{label}`` is the model
# provider, ``{key_hint}`` the variable its key goes in, ``{env_hint}`` the example's .env.
_ERROR_TEXT: dict[str, dict[str, str]] = {
    "no_key": {
        "en": "No API key is configured for {label}, so chat can't run. Add one in Model "
        "settings in the top bar, or set {key_hint} in {env_hint} or the repo-root .env and "
        "restart; everything except chat works without one.",
        "zh": "尚未为 {label} 配置 API 密钥，聊天暂不可用。请在顶栏的「模型设置」中填写，或在 "
        "{env_hint} 或仓库根目录的 .env 中设置 {key_hint} 后重启；除聊天外的功能都可正常使用。",
    },
    "auth_failed": {
        "en": "{label} rejected the API key. Check it in Model settings, or {key_hint} in "
        "{env_hint} or the repo-root .env, and unset any stale key exported by your shell.",
        "zh": "{label} 拒绝了 API 密钥。请在「模型设置」中检查，或检查 {env_hint} 或仓库根目录 "
        ".env 中的 {key_hint}，并清除 shell 中导出的过期密钥。",
    },
    "provider_error": {
        "en": "{label} could not complete the request ({status}). Check the model name and "
        "endpoint in Model settings (or MODEL_NAME and MODEL_BASE_URL in the .env), then try "
        "again.",
        "zh": "{label} 无法完成请求（{status}）。请在「模型设置」中检查模型名称和接口地址"
        "（或 .env 中的 MODEL_NAME 和 MODEL_BASE_URL）后重试。",
    },
    "generic": {
        "en": "Something went wrong on our side. Please try again.",
        "zh": "我们这边出了点问题，请稍后重试。",
    },
}


def reply_language(locale: Locale | None) -> str | None:
    """The language name a session context carries for the locale a request names."""
    return REPLY_LANGUAGES.get(locale) if locale else None


def chat_error_text(
    kind: str, locale: Locale | None, provider: ModelProvider, env_hint: str, status: object = ""
) -> str:
    template = _ERROR_TEXT[kind]["zh" if locale == "zh" else "en"]
    return template.format(
        label=provider.label, key_hint=provider.key_hint, env_hint=env_hint, status=status
    )


class DemoStorefront(Protocol):
    """What the shared routes use from a vertical's mock storefront on top of the
    ``StorefrontBackend`` interface it implements: the listings (``products``), a lookup
    by id that also resolves a variant, the store name, per-session cleanup, and the
    cross-user order feed the merchant overview shows."""

    store_name: str
    products: dict[str, ProductDetails]

    def product(self, product_id: str) -> ProductDetails | None: ...

    def reset_session(self, session_id: str) -> None: ...

    def recent_orders(self, limit: int = 6) -> list[Order]: ...

    async def get_cart(self, session: ShoppingSessionContext) -> Cart: ...

    async def add_to_cart(
        self, session: ShoppingSessionContext, product_id: str, quantity: int
    ) -> Cart: ...


def load_demo_env(example_root: Path) -> None:
    """Load credentials before any agent is constructed. A variable already in the
    environment wins; the example's own ``.env`` fills in the rest, then the repo-root
    one; ``COMMERCE_DEMO_AUTH=sdk`` clears key variables instead so the Anthropic SDK's
    own credential chain is used."""
    if os.environ.get("COMMERCE_DEMO_AUTH", "").lower() == "sdk":
        os.environ.pop("ANTHROPIC_API_KEY", None)
        os.environ.pop("ANTHROPIC_AUTH_TOKEN", None)
    else:
        load_dotenv(example_root / ".env", override=False)
        load_dotenv(REPO_ROOT / ".env", override=False)


def host_approval_default() -> bool:
    """Merchant portals require host approval unless ``MERCHANT_REQUIRE_HOST_APPROVAL=0``."""
    return os.environ.get("MERCHANT_REQUIRE_HOST_APPROVAL", "1") != "0"


# The event loop holds only weak references to tasks, so fire-and-forget work (memory
# extraction after a turn) is kept alive here until it completes.
_background_tasks: set[asyncio.Task[Any]] = set()


def spawn_background(coro: Coroutine[Any, Any, object]) -> None:
    task = asyncio.get_running_loop().create_task(coro)
    _background_tasks.add(task)
    task.add_done_callback(_background_tasks.discard)


def _lifespan(on_startup: Sequence[Callable[[], Awaitable[None]]]):
    @asynccontextmanager
    async def lifespan(_: FastAPI) -> AsyncIterator[None]:
        provider = resolve_provider()
        logger.info(
            "model provider: %s, model %s", provider.label, provider.model or "(config default)"
        )
        if not provider.has_key():
            logger.info(
                "No API key for %s in the environment or .env files%s. If chat returns auth "
                "errors, set %s in a .env file (repo root or the example's directory).",
                provider.label,
                "; the Anthropic SDK falls back to its own credential chain"
                if provider.is_anthropic
                else "",
                provider.key_hint,
            )
        for step in on_startup:
            await step()
        yield

    return lifespan


def build_app(title: str, on_startup: Sequence[Callable[[], Awaitable[None]]] = ()) -> FastAPI:
    """A FastAPI app that answers only to loopback host names (plus ``DEMO_ALLOWED_HOSTS``,
    for a deployment that puts its own authentication in front) and to any localhost
    origin. Rejecting other Host headers stops DNS-rebinding, which CORS does not. Logs go
    to stderr at ``DEMO_LOG_LEVEL``: ``INFO`` is a line per model call, ``DEBUG`` adds the bodies."""
    logging.basicConfig(
        level=os.environ.get("DEMO_LOG_LEVEL", "INFO").upper(),
        format="%(levelname)s %(name)s: %(message)s",
    )
    # The model-call line carries what httpx's line for the same request would.
    logging.getLogger("httpx").setLevel(logging.WARNING)
    extra_hosts = [
        host.strip().rsplit(":", 1)[0] if ":" in host.strip() else host.strip()
        for host in os.environ.get("DEMO_ALLOWED_HOSTS", "").split(",")
    ]
    app = FastAPI(title=title, version="0.1.0", lifespan=_lifespan(on_startup))
    app.add_middleware(
        TrustedHostMiddleware,
        allowed_hosts=["localhost", "127.0.0.1", *(host for host in extra_hosts if host)],
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origin_regex=r"http://(localhost|127\.0\.0\.1):\d+",
        allow_methods=["*"],
        allow_headers=["*"],
    )
    install_model_settings_routes(app)
    return app


class TurnAgent(Protocol):
    def stream_turn(
        self, messages: list[dict[str, Any]], session: Any, state: Any
    ) -> AsyncIterator[AgentEvent]: ...

    async def update_memory(self, messages: list[dict[str, Any]], session: Any) -> Any: ...


def append_user_turn(record: SessionRecord[Any], message: str, events_label: str) -> None:
    """Add the user's message to the transcript, preceded by a note listing what happened
    outside the conversation since the last reply, when anything did."""
    if not record.pending_app_events:
        record.messages.append({"role": "user", "content": message})
        return
    note = f"[{events_label} since your last reply: " + " ".join(record.pending_app_events) + "]"
    record.pending_app_events.clear()
    record.messages.append(
        {
            "role": "user",
            "content": [{"type": "text", "text": note}, {"type": "text", "text": message}],
        }
    )


def stream_turn(
    agent: TurnAgent,
    sessions: SessionStore[Any],
    record: SessionRecord[Any],
    session: Any,
    *,
    env_hint: str,
    locale: Locale | None = None,
    log: OperationsLog | None = None,
) -> StreamingResponse:
    """Stream one turn as SSE; the record is written back once the stream has ended (the
    request dependency wrote back before it began). Credential and provider failures become
    a readable error event, in the request's ``locale``, naming ``env_hint`` (the example's
    ``.env`` path); anything else is logged and reported generically. Memory extraction
    runs after the response has streamed. With ``log``, the turn's record goes to the
    operations log, naming the model and provider it ran on, and ``turn_complete``
    carries its ``turn_id``. The turn runs under the model settings in force when it
    starts."""
    apply_model_settings(agent)
    provider = resolve_provider()
    recorder = (
        log.turn(
            record.session_id,
            locale,
            model=getattr(getattr(agent, "config", None), "model", None) or provider.model,
            provider=provider.name,
        )
        if log is not None
        else None
    )

    def error(kind: str, status: object = "") -> str:
        if recorder is not None:
            recorder.failed(kind)
        return to_sse(AgentEvent.error(chat_error_text(kind, locale, provider, env_hint, status)))

    async def event_stream() -> AsyncIterator[str]:
        try:
            async for event in agent.stream_turn(record.messages, session, record.state):
                if event.type == "turn_complete" and event.data.get("results_cleared"):
                    record.stored_messages = 0  # earlier messages changed: rewrite the transcript
                yield to_sse(recorder.observe(event) if recorder is not None else event)
        except (anthropic.AuthenticationError, ModelAuthenticationError) as failure:
            logger.exception("chat turn failed: API authentication")
            missing = isinstance(failure, ModelAuthenticationError) and failure.status is None
            yield error("no_key" if missing else "auth_failed")
        except ModelProviderError as failure:
            logger.exception("chat turn failed: model provider")
            yield error("provider_error", failure.status or "")
        except Exception as failure:  # the client gets a safe event, the log gets the rest
            logger.exception("chat turn failed")
            described = str(failure).lower()
            if any(word in described for word in ("authentication", "credential", "api_key")):
                yield error("no_key")
            else:
                yield error("generic")
        else:
            spawn_background(agent.update_memory(record.messages, session))
        finally:
            if recorder is not None:
                recorder.write()

    def write_back() -> None:
        try:
            sessions.save(record)
        except SessionConflictError:
            # A button's request wrote the session while the turn streamed. The turn is the
            # larger write, so it goes in over that version; the note the button queued is lost.
            record.version = (sessions.read_state(record.session_id) or (0, {}))[0]
            logger.warning(
                "session %s: a write raced the turn; the turn wins", session_tag(record.session_id)
            )
            sessions.save(record)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        background=BackgroundTask(write_back),
    )
