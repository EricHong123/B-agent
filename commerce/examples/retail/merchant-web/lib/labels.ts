// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** Translated counterparts of web-shared's English-only label helpers. */

import { formatNumber, type Translate } from "web-shared";

/** `plural(t, 3, "{count} order", "{count} orders")`; both keys carry the `{count}` placeholder. */
export function pluralT(t: Translate, count: number, one: string, many: string): string {
  return t(count === 1 ? one : many, { count: formatNumber(count) });
}

/** "12 days of cover", "1 day of cover", "<1 day of cover". */
export function coverText(t: Translate, days: number): string {
  return days < 1 ? t("<1 day of cover") : pluralT(t, Math.round(days), "{count} day of cover", "{count} days of cover");
}

/** "Good morning" before noon, "Good afternoon" until six, then "Good evening". */
export function greetingText(t: Translate, now: Date): string {
  const hour = now.getHours();
  if (hour < 12) return t("Good morning");
  if (hour < 18) return t("Good afternoon");
  return t("Good evening");
}

/** The question a KPI tile prefills: why the figure moved against the comparison window. */
export function askWhyText(t: Translate, label: string, changePct: number | null | undefined, comparison: string): string {
  const name = t(label).toLowerCase();
  if (changePct == null) return t("How is {name} trending, and what's behind it?", { name });
  const vars = { name, pct: Math.abs(changePct).toFixed(1), comparison: t(comparison || "prior period") };
  return changePct >= 0 ? t("Why is {name} up {pct}% against the {comparison}?", vars) : t("Why is {name} down {pct}% against the {comparison}?", vars);
}

/** "Proposed by Avery's assistant" or "Staged by Avery". */
export function proposerText(t: Translate, change: { created_by: string; created_by_kind?: "operator" | "agent" }): string {
  return change.created_by_kind === "agent" ? t("Proposed by {name}'s assistant", { name: change.created_by }) : t("Staged by {name}", { name: change.created_by });
}
