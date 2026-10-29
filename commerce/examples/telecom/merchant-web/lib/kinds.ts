// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** How each kind of telecom record shows: its label, icon, and tone. */

import type { KindStyle, Tone } from "web-shared";
import type { InventoryAlert, ListingStatus, OrderIssue } from "./types";

export const ISSUE_KINDS: Record<OrderIssue["kind"], KindStyle> = {
  delayed: { label: "Delayed", icon: "truck", tone: "warn" },
  return_spike: { label: "Return spike", icon: "return", tone: "danger" },
  buyer_message: { label: "Customer message", icon: "message", tone: "info" },
  damaged: { label: "Issue reported", icon: "alert", tone: "danger" },
};

export const INVENTORY_KINDS: Record<InventoryAlert["kind"], KindStyle> = {
  low_stock: { label: "Low stock", icon: "low", tone: "warn" },
  slow_mover: { label: "Slow mover", icon: "clock", tone: "muted" },
};

export const LISTING_STATUS: Record<ListingStatus, { label: string; tone: Tone }> = {
  active: { label: "Active", tone: "ok" },
  paused: { label: "Paused", tone: "muted" },
  draft: { label: "Draft", tone: "info" },
  out_of_stock: { label: "Out of stock", tone: "danger" },
};

export const ORDER_STATUS: Record<string, { label: string; tone: Tone }> = {
  processing: { label: "Processing", tone: "muted" },
  shipped: { label: "Shipped", tone: "info" },
  out_for_delivery: { label: "Out for delivery", tone: "info" },
  delivered: { label: "Delivered", tone: "ok" },
  delayed: { label: "Delayed", tone: "warn" },
  cancelled: { label: "Cancelled", tone: "muted" },
  return_initiated: { label: "Return requested", tone: "violet" },
  refunded: { label: "Refunded", tone: "ok" },
};

/** Unknown categories sort last. */
export const CATEGORY_ORDER = ["plans", "home-internet", "devices", "add-ons"];

export const CATEGORY_LABELS: Record<string, string> = {
  plans: "Plans",
  "home-internet": "Home internet",
  devices: "Devices",
  "add-ons": "Add-ons",
};

/** The singular noun for one product in a category. */
export const CATEGORY_NOUNS: Record<string, string> = {
  plans: "plan",
  "home-internet": "plan",
  devices: "device",
  "add-ons": "add-on",
};

/** Stock counts active lines in these categories. */
export const LINE_CATEGORIES = new Set(["plans", "home-internet"]);
