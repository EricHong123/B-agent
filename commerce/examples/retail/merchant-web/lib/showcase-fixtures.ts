// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** Copied from the retail merchant fixtures under data/. */

import type { ChangePreviewPayload, DigestPayload } from "./types";

const digest: DigestPayload = {
  title: "Morning digest",
  items: [
    {
      kind: "low_stock",
      ref_id: "AR-2102",
      headline: "3 units left of the ocean wall decals (AR-2102) — under two days of cover",
      why_it_matters: "Selling roughly 52 units a month; at that pace the listing goes dark this week.",
      listing: {
        listing_id: "AR-2102",
        title: "ACME Kids Peel-and-Stick Ocean Wall Decals (36 pc)",
        status: "active",
        price: 24.0,
        stock: 3,
      },
    },
    {
      kind: "order_issue",
      ref_id: "AR-80417",
      headline: "Six returns on the travel pillow this week, all citing firmness",
      why_it_matters: "A return spike on a top seller usually means a listing-content gap.",
    },
    {
      kind: "metric",
      headline: "Kids' room sales are up 21% week-over-week",
      why_it_matters: "Most of the lift traces to the under-the-sea decor line.",
    },
  ],
};

const change_preview: ChangePreviewPayload = {
  change_id: "chg-3021",
  headline: "Refill AR-2102 before it sells out",
  note: "Puts about a month of cover back on the shelf at the trailing sales pace.",
  change: {
    change_id: "chg-3021",
    kind: "inventory_action",
    status: "staged",
    summary: "Add 52 units of ACME Kids Peel-and-Stick Ocean Wall Decals (AR-2102)",
    items: [{ target: "AR-2102", field: "stock", before: 3, after: 55 }],
    created_at: "2026-07-09",
    created_by: "Avery",
    created_by_kind: "agent",
  },
};

export const SHOWCASE = { digest, change_preview };
