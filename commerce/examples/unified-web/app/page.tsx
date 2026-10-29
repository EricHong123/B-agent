// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { cookies } from "next/headers";
import { LOCALE_COOKIE, parseLocale } from "web-shared/locale";
import UnifiedApp from "../components/UnifiedApp";

export default async function Page() {
  const locale = parseLocale((await cookies()).get(LOCALE_COOKIE)?.value);
  return <UnifiedApp initialLocale={locale} />;
}
