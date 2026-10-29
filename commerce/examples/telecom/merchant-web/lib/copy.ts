// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** Wording helpers that take the translate function, for text the shared helpers build in English. */

import { formatNumber, type Translate } from "web-shared";

/** "12 days": picks between two English keys, each with an `{n}` placeholder. */
export function count(t: Translate, n: number, one: string, many: string): string {
  return t(n === 1 ? one : many, { n: formatNumber(n) });
}

export function greetingText(t: Translate, now: Date): string {
  const hour = now.getHours();
  if (hour < 12) return t("Good morning");
  if (hour < 18) return t("Good afternoon");
  return t("Good evening");
}

export function coverText(t: Translate, days: number): string {
  if (days < 1) return t("<1 day of cover");
  return count(t, Math.round(days), "{n} day of cover", "{n} days of cover");
}

/** The question a KPI tile prefills: why the figure moved against the comparison window. */
export function askWhyText(t: Translate, label: string, changePct: number | null | undefined, comparison: string): string {
  const name = t(label).toLowerCase();
  if (changePct == null) return t("How is {name} trending, and what's behind it?", { name });
  const pct = Math.abs(changePct).toFixed(1);
  const against = comparison || t("prior period");
  return t(changePct >= 0 ? "Why is {name} up {pct}% against the {comparison}?" : "Why is {name} down {pct}% against the {comparison}?", {
    name,
    pct,
    comparison: against,
  });
}

export function proposerText(
  t: Translate,
  change: { created_by: string; created_by_kind?: "operator" | "agent" },
): string {
  return t(change.created_by_kind === "agent" ? "Proposed by {name}'s assistant" : "Staged by {name}", { name: change.created_by });
}

/** Splits a translated sentence around a `{slot}` that holds a React node. */
export function aroundSlot(t: Translate, text: string): [string, string] {
  const [before, after = ""] = t(text, { slot: "\u0000" }).split("\u0000");
  return [before, after];
}
