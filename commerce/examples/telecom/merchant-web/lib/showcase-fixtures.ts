// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import type {
  ChangePreviewPayload,
  DigestPayload,
  MetricsPayload,
  PlanMixPayload,
} from "./types";

/** Payloads for /showcase, taken from data/merchant_subscribers.json and the catalog. */

const metrics: MetricsPayload = {
  title: "Essential 5GB — base health",
  period: "2026-04-27/2026-07-20",
  metrics: [
    {
      metric: "churn_rate",
      value: 2.1,
      change_pct: 7.7,
      note: "Highest in the base — up 13 straight weeks from 1.46%.",
      series: {
        metric: "churn_rate",
        unit: "%",
        granularity: "week",
        points: [
          { date: "2026-04-27", value: 1.46 },
          { date: "2026-05-04", value: 1.51 },
          { date: "2026-05-11", value: 1.52 },
          { date: "2026-05-18", value: 1.49 },
          { date: "2026-05-25", value: 1.61 },
          { date: "2026-06-01", value: 1.62 },
          { date: "2026-06-08", value: 1.64 },
          { date: "2026-06-15", value: 1.75 },
          { date: "2026-06-22", value: 1.72 },
          { date: "2026-06-29", value: 1.8 },
          { date: "2026-07-06", value: 1.9 },
          { date: "2026-07-13", value: 1.95 },
          { date: "2026-07-20", value: 2.1 },
        ],
      },
    },
    { metric: "subscribers", value: 12400, note: "25.0% of the 49,620-line base." },
    { metric: "arpu", value: 38.4 },
    { metric: "margin_per_line", value: 25.07, note: "Against $13.33 wholesale per line." },
  ],
};

const digest: DigestPayload = {
  title: "This morning's base digest",
  items: [
    {
      kind: "metric",
      ref_id: "AM-PLAN-101",
      headline: "Essential 5GB churn hit 2.1% — highest in the base, rising 13 straight weeks",
      why_it_matters:
        "12,400 lines at $25.07 margin per line — every tenth of a point of weekly churn is roughly a dozen lines walking out.",
    },
    {
      kind: "note",
      ref_id: "top-up-heavy",
      headline: "1,310 Essential lines bought 2+ data top-ups in each of the last two cycles",
      why_it_matters:
        "They are paying more than Plus 15GB would cost — a right-plan move saves them money and defuses the churn driver.",
    },
    {
      kind: "low_stock",
      ref_id: "AM-DEV-202",
      headline: "ACME Phone 5 is below its restock threshold",
      why_it_matters:
        "18 units on hand against a 40-unit threshold, selling 176 in 30 days — about three days of cover.",
      listing: {
        listing_id: "AM-DEV-202",
        title: "ACME Phone 5",
        status: "active",
        price: 949.0,
        stock: 18,
        category: "devices",
      },
    },
  ],
};

const change_preview: ChangePreviewPayload = {
  change_id: "chg-4203",
  headline: "Standing price move — Essential 5GB",
  note: "Moves Essential 5GB from $35.00 to $37.00 a month; margin per line rises from $25.07 to $27.07 against $13.33 wholesale.",
  change: {
    change_id: "chg-4203",
    kind: "price_update",
    status: "staged",
    summary: "Essential 5GB standing price $35.00 → $37.00 (+5.7%)",
    items: [{ target: "AM-PLAN-101", field: "price", before: 35.0, after: 37.0 }],
    created_at: "2026-07-21",
    created_by: "Sam",
    created_by_kind: "agent",
    margin_impact: 24800.0,
    // Margin fields make the card render its headroom bar.
    margin_before_pct: 61.9,
    margin_after_pct: 64.0,
    guardrail_notes: [
      "AM-PLAN-101 affects 12,400 active lines on Essential 5GB — every one sees the new price at their next bill cycle",
      "Churn on this plan is already 2.1%/week and rising — pair a price move with the top-up-heavy right-plan outreach.",
    ],
  },
};

const plan_mix: PlanMixPayload = {
  title: "Where the base sits — Essential 5GB vs Unlimited Plus",
  total_subscribers: 49620,
  grain: "week",
  plans: [
    {
      plan_id: "AM-PLAN-101",
      title: "Essential 5GB",
      kind: "mobile",
      price: 35.0,
      currency: "USD",
      subscribers: 12400,
      share_pct: 25.0,
      churn_rate_pct: 2.1,
      arpu: 38.4,
      avg_usage_gb: 4.6,
      wholesale_cost_per_line_usd: 13.33,
      margin_per_line_usd: 25.07,
      note: "The volume plan and the churn problem: a quarter of the base, thinning at 2.1%/week.",
      weeks: [
        { week_start: "2026-06-15", subscribers: 12479, churn_rate_pct: 1.75, arpu: 38.13 },
        { week_start: "2026-06-22", subscribers: 12464, churn_rate_pct: 1.72, arpu: 38.17 },
        { week_start: "2026-06-29", subscribers: 12507, churn_rate_pct: 1.8, arpu: 38.34 },
        { week_start: "2026-07-06", subscribers: 12464, churn_rate_pct: 1.9, arpu: 38.36 },
        { week_start: "2026-07-13", subscribers: 12381, churn_rate_pct: 1.95, arpu: 38.22 },
        { week_start: "2026-07-20", subscribers: 12400, churn_rate_pct: 2.1, arpu: 38.4 },
      ],
    },
    {
      plan_id: "AM-PLAN-104",
      title: "Unlimited Plus",
      kind: "mobile",
      price: 85.0,
      currency: "USD",
      subscribers: 4300,
      share_pct: 8.7,
      churn_rate_pct: 0.6,
      arpu: 87.0,
      avg_usage_gb: 38.0,
      wholesale_cost_per_line_usd: 65.1,
      margin_per_line_usd: 21.9,
      weeks: [
        { week_start: "2026-06-15", subscribers: 4229, churn_rate_pct: 0.58, arpu: 86.6 },
        { week_start: "2026-06-22", subscribers: 4237, churn_rate_pct: 0.64, arpu: 86.98 },
        { week_start: "2026-06-29", subscribers: 4261, churn_rate_pct: 0.6, arpu: 86.59 },
        { week_start: "2026-07-06", subscribers: 4262, churn_rate_pct: 0.58, arpu: 86.75 },
        { week_start: "2026-07-13", subscribers: 4298, churn_rate_pct: 0.56, arpu: 86.69 },
        { week_start: "2026-07-20", subscribers: 4300, churn_rate_pct: 0.6, arpu: 87.0 },
      ],
    },
  ],
};

export const SHOWCASE = { metrics, digest, change_preview, plan_mix };
