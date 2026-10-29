// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** Retail-specific labels on top of web-shared's formatters. */

import { formatDayMonth, formatMoney, type RecordRowData, type Translate, titleCase } from "web-shared";
import { ORDER_STATUS } from "./kinds";
import { pluralT } from "./labels";
import type { RecentOrder } from "./types";

const CATEGORY_LABELS: Record<string, string> = {
  "beauty-personal-care": "Beauty & personal care",
  fitness: "Fitness",
  "furniture-bedroom": "Furniture & bedroom",
  grocery: "Grocery",
  "home-kitchen": "Home & kitchen",
  "kids-room": "Kids' room",
  "office-electronics": "Office & electronics",
  "outdoor-camping": "Outdoor & camping",
  "pet-supplies": "Pet supplies",
  "toys-games": "Toys & games",
  travel: "Travel",
};

export function formatCategoryLabel(slug: string, t: Translate): string {
  return t(CATEGORY_LABELS[slug] ?? titleCase(slug.replaceAll("-", "_")));
}

export function orderRows(orders: RecentOrder[], t: Translate): RecordRowData[] {
  return orders.map((order) => ({
    id: order.order_id,
    detail: pluralT(t, order.items, "{count} item", "{count} items"),
    sub: `${formatDayMonth(order.placed_at)} · ${formatMoney(order.total)}`,
    status: ORDER_STATUS[order.status]
      ? { ...ORDER_STATUS[order.status], label: t(ORDER_STATUS[order.status].label) }
      : { label: t(order.status.replaceAll("_", " ")), tone: "muted" },
  }));
}
