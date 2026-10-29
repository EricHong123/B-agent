// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { createContext, type ReactNode, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { SHARED_ZH } from "./i18n-zh";
import { htmlLang, type Locale, LOCALE_COOKIE } from "./locale";

export type { Locale } from "./locale";

/**
 * The web apps' two languages. English is the source text: `t("Your bag")` looks the string up
 * in the Chinese table and returns it unchanged in English or when no entry exists. `{name}`
 * placeholders are filled from `vars` in either language. The choice lives in the
 * `acme-locale` cookie, so the server renders the language the client hydrates with, and one
 * switch applies to every app on localhost.
 */
export type Messages = Readonly<Record<string, string>>;
export type Translate = (text: string, vars?: Record<string, string | number>) => string;

function fill(text: string, vars?: Record<string, string | number>): string {
  if (!vars) return text;
  return text.replace(/\{(\w+)\}/g, (whole, name: string) =>
    name in vars ? String(vars[name]) : whole,
  );
}

export function translate(
  locale: Locale,
  messages: Messages,
  text: string,
  vars?: Record<string, string | number>,
): string {
  return fill(locale === "zh" ? (messages[text] ?? text) : text, vars);
}

interface LocaleState {
  locale: Locale;
  setLocale: (locale: Locale) => void;
  t: Translate;
}

const english: Translate = (text, vars) => fill(text, vars);
// Dispatched on window when a provider switches, so every provider on the page follows.
const LOCALE_EVENT = "acme-locale-change";
const LocaleContext = createContext<LocaleState>({
  locale: "en",
  setLocale: () => {},
  t: english,
});

/** Wraps an app in its layout. `messages` is the app's own table, merged over the shared one. */
export function LocaleProvider({
  initial,
  messages,
  children,
}: {
  initial: Locale;
  messages?: Messages;
  children: ReactNode;
}) {
  const [locale, setState] = useState<Locale>(initial);
  const table = useMemo(() => ({ ...SHARED_ZH, ...messages }), [messages]);
  const setLocale = useCallback((next: Locale) => {
    document.cookie = `${LOCALE_COOKIE}=${next}; path=/; max-age=31536000; samesite=lax`;
    document.documentElement.lang = htmlLang(next);
    setState(next);
    window.dispatchEvent(new CustomEvent<Locale>(LOCALE_EVENT, { detail: next }));
  }, []);
  // Another app on the same page switched: follow it.
  useEffect(() => {
    const follow = (event: Event) => setState((event as CustomEvent<Locale>).detail);
    window.addEventListener(LOCALE_EVENT, follow);
    return () => window.removeEventListener(LOCALE_EVENT, follow);
  }, []);
  const t = useCallback<Translate>(
    (text, vars) => translate(locale, table, text, vars),
    [locale, table],
  );
  const value = useMemo(() => ({ locale, setLocale, t }), [locale, setLocale, t]);
  return <LocaleContext.Provider value={value}>{children}</LocaleContext.Provider>;
}

export function useLocale(): LocaleState {
  return useContext(LocaleContext);
}

/** The translate function for the current locale. */
export function useT(): Translate {
  return useContext(LocaleContext).t;
}

/** The EN / 中文 switch both shells carry in their bars. */
export function LanguageToggle({ className = "" }: { className?: string }) {
  const { locale, setLocale, t } = useLocale();
  const next: Locale = locale === "zh" ? "en" : "zh";
  return (
    <button
      type="button"
      onClick={() => setLocale(next)}
      aria-label={t("Switch language")}
      title={t("Switch language")}
      className={`inline-flex h-8 shrink-0 items-center rounded-full border border-(--line) px-2.5 text-[12.5px] font-semibold text-(--ink-2) transition-colors hover:text-(--ink) ${className}`}
    >
      {next === "zh" ? "中文" : "EN"}
    </button>
  );
}
