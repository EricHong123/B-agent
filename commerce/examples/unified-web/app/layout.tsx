// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import type { Metadata } from "next";
import { cookies } from "next/headers";
import { htmlLang, LOCALE_COOKIE, parseLocale } from "web-shared/locale";
import "./globals.css";

export const metadata: Metadata = {
  title: "ACME",
  description: "The ACME storefronts and merchant portals in one app.",
};

export default async function RootLayout({ children }: { children: React.ReactNode }) {
  const locale = parseLocale((await cookies()).get(LOCALE_COOKIE)?.value);
  return (
    <html lang={htmlLang(locale)} suppressHydrationWarning>
      <body suppressHydrationWarning>{children}</body>
    </html>
  );
}
