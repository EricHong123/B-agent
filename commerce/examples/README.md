# examples

Four vertical demos, each running both agents over one catalog: `retail/` (ACME),
`travel/` (ACME Travel), `telecom/` (ACME Mobile), and `entertainment/` (ACME Tickets).
`python scripts/run_demo.py <vertical>` starts one; each vertical's README lists its ports,
prompts to try on both surfaces, and what it adds to the libraries.

## Layout

| Path | Contents |
|---|---|
| `demo_common/` | Host code the four APIs share: app and middleware (`host.py`), the model provider from `MODEL_PROVIDER` or the settings panel (`model_provider.py`), the settings panel's routes (`model_settings.py`), the operations log with the feedback and handoff routes (`analytics.py`), session store (`sessions.py`), storefront routes (`storefront.py`), merchant router (`merchant.py`), memory routes and fixture seeder (`memory.py`), mock-backend helpers (`*_fixtures.py`) |
| `web-shared/` | The npm package the eight web apps import: the API client, the session and turn hooks, the event types (`protocol.ts` mirrors `commerce_common/streaming.py`), the transcript and inspector components, shared primitives and icons, and the two app frames (`storefront/`, `portal/`), the English/Chinese switch (`i18n.tsx`, `locale.ts`, `i18n-zh.ts`), and the shared look (`theme.css`: one light page, card, text, rule, and shadow set; each app keeps its accent, status, and tier colors and its typefaces) |
| `hub/` | The demo hub (`index.html`, :3200 under `scripts/start_all.sh --separate-apps`): every storefront and portal in one page, each running whole in its own frame, as an overview grid of the apps ticked (zoomed so a cell shows the desktop layout), one app, or a vertical's two side by side; each vertical records its live ports in `hub/runtime/` (`scripts/run_demo.py`) |
| `unified-web/` | Five apps as one (:3300 under `scripts/start_all.sh`): the retail storefront and portal, the travel storefront, and the telecom and ticketing portals behind one rail. It imports each app's own page, styles, typefaces (`app/fonts.ts`), and Chinese table as they are: `next.config.mjs` resolves each app's `@/` inside that app, `postcss-scope.cjs` confines each app's stylesheet to its frame, and each app reads its vertical's `NEXT_PUBLIC_<VERTICAL>_API_URL`; `hosted-apps.cjs` lists them, and `scripts/check.py` holds the list to `components/UnifiedApp.tsx` |
| `package.json` | The npm workspace: `web-shared` plus every `*/storefront-web` and `*/merchant-web` (`npm ci` installs all of them) |
| `<vertical>/api/` | One FastAPI process: the two mock backends, the two agent configs (`agent_config.py`), the vertical's own routes and presentation extensions, and the merchant router mounted under `/api/merchant` |
| `<vertical>/data/` | The fixtures both backends load, listed in the vertical's README |
| `<vertical>/storefront-web/`, `<vertical>/merchant-web/` | The Next.js apps: this vertical's cards, views, and tokens over `web-shared` |

Sessions, carts, and staged changes live in one process's memory in `demo_common`, so the
examples run one worker.

`web-shared` holds the session, streaming, and rendering plumbing once. Each app holds its
own components: `components/generative/` has one entry per presentation tool, typed by the
app's `lib/types.ts`, so the four frontends are four builds of the same payload schemas
(`shopping_agent/tools/presentation.py`, `merchant_agent/tools/presentation.py`); a
deployment's frontend is a fifth.

## Languages

Every app renders in English or Simplified Chinese; the EN / 中文 button in the app bar (the
portal's sidebar) switches it. The choice is the `acme-locale` cookie, which the layout reads
so the server renders the language the client hydrates with, and which every app on
localhost shares. English text is the key: `useT()` from `web-shared` looks it up in the
app's `lib/i18n-zh.ts` over `web-shared/i18n-zh.ts` and falls back to English. A chat request
carries the locale; the host puts the matching `reply_language` in the context block and the
agent writes in it. Catalog data (names, descriptions, fees) stays as the fixtures author it.

## Showcase pages

Every web app serves `/showcase`, which renders each of its components from
`lib/showcase-fixtures.ts`; it needs neither the API nor a key, and `run_demo.py` prints
the storefront's showcase URL when the demo is up. Open it when changing a component.

## Identity

A storefront session starts by naming a profile from `data/users.json` (`POST /api/session`);
a merchant session binds to the one merchant the process serves. Every later request carries
only the session id, in `X-Session-Id`, and the routes read the principal from it.

## Environment variables

| Variable | Effect | Read in | Default |
|---|---|---|---|
| `ANTHROPIC_API_KEY` or `ANTHROPIC_AUTH_TOKEN` | Chat credentials; the environment wins over `<vertical>/.env`, which wins over the repo-root `.env` | `demo_common/host.py` | unset (client credential chain) |
| `MODEL_PROVIDER` | `anthropic`, or an OpenAI-compatible preset: `openai`, `deepseek`, `qwen`, `moonshot`, `zhipu`, `ollama`, `openai-compatible` | `demo_common/model_provider.py` | `anthropic` |
| `MODEL_API_KEY` | The provider's key; each preset also reads its usual variable (`OPENAI_API_KEY`, `DEEPSEEK_API_KEY`, `DASHSCOPE_API_KEY`, `MOONSHOT_API_KEY`, `ZHIPUAI_API_KEY`) | `demo_common/model_provider.py` | unset |
| `MODEL_BASE_URL`, `MODEL_NAME`, `MODEL_FAST_NAME` | The endpoint, the turn loop's model, and memory extraction's model, over the preset's | `demo_common/model_provider.py` | the preset's |
| `COMMERCE_DEMO_AUTH` | `sdk` skips the `.env` files and clears the key variables so the client's credential chain is used; `run_demo.py --federated` sets it | `demo_common/host.py` | unset |
| `DEMO_ALLOWED_HOSTS` | Comma-separated Host values the API answers to besides `localhost` and `127.0.0.1` | `demo_common/host.py` | unset |
| `DEMO_MODEL_SETTINGS`, `DEMO_MODEL_SETTINGS_FILE` | `0` makes the model settings panel read-only; the file replaces `.model-settings.json` at the repo root, whose values (saved from the panel) replace the `MODEL_*` variables while it exists | `demo_common/model_settings.py`, `demo_common/model_provider.py` | editable, repo root |
| `DEMO_ANALYTICS`, `DEMO_ANALYTICS_DIR` | `0` turns the operations log off; the directory replaces `<vertical>/data/.analytics/` (`docs/metrics.md`) | `demo_common/analytics.py` | on, per vertical |
| `DEMO_LOG_LEVEL` | `INFO` writes one line per model call; `DEBUG` adds each request and response | `demo_common/host.py` | `INFO` |
| `MERCHANT_REQUIRE_HOST_APPROVAL` | `0` lets an approval typed in chat apply a change; `1` requires the preview card's button | `demo_common/host.py` | `1` |
| `MERCHANT_ANALYSIS_CODE_EXECUTION` | `1` mounts the hosted code execution tool in the retail analysis delegate | `retail/api/agent_config.py` | `0` |
| `MERCHANT_ANALYSIS_MODEL` | The retail analysis delegate's model | `retail/api/agent_config.py` | unset (main model) |
| `NEXT_PUBLIC_API_URL` | Where a web app sends its requests; `run_demo.py` sets it to the port the API came up on | `<app>/lib/api.ts` | `http://localhost:<API_PORT>` |

The API reads its variables at startup; a web app takes the `NEXT_PUBLIC_` values when it
is built or its dev server starts.
