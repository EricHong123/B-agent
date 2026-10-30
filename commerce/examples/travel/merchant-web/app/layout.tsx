// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import type { Metadata } from "next";
import { cookies } from "next/headers";
import { LocaleProvider } from "web-shared/i18n";
import { htmlLang, LOCALE_COOKIE, parseLocale } from "web-shared/locale";
import { ZH } from "../lib/i18n-zh";
import { fontVariables } from "./fonts";
import "./globals.css";

export const metadata: Metadata = {
  title: "ACME Travel Merchant",
  description: "The ACME Travel back office, an example for the merchant agent.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = parseLocale((await cookies()).get(LOCALE_COOKIE)?.value);
  return (
    <html lang={htmlLang(locale)} suppressHydrationWarning className={fontVariables}>
      <body suppressHydrationWarning>
        <LocaleProvider initial={locale} messages={ZH}>
          {children}
        </LocaleProvider>
      </body>
    </html>
  );
}
