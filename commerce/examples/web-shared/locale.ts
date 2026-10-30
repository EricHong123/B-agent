// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/**
 * The locale cookie, readable from a server layout and from the browser. The layout reads it to
 * render the language the client hydrates with; i18n.tsx writes it.
 */
export type Locale = "en" | "zh";

export const LOCALE_COOKIE = "acme-locale";

export function parseLocale(value: string | null | undefined): Locale {
  return value === "zh" ? "zh" : "en";
}

/** The `lang` attribute for a locale. */
export function htmlLang(locale: Locale): string {
  return locale === "zh" ? "zh-CN" : "en";
}

/** The locale in `document.cookie`, for code outside React (the API client). */
export function cookieLocale(): Locale {
  if (typeof document === "undefined") return "en";
  const match = document.cookie.match(new RegExp(`(?:^|; )${LOCALE_COOKIE}=([^;]*)`));
  return parseLocale(match?.[1]);
}
