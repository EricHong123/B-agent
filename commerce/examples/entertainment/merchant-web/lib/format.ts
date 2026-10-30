// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { formatChangePct, formatNumber, type Translate } from "web-shared";

/** Signed percentage points against baseline. */
export function formatPacePts(value: number, t: Translate): string {
  const sign = value > 0 ? "+" : "";
  return t("{value} pts", { value: `${sign}${value.toFixed(1)}` });
}

export function formatDaysToEvent(days: number | null | undefined, t: Translate): string {
  if (days == null) return "";
  if (days < 0) return t("past");
  if (days === 0) return t("tonight");
  return t(days === 1 ? "in {n} day" : "in {n} days", { n: formatNumber(days) });
}

/** "3 events": the caller passes the singular and plural source strings, each with an `{n}` placeholder. */
export function countLabel(t: Translate, count: number, one: string, many: string): string {
  return t(count === 1 ? one : many, { n: formatNumber(count) });
}

/** "Good morning" before noon, "Good afternoon" until six, then "Good evening". */
export function greetingFor(now: Date, t: Translate): string {
  const hour = now.getHours();
  if (hour < 12) return t("Good morning");
  if (hour < 18) return t("Good afternoon");
  return t("Good evening");
}

/** The question a KPI tile prefills: why the figure moved against the comparison window. */
export function askWhy(t: Translate, label: string, changePct: number | null | undefined, comparison: string): string {
  const name = t(label).toLowerCase();
  if (changePct == null) return t("How is {name} trending, and what's behind it?", { name });
  return t(changePct >= 0 ? "Why is {name} up {pct}% against the {comparison}?" : "Why is {name} down {pct}% against the {comparison}?", {
    name,
    pct: Math.abs(changePct).toFixed(1),
    comparison: comparison ? t(comparison) : t("prior period"),
  });
}

/** "sells out in ~4 days", "sells out within a day". */
export function runwayLabel(days: number, t: Translate): string {
  if (days < 1) return t("sells out within a day");
  const rounded = Math.round(days);
  return t(rounded === 1 ? "sells out in ~{n} day" : "sells out in ~{n} days", { n: formatNumber(rounded) });
}

/** The percent change that follows "up" or "down" in the briefing, unsigned. */
export function unsignedChangePct(value: number): string {
  return formatChangePct(Math.abs(value)).replace("+", "");
}
