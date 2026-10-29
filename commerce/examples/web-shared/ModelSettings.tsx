// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/**
 * The model settings panel both shells carry in their bars: the provider, endpoint, model
 * names, and key the example API calls, saved through `/api/model-settings`
 * (demo_common/model_settings.py). The API never returns a key; the panel shows whether one is
 * set and, for a key saved here, its last four characters.
 */

import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import type { AgentApi } from "./api";
import { type Translate, useT } from "./i18n";
import { Icon } from "./icons";
import { Button, Sheet } from "./ui";

interface Preset {
  name: string;
  label: string;
  base_url: string | null;
  model: string | null;
  fast_model: string | null;
  key_required: boolean;
}

interface Settings {
  provider: string | null;
  label: string | null;
  base_url: string | null;
  model: string | null;
  fast_model: string | null;
  has_key: boolean;
  key_required: boolean;
  key_hint: string | null;
  key_preview: string | null;
  source: "page" | "env";
  problem: string | null;
  editable: boolean;
  presets: Preset[];
}

type Notice = { tone: "ok" | "error"; text: string } | null;

interface TestResult {
  ok: boolean;
  code?: "invalid" | "no_key" | "auth" | "status" | "unreachable";
  label?: string;
  model?: string;
  status?: number | null;
  error?: string;
}

interface ModelList {
  ok: boolean;
  code?: "invalid" | "no_key" | "auth" | "status" | "unreachable";
  label?: string;
  status?: number;
  models?: string[];
  error?: string;
}

type Listing = { state: "idle" | "loading" } | { state: "ok"; models: string[] } | { state: "error"; text: string; noKey?: boolean };

const PATH = "/api/model-settings";

async function call<T>(root: string, method: string, path = "", body?: unknown): Promise<{ data?: T; error?: string }> {
  try {
    const response = await fetch(`${root}${PATH}${path}`, {
      method,
      headers: body === undefined ? undefined : { "Content-Type": "application/json" },
      body: body === undefined ? undefined : JSON.stringify(body),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) return { error: typeof data?.detail === "string" ? data.detail : `HTTP ${response.status}` };
    return { data: data as T };
  } catch {
    return { error: "unreachable" };
  }
}

function Field({ label, hint, children }: { label: string; hint?: string; children: ReactNode }) {
  return (
    <label className="flex flex-col gap-1.5">
      <span className="text-[12.5px] font-semibold text-(--ink)">{label}</span>
      {children}
      {hint ? <span className="text-[11.5px] leading-snug text-(--ink-soft)">{hint}</span> : null}
    </label>
  );
}

/** Why a provider's models did not load, in the page's language. */
function listingFailure(result: ModelList, t: Translate): string {
  const vars = { label: result.label ?? "", status: String(result.status ?? "—") };
  switch (result.code) {
    case "no_key":
      return t("Enter the API key to load {label}'s models.", vars);
    case "auth":
      return t("{label} rejected the API key.", vars);
    case "status":
      return t("{label} could not list its models ({status}); type the model name instead.", vars);
    case "unreachable":
      return t("Could not reach {label}; check the endpoint.", vars);
    default:
      return t(result.error ?? "");
  }
}

/** A model name: picked from the provider's list once it has loaded, typed otherwise. */
function ModelPicker({
  value,
  onChange,
  models,
  placeholder,
  defaultLabel,
  disabled,
}: {
  value: string;
  onChange: (value: string) => void;
  models: string[] | null;
  /** The typed field's placeholder; `defaultLabel` is the picker's empty choice. */
  placeholder: string;
  defaultLabel: string;
  disabled: boolean;
}) {
  if (!models?.length) {
    return <input value={value} onChange={(event) => onChange(event.target.value)} placeholder={placeholder} disabled={disabled} className={INPUT} />;
  }
  return (
    <select value={value} onChange={(event) => onChange(event.target.value)} disabled={disabled} className={INPUT}>
      <option value="">{defaultLabel}</option>
      {value && !models.includes(value) ? <option value={value}>{value}</option> : null}
      {models.map((name) => (
        <option key={name} value={name}>
          {name}
        </option>
      ))}
    </select>
  );
}

const INPUT =
  "w-full rounded-[10px] border border-(--line-strong) bg-(--card) px-3 py-[7px] text-[14px] text-(--ink) outline-none placeholder:text-(--ink-faint) focus:border-(--accent) disabled:opacity-60";

function ModelSettingsSheet({ api, onClose }: { api: AgentApi; onClose: () => void }) {
  const t = useT();
  const [settings, setSettings] = useState<Settings | null>(null);
  const [loadError, setLoadError] = useState(false);
  const [provider, setProvider] = useState("anthropic");
  const [baseUrl, setBaseUrl] = useState("");
  const [model, setModel] = useState("");
  const [fastModel, setFastModel] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [busy, setBusy] = useState<"save" | "test" | "reset" | null>(null);
  const [notice, setNotice] = useState<Notice>(null);
  const [listing, setListing] = useState<Listing>({ state: "idle" });
  const [typing, setTyping] = useState(false); // type a model name instead of picking one
  const listingRun = useRef(0);

  const adopt = useCallback((next: Settings) => {
    setSettings(next);
    const preset = next.presets.find((p) => p.name === next.provider);
    setProvider(next.provider ?? "anthropic");
    // A value equal to the preset's default shows as the placeholder, not as an override.
    setBaseUrl(next.base_url && next.base_url !== preset?.base_url ? next.base_url : "");
    setModel(next.model && next.model !== preset?.model ? next.model : "");
    // The memory model defaults to the preset's, or to the main model once that is set.
    const fastDefault = next.fast_model === preset?.fast_model || next.fast_model === next.model;
    setFastModel(next.fast_model && !fastDefault ? next.fast_model : "");
    setApiKey("");
  }, []);

  useEffect(() => {
    call<Settings>(api.root, "GET").then(({ data }) => (data ? adopt(data) : setLoadError(true)));
  }, [api.root, adopt]);

  const preset = settings?.presets.find((p) => p.name === provider);
  const sameProvider = settings?.provider === provider;
  const editable = settings?.editable ?? false;
  const testFailure = (result: TestResult) => {
    const vars = { label: result.label ?? "", status: String(result.status ?? "—") };
    switch (result.code) {
      case "no_key":
        return t("No API key is set for {label}.", vars);
      case "auth":
        return t("{label} rejected the API key.", vars);
      case "status":
        return t("{label} returned an error ({status}); check the model name and endpoint.", vars);
      case "unreachable":
        return t("Could not reach {label}; check the endpoint.", vars);
      default:
        return t(result.error ?? "");
    }
  };
  // The provider's models, loaded as soon as there is a key to ask with: the one being typed,
  // or the one saved here or in .env. A newer request makes an older answer moot.
  const loadModels = useCallback(async () => {
    const run = ++listingRun.current;
    setListing({ state: "loading" });
    const { data } = await call<ModelList>(api.root, "POST", "/models", {
      provider,
      api_key: apiKey.trim() || null,
      base_url: baseUrl.trim() || null,
    });
    if (run !== listingRun.current) return;
    if (data?.ok) setListing({ state: "ok", models: data.models ?? [] });
    else setListing({ state: "error", text: data ? listingFailure(data, t) : t("The API is not reachable."), noKey: data?.code === "no_key" });
  }, [api.root, provider, apiKey, baseUrl, t]);

  useEffect(() => {
    if (!settings?.editable) return;
    const key = apiKey.trim();
    if (key && key.length < 8) return; // still typing
    const timer = window.setTimeout(loadModels, key ? 600 : 0);
    return () => window.clearTimeout(timer);
  }, [settings?.editable, apiKey, loadModels]);

  const models = listing.state === "ok" && !typing ? listing.models : null;
  // Anthropic and the named presets have a default model; an open endpoint needs one chosen.
  const needsModel = provider !== "anthropic" && !preset?.model;
  const modelDefault = needsModel
    ? t("Choose a model")
    : t("Provider default ({model})", { model: preset?.model ?? t("default model") });
  // Memory extraction runs on the preset's small model, else on the main model.
  const fastDefault = preset?.fast_model
    ? t("Provider default ({model})", { model: preset.fast_model })
    : model
      ? t("Same as the model ({model})", { model })
      : t("Same as the model");
  const errorText = (error?: string) => (error === "unreachable" ? t("The API is not reachable.") : t(error ?? ""));

  const save = async () => {
    setBusy("save");
    setNotice(null);
    const { data, error } = await call<Settings>(api.root, "PUT", "", {
      provider,
      base_url: baseUrl || null,
      model: model || null,
      fast_model: fastModel || null,
      // Left empty, the key already saved for this provider stays.
      api_key: apiKey ? apiKey : null,
    });
    setBusy(null);
    if (data) {
      adopt(data);
      setNotice({ tone: "ok", text: t("Saved. The next reply uses these settings.") });
    } else {
      setNotice({ tone: "error", text: errorText(error) });
    }
  };

  const removeKey = async () => {
    setBusy("save");
    const { data, error } = await call<Settings>(api.root, "PUT", "", {
      provider,
      base_url: baseUrl || null,
      model: model || null,
      fast_model: fastModel || null,
      api_key: "",
    });
    setBusy(null);
    if (data) adopt(data);
    setNotice(data ? { tone: "ok", text: t("The saved key was removed.") } : { tone: "error", text: errorText(error) });
  };

  const test = async () => {
    setBusy("test");
    setNotice(null);
    const { data, error } = await call<TestResult>(api.root, "POST", "/test");
    setBusy(null);
    if (data?.ok) {
      setNotice({ tone: "ok", text: t("Connected: {label} answered with {model}.", { label: data.label ?? "", model: data.model ?? "" }) });
    } else {
      setNotice({ tone: "error", text: data ? testFailure(data) : errorText(error) });
    }
  };

  const reset = async () => {
    setBusy("reset");
    setNotice(null);
    const { data, error } = await call<Settings>(api.root, "DELETE");
    setBusy(null);
    if (data) {
      adopt(data);
      setNotice({ tone: "ok", text: t("Back to the .env settings.") });
    } else {
      setNotice({ tone: "error", text: errorText(error) });
    }
  };

  const keyPlaceholder = preset && !preset.key_required
    ? t("Not needed for this provider")
    : !sameProvider
    ? t("Paste the key for this provider")
    : settings?.key_preview
      ? t("Saved ({preview}); leave empty to keep it", { preview: settings.key_preview })
      : settings?.has_key
        ? t("Set in .env ({hint}); paste one to override it", { hint: settings.key_hint ?? "" })
        : t("Not set");

  return (
    <Sheet
      title={t("Model settings")}
      onClose={onClose}
      footer={
        editable ? (
          <>
            <Button variant="primary" onClick={save} disabled={busy !== null}>
              {busy === "save" ? t("Saving…") : t("Save")}
            </Button>
            <Button onClick={test} disabled={busy !== null}>
              {busy === "test" ? t("Testing…") : t("Test connection")}
            </Button>
            {settings?.source === "page" ? (
              <button
                type="button"
                onClick={reset}
                disabled={busy !== null}
                className="ml-auto text-[12.5px] font-medium text-(--ink-soft) underline-offset-2 hover:text-(--ink) hover:underline disabled:opacity-50"
              >
                {t("Use .env instead")}
              </button>
            ) : null}
          </>
        ) : undefined
      }
    >
      {loadError ? (
        <p className="text-[13.5px] text-(--danger)">{t("The API is not reachable.")}</p>
      ) : !settings ? (
        <div className="ac-skeleton h-24 rounded-xl" />
      ) : (
        <>
          <div className="rounded-xl border border-(--line) bg-(--well) px-3.5 py-2.5 text-[13px] leading-relaxed text-(--ink)">
            <div className="font-semibold">
              {settings.label ? `${settings.label} · ${settings.model ?? t("default model")}` : t("No usable provider")}
            </div>
            <div className="text-(--ink-soft)">
              {settings.source === "page" ? t("Saved from this panel") : t("From the .env files")}
              {" · "}
              {!settings.key_required ? t("No API key needed") : settings.has_key ? t("API key set") : t("No API key")}
            </div>
            {settings.problem ? <div className="mt-1 text-(--danger)">{settings.problem}</div> : null}
          </div>
          {notice ? (
            <p role="status" className={`text-[13px] leading-relaxed ${notice.tone === "ok" ? "text-(--ok)" : "text-(--danger)"}`}>
              {notice.text}
            </p>
          ) : null}
          {!editable ? (
            <p className="text-[13px] text-(--ink-soft)">{t("This API's model is set by its environment (DEMO_MODEL_SETTINGS=0).")}</p>
          ) : null}
          <Field label={t("Provider")}>
            <select
              value={provider}
              onChange={(event) => {
                // A key typed for one provider is never sent to another.
                setProvider(event.target.value);
                setApiKey("");
                setModel("");
                setFastModel("");
              }}
              disabled={!editable}
              className={INPUT}
            >
              {settings.presets.map((p) => (
                <option key={p.name} value={p.name}>
                  {p.label}
                </option>
              ))}
            </select>
          </Field>
          <Field
            label={t("API key")}
            hint={preset && !preset.key_required ? t("This provider runs without a key.") : t("Stored on this computer only; never sent back to the page.")}
          >
            <input
              type="password"
              autoComplete="off"
              value={apiKey}
              onChange={(event) => setApiKey(event.target.value)}
              placeholder={keyPlaceholder}
              disabled={!editable}
              className={INPUT}
            />
          </Field>
          {editable && sameProvider && settings.key_preview ? (
            <button
              type="button"
              onClick={removeKey}
              disabled={busy !== null}
              className="-mt-2 self-start text-[12px] font-medium text-(--ink-soft) underline-offset-2 hover:text-(--ink) hover:underline"
            >
              {t("Remove the saved key")}
            </button>
          ) : null}
          <Field label={t("Endpoint")} hint={provider === "anthropic" ? t("Leave empty for the Anthropic API.") : undefined}>
            <input
              value={baseUrl}
              onChange={(event) => setBaseUrl(event.target.value)}
              placeholder={preset?.base_url ?? (provider === "anthropic" ? "https://api.anthropic.com" : "https://…/v1")}
              disabled={!editable}
              className={INPUT}
            />
          </Field>
          <Field label={t("Model")}>
            <ModelPicker
              value={model}
              onChange={setModel}
              models={models}
              placeholder={preset?.model ?? (needsModel ? t("Model name") : t("default model"))}
              defaultLabel={modelDefault}
              disabled={!editable}
            />
          </Field>
          {editable ? (
            <div className="-mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11.5px] leading-snug text-(--ink-soft)">
              <span className={listing.state === "error" && !listing.noKey ? "text-(--danger)" : ""}>
                {listing.state === "loading"
                  ? t("Loading the provider's models…")
                  : listing.state === "ok"
                    ? listing.models.length
                      ? needsModel
                        ? t("{n} models loaded; pick the one to use.", { n: listing.models.length })
                        : t("{n} models loaded; pick one, or leave the default.", { n: listing.models.length })
                      : t("The provider listed no models; type the model name.")
                    : listing.state === "error"
                      ? listing.text
                      : needsModel
                        ? t("This endpoint has no default; name the model.")
                        : t("Leave empty for the provider's default.")}
              </span>
              {listing.state === "ok" && listing.models.length ? (
                <button type="button" onClick={() => setTyping(!typing)} className="font-medium underline-offset-2 hover:text-(--ink) hover:underline">
                  {typing ? t("Pick from the list") : t("Type a name")}
                </button>
              ) : null}
              {listing.state !== "loading" && !(listing.state === "error" && listing.noKey) ? (
                <button type="button" onClick={loadModels} className="font-medium underline-offset-2 hover:text-(--ink) hover:underline">
                  {t("Reload list")}
                </button>
              ) : null}
            </div>
          ) : null}
          <Field label={t("Memory model")} hint={t("Extracts saved facts after each reply; a smaller model is enough.")}>
            <ModelPicker
              value={fastModel}
              onChange={setFastModel}
              models={models}
              placeholder={preset?.fast_model ?? (model || preset?.model || t("default model"))}
              defaultLabel={fastDefault}
              disabled={!editable}
            />
          </Field>
        </>
      )}
    </Sheet>
  );
}

/** The bar button that opens the panel. */
export function ModelSettingsButton({ api, className = "" }: { api: AgentApi; className?: string }) {
  const t = useT();
  const [open, setOpen] = useState(false);
  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        aria-label={t("Model settings")}
        title={t("Model settings")}
        className={`grid h-8 w-8 shrink-0 place-items-center rounded-full border border-(--line) text-(--ink-2) transition-colors hover:text-(--ink) ${className}`}
      >
        <Icon name="settings" size={16} />
      </button>
      {open ? <ModelSettingsSheet api={api} onClose={() => setOpen(false)} /> : null}
    </>
  );
}
