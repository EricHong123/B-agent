// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import type { Translate } from "./i18n";

/**
 * The default `t` of helpers that take an optional one: English as written, `{name}` filled.
 * It lives apart from i18n.tsx so server and plain modules can use it without the client context.
 */
export const english: Translate = (text, vars) =>
  vars ? text.replace(/\{(\w+)\}/g, (whole, name: string) => (name in vars ? String(vars[name]) : whole)) : text;
