// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** Counts from data/inventory.json and merchant_pacing.json; metrics from merchant_metrics.json. */

import type {
  ChangePreviewPayload,
  DigestPayload,
  EventPacingPayload,
  MetricsPayload,
  StagedChange,
} from "./types";

const TERRACE_EASE: StagedChange = {
  change_id: "chg-4102",
  kind: "price_update",
  status: "staged",
  summary: "Terrace ease for the final stretch (AT-TIX-101-TER, all-in $54.50 → $48.50)",
  items: [{ target: "AT-TIX-101-TER", field: "price", before: 54.5, after: 48.5 }],
  created_at: "2026-07-27",
  created_by: "Jo",
  created_by_kind: "agent",
  currency: "USD",
  // Price delta × the tier's recent weekly sales (31 tickets/week).
  margin_impact: -186.0,
  // Backend-computed per-ticket margins around the move (cost = $15.50 fees + 68% of
  // face): $42.02 under the $54.50 sticker, $37.94 under $48.50.
  margin_before_pct: 22.9,
  margin_after_pct: 21.8,
  guardrail_notes: [
    "AT-TIX-101-TER: all-in $54.50 → $48.50; itemized fees $15.50 stay fixed, face value $39.00 → $33.00",
  ],
};

const change_preview: ChangePreviewPayload = {
  change_id: "chg-4102",
  headline: "Upper Terrace price ease — The Headliner, Fri Aug 14",
  note: "Eases the Terrace from $54.50 to $48.50 a ticket for the final 18 days; the itemized fees stay fixed, so only the face value moves.",
  change: TERRACE_EASE,
};

const metrics: MetricsPayload = {
  title: "Last week at the box office",
  period: "2026-07-20/2026-07-26",
  metrics: [
    {
      metric: "sales",
      value: 55794.5,
      change_pct: 5.6,
      currency: "USD",
      series: {
        metric: "sales",
        granularity: "day",
        points: [
          { date: "2026-07-20", value: 7689.04 },
          { date: "2026-07-21", value: 7475.31 },
          { date: "2026-07-22", value: 6816.65 },
          { date: "2026-07-23", value: 6912.61 },
          { date: "2026-07-24", value: 8875.95 },
          { date: "2026-07-25", value: 9667.22 },
          { date: "2026-07-26", value: 8357.72 },
        ],
      },
    },
    { metric: "orders", value: 286, change_pct: 4.0 },
    { metric: "tickets", value: 697, change_pct: 9.1 },
    { metric: "average_order_value", value: 195.09, change_pct: 1.6, currency: "USD" },
  ],
};

const digest: DigestPayload = {
  title: "Morning check — the Friday ACME Amphitheater show",
  items: [
    {
      kind: "low_stock",
      ref_id: "AT-TIX-101-PIT",
      headline: "GA Pit is down to 6 open seats",
      why_it_matters:
        "344 of 350 sold with 18 days to go — decide on the 14 releasable held seats before the final push.",
      listing: {
        listing_id: "AT-TIX-101-PIT",
        title: "The Headliner — Summer Tour · Fri Aug 14 · GA Pit",
        status: "active",
        price: 112.0,
        currency: "USD",
        stock: 6,
      },
    },
    {
      kind: "slow_mover",
      ref_id: "AT-TIX-101-TER",
      headline: "Upper Terrace is 32.7 pts behind its baseline",
      why_it_matters:
        "38.7% sold vs 71.4% for comparable amphitheater shows at 18 days out, and 90 promoter-hold seats are still off sale.",
      listing: {
        listing_id: "AT-TIX-101-TER",
        title: "The Headliner — Summer Tour · Fri Aug 14 · Upper Terrace",
        status: "active",
        price: 54.5,
        currency: "USD",
        stock: 552,
      },
    },
    {
      kind: "pending_change",
      ref_id: "chg-4102",
      headline: "Terrace price ease awaits your approval",
      why_it_matters: "Staged only — nothing moves until you approve it on the preview card.",
      change: TERRACE_EASE,
    },
  ],
};

const event_pacing: EventPacingPayload = {
  grain: "week",
  events: [
    {
      event_id: "AT-EVT-101",
      event_name: "The Headliner — Summer Tour",
      venue: "ACME Amphitheater",
      city: "Springfield",
      event_date: "2026-08-14",
      on_sale_date: "2026-05-08",
      days_to_event: 18,
      baseline_kind: "amphitheater",
      note: "Upper Terrace is the gap: 38.7% sold against a 71.4% baseline at 18 days out, with 90 promoter-hold seats still off sale.",
      tiers: [
        {
          product_id: "AT-TIX-101-PIT",
          tier: "GA Pit",
          price: 112.0,
          currency: "USD",
          capacity: 350,
          sold: 344,
          remaining: 6,
          sell_through_pct: 98.3,
          baseline_pct: 71.4,
          pace_vs_baseline_pts: 26.9,
          waitlist_depth: 0,
          holds: { promoter_hold: 8, production_hold: 6, comps: 8, kills: 0 },
          weekly_sold_cum: [
            { week_start: "2026-05-04", sold_cum: 5 },
            { week_start: "2026-05-11", sold_cum: 25 },
            { week_start: "2026-05-18", sold_cum: 51 },
            { week_start: "2026-05-25", sold_cum: 75 },
            { week_start: "2026-06-01", sold_cum: 100 },
            { week_start: "2026-06-08", sold_cum: 125 },
            { week_start: "2026-06-15", sold_cum: 152 },
            { week_start: "2026-06-22", sold_cum: 186 },
            { week_start: "2026-06-29", sold_cum: 224 },
            { week_start: "2026-07-06", sold_cum: 264 },
            { week_start: "2026-07-13", sold_cum: 292 },
            { week_start: "2026-07-20", sold_cum: 344 },
          ],
          recent_weekly_sales: 30.0,
        },
        {
          product_id: "AT-TIX-101-LOW",
          tier: "Lower Bowl",
          price: 89.0,
          currency: "USD",
          capacity: 1200,
          sold: 815,
          remaining: 385,
          sell_through_pct: 67.9,
          baseline_pct: 71.4,
          pace_vs_baseline_pts: -3.5,
          waitlist_depth: 0,
          holds: { promoter_hold: 60, production_hold: 24, comps: 18, kills: 0 },
          weekly_sold_cum: [
            { week_start: "2026-05-04", sold_cum: 12 },
            { week_start: "2026-05-11", sold_cum: 60 },
            { week_start: "2026-05-18", sold_cum: 120 },
            { week_start: "2026-05-25", sold_cum: 172 },
            { week_start: "2026-06-01", sold_cum: 243 },
            { week_start: "2026-06-08", sold_cum: 304 },
            { week_start: "2026-06-15", sold_cum: 371 },
            { week_start: "2026-06-22", sold_cum: 444 },
            { week_start: "2026-06-29", sold_cum: 515 },
            { week_start: "2026-07-06", sold_cum: 596 },
            { week_start: "2026-07-13", sold_cum: 710 },
            { week_start: "2026-07-20", sold_cum: 815 },
          ],
          recent_weekly_sales: 75.0,
        },
        {
          product_id: "AT-TIX-101-TER",
          tier: "Upper Terrace",
          price: 54.5,
          currency: "USD",
          capacity: 900,
          sold: 348,
          remaining: 552,
          sell_through_pct: 38.7,
          baseline_pct: 71.4,
          pace_vs_baseline_pts: -32.7,
          waitlist_depth: 0,
          holds: { promoter_hold: 90, production_hold: 0, comps: 10, kills: 40 },
          weekly_sold_cum: [
            { week_start: "2026-05-04", sold_cum: 5 },
            { week_start: "2026-05-11", sold_cum: 25 },
            { week_start: "2026-05-18", sold_cum: 49 },
            { week_start: "2026-05-25", sold_cum: 76 },
            { week_start: "2026-06-01", sold_cum: 101 },
            { week_start: "2026-06-08", sold_cum: 129 },
            { week_start: "2026-06-15", sold_cum: 157 },
            { week_start: "2026-06-22", sold_cum: 190 },
            { week_start: "2026-06-29", sold_cum: 224 },
            { week_start: "2026-07-06", sold_cum: 265 },
            { week_start: "2026-07-13", sold_cum: 302 },
            { week_start: "2026-07-20", sold_cum: 348 },
          ],
          recent_weekly_sales: 31.0,
        },
      ],
    },
  ],
};

export const SHOWCASE = { metrics, digest, change_preview, event_pacing };
