// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { formatMoney } from "web-shared";
import type { AccountContext, Product } from "./types";

type Catalog = Record<string, Product>;

type Line = { product_id: string; line_total: number };

export function formatPrice(value: number, currency = "USD"): string {
  return formatMoney(value, currency, { whole: Number.isInteger(value) });
}

export function formatPriceWithUnit(product: Product): string {
  const base = formatPrice(product.price, product.currency);
  return product.attributes?.price_unit === "per_month" ? `${base}/mo` : base;
}

export function plateGlyph(product: Product): string {
  const title = product.title;
  const patterns: [RegExp, (m: RegExpMatchArray) => string][] = [
    [/Phone (\d+) (Pro|Max|Lite)/, (m) => `${m[1]} ${m[2]}`],
    [/Phone (\d+)/, (m) => `Phone ${m[1]}`],
    [/Tablet (\d+)/, (m) => `Tab ${m[1]}`],
    [/Watch/, () => "Watch"],
    [/(\d+) Gig/, (m) => `${m[1]} Gig`],
    [/Fiber (\d+)/, (m) => `${m[1]}`],
    [/(\d+)GB/, (m) => `${m[1]}GB`],
    [/Unlimited Plus/, () => "U·Plus"],
    [/Unlimited/, () => "U"],
  ];
  for (const [pattern, pick] of patterns) {
    const match = title.match(pattern);
    if (match) return pick(match);
  }
  const word = title.split(" ").find((w) => w.length > 2);
  return word ?? title.slice(0, 6);
}

export function plateTint(product: Product): string {
  switch (product.category) {
    case "plans":
      return "linear-gradient(135deg, rgba(0,184,107,0.10), rgba(0,184,107,0.02))";
    case "home-internet":
      return "linear-gradient(135deg, rgba(14,17,22,0.08), rgba(14,17,22,0.02))";
    case "devices":
      return "linear-gradient(135deg, rgba(86,93,102,0.14), rgba(86,93,102,0.03))";
    default:
      return "linear-gradient(135deg, rgba(184,122,0,0.08), rgba(184,122,0,0.02))";
  }
}

/** Falls back to the id prefix until the catalog loads. */
export function priceUnitOf(productId: string, catalog: Catalog): string {
  const product = catalog[productId];
  if (product) return product.attributes?.price_unit ?? "one_time";
  return /-(PLAN|NET)-/.test(productId) ? "per_month" : "one_time";
}

export function splitCart(items: Line[], catalog: Catalog): { monthly: number; today: number } {
  let monthly = 0;
  let today = 0;
  for (const item of items) {
    if (priceUnitOf(item.product_id, catalog) === "per_month") monthly += item.line_total;
    else today += item.line_total;
  }
  return { monthly, today };
}

/** A staged plan replaces the current one; other recurring lines add on. */
export function billAfterOrder(
  account: AccountContext | null | undefined,
  items: Line[],
  catalog: Catalog,
): { before: number; after: number; replacesPlan: boolean } | null {
  const before = account?.monthly_bill_usd;
  if (account == null || before == null) return null;
  const { monthly: stagedMonthly } = splitCart(items, catalog);
  const replacesPlan =
    items.some((item) => /-PLAN-/.test(item.product_id)) &&
    account.current_plan?.price_per_month != null;
  const currentPlan = replacesPlan ? (account.current_plan.price_per_month ?? 0) : 0;
  const after = Math.round((before - currentPlan + stagedMonthly) * 100) / 100;
  return { before, after, replacesPlan };
}

/** Average monthly data against the plan's cap; `cap` is null on unlimited plans. */
export function usageOf(account: AccountContext): { avg: number; cap: number | null; over: boolean; share: number } {
  const avg = account.recent_usage.avg_gb_per_month_last_3;
  const allowance = account.current_plan.data_allowance_gb;
  const cap = allowance != null && allowance !== "unlimited" && Number(allowance) > 0 ? Number(allowance) : null;
  return { avg, cap, over: cap != null && avg > cap, share: cap != null ? Math.min(avg / cap, 1) : 0.5 };
}
