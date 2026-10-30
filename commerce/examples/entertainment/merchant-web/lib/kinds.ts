// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** How each kind of box-office record shows: its label, icon, and tone. */

import type { KindStyle, Tone } from "web-shared";
import type { InventoryAlert, OrderIssue } from "./types";

export const ISSUE_KINDS: Record<OrderIssue["kind"], KindStyle> = {
  delayed: { label: "Delayed", icon: "clock", tone: "warn" },
  return_spike: { label: "Refund spike", icon: "return", tone: "danger" },
  buyer_message: { label: "Fan message", icon: "message", tone: "info" },
  damaged: { label: "Issue reported", icon: "alert", tone: "danger" },
};

export const INVENTORY_KINDS: Record<InventoryAlert["kind"], KindStyle> = {
  low_stock: { label: "Nearly sold out", icon: "low", tone: "warn" },
  slow_mover: { label: "Behind pace", icon: "chart", tone: "danger" },
};

// The shared order statuses are shipping terms; relabel them for tickets.
export const ORDER_STATUS: Record<string, { label: string; tone: Tone }> = {
  processing: { label: "Processing", tone: "muted" },
  shipped: { label: "Issued", tone: "info" },
  out_for_delivery: { label: "Issued", tone: "info" },
  delivered: { label: "Delivered", tone: "ok" },
  delayed: { label: "Delayed", tone: "warn" },
  cancelled: { label: "Cancelled", tone: "muted" },
  return_initiated: { label: "Return requested", tone: "violet" },
  refunded: { label: "Refunded", tone: "ok" },
};
