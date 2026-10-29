// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { formatMoney, type Translate } from "web-shared";
import type { Product } from "./types";

// --- Event date blocks -------------------------------------------------------

const MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"];
const DAYS = ["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"];

export interface DateBlock {
  mon: string;
  day: string;
  dow: string;
}

/** Built in UTC so the day does not drift with the viewer's timezone. */
export function dateBlock(isoDate?: string | null): DateBlock | null {
  if (!isoDate) return null;
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!match) return null;
  const [, year, month, day] = match;
  const utc = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
  return {
    mon: MONTHS[Number(month) - 1] ?? month,
    day: String(Number(day)),
    dow: DAYS[utc.getUTCDay()],
  };
}

export function formatTime(time?: string | null): string | null {
  if (!time) return null;
  const match = /^(\d{1,2}):(\d{2})$/.exec(time);
  if (!match) return time;
  const hour = Number(match[1]);
  const suffix = hour >= 12 ? "PM" : "AM";
  const twelve = hour % 12 === 0 ? 12 : hour % 12;
  return `${twelve}:${match[2]} ${suffix}`;
}

/** mm:ss. */
export function formatCountdown(secondsRemaining: number): string {
  const clamped = Math.max(0, secondsRemaining);
  const minutes = Math.floor(clamped / 60);
  const seconds = Math.floor(clamped % 60);
  return `${String(minutes).padStart(2, "0")}:${String(seconds).padStart(2, "0")}`;
}

/** Defaults until /api/holds reports the venue's windows; the live context carries the real ones. */
export const DEFAULT_HOLD_MINUTES = 8;
export const DEFAULT_OFFER_WINDOW_MINUTES = 10;

/** Blends amber to red over the last 60s. */
export function countdownTone(seconds: number | null): string {
  if (seconds == null || seconds > 60) return "var(--warn)";
  const pct = Math.round(((60 - Math.max(0, seconds)) / 60) * 100);
  return `color-mix(in oklab, var(--danger) ${pct}%, var(--warn))`;
}

// --- Status pills ---------------------------------------------------------------

export type PillTone = "calm" | "scarce" | "out" | "accent";

export interface StatusPill {
  label: string;
  tone: PillTone;
}

export function statusPill(product: Product): StatusPill {
  if (product.in_stock === false) return { label: "Sold out · waitlist", tone: "out" };
  if ((product.labels ?? []).some((label) => label.startsWith("Selling fast"))) {
    return { label: "Selling fast", tone: "scarce" };
  }
  return { label: "On sale", tone: "calm" };
}

export function scarcityLine(product: Product, t: Translate): string | null {
  if (!(product.labels ?? []).some((label) => label.startsWith("Selling fast"))) return null;
  const remaining = product.attributes?.tickets_remaining;
  const tier = product.attributes?.tier;
  if (!remaining || !tier) return null;
  return t("{remaining} left in {tier}", { remaining, tier });
}

// --- Fees & value scores ----------------------------------------------------------

export interface FeeParts {
  base: number;
  baseLabel: "Face value" | "Seller price";
  service: number;
  facility: number;
  processing: number;
}

export function feeParts(product: Product): FeeParts | null {
  const attrs = product.attributes ?? {};
  const face = Number(attrs.face_price_usd);
  const seller = Number(attrs.seller_price_usd);
  const base = Number.isFinite(face) ? face : seller;
  const service = Number(attrs.service_fee_usd);
  const facility = Number(attrs.facility_fee_usd);
  const processing = Number(attrs.processing_fee_usd);
  if (![base, service, facility, processing].every(Number.isFinite)) return null;
  return {
    base,
    baseLabel: Number.isFinite(face) ? "Face value" : "Seller price",
    service,
    facility,
    processing,
  };
}

export function soldTogetherCount(product: Product): number {
  const parsed = Number(product.attributes?.sold_together);
  return Number.isFinite(parsed) && parsed > 1 ? parsed : 1;
}

export interface ValueScore {
  score: number;
  verdict: "green" | "amber" | "red";
  vsFace: string;
  boxAllIn: number | null;
}

/** Backend-computed. */
export function valueScore(product: Product): ValueScore | null {
  const attrs = product.attributes ?? {};
  const score = Number(attrs.value_score);
  const verdict = attrs.value_verdict;
  if (!Number.isFinite(score) || !verdict) return null;
  const boxAllIn = Number(attrs.box_office_all_in_usd);
  return {
    score,
    verdict: verdict === "green" || verdict === "amber" || verdict === "red" ? verdict : "amber",
    vsFace: attrs.vs_box_office ?? "",
    boxAllIn: Number.isFinite(boxAllIn) ? boxAllIn : null,
  };
}

export function valueScoreBasis(value: ValueScore, t: Translate): string {
  const delta = value.vsFace.replace("+", "");
  const pct = value.vsFace.startsWith("-") ? delta.replace("-", "") : delta;
  const direction = value.vsFace.startsWith("-")
    ? t("{pct} below", { pct })
    : value.vsFace === "+0%" || value.vsFace === "0%"
      ? t("level with")
      : t("{pct} above", { pct });
  return value.boxAllIn != null
    ? t("{direction} the box-office all-in price ({price}) for the same tier", {
        direction,
        price: formatMoney(value.boxAllIn),
      })
    : t("{direction} the box-office all-in price for the same tier", { direction });
}

// --- Tier legend colors ---------------------------------------------------------

/** Kept distinct from the warn and danger hues. */
const TIER_COLORS = [
  "var(--tier-1)",
  "var(--tier-2)",
  "var(--tier-3)",
  "var(--tier-4)",
] as const;

/** Assigned by price descending; map, legend, and list share it. */
export function tierColorMap(
  tiers: { product_id: string; price: number }[],
): Record<string, string> {
  const distinct = [...new Map(tiers.map((tier) => [tier.product_id, tier])).values()];
  distinct.sort((a, b) => b.price - a.price);
  return Object.fromEntries(
    distinct.map((tier, index) => [tier.product_id, TIER_COLORS[index % TIER_COLORS.length]]),
  );
}
