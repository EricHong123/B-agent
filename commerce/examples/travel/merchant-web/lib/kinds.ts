// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** How each kind of supplier record shows: its label, icon, and tone. */

import type { KindStyle, Tone, Translate } from "web-shared";
import type { InventoryAlert, ListingStatus, OrderIssue } from "./types";

export const ISSUE_KINDS: Record<OrderIssue["kind"], KindStyle> = {
  delayed: { label: "Delayed", icon: "clock", tone: "warn" },
  return_spike: { label: "Cancellations", icon: "return", tone: "danger" },
  buyer_message: { label: "Guest message", icon: "message", tone: "info" },
  damaged: { label: "Issue reported", icon: "alert", tone: "danger" },
};

export const INVENTORY_KINDS: Record<InventoryAlert["kind"], KindStyle> = {
  low_stock: { label: "Tight availability", icon: "bed", tone: "warn" },
  slow_mover: { label: "Soft pacing", icon: "low", tone: "muted" },
};

export const LISTING_STATUS: Record<ListingStatus, { label: string; tone: Tone }> = {
  active: { label: "Active", tone: "ok" },
  paused: { label: "Paused", tone: "muted" },
  draft: { label: "Draft", tone: "info" },
  out_of_stock: { label: "Sold out", tone: "danger" },
};

// The shared order pipeline's parcel statuses, translated into booking language.
export const BOOKING_STATUS: Record<string, { label: string; tone: Tone }> = {
  processing: { label: "Processing", tone: "muted" },
  shipped: { label: "Confirmed", tone: "info" },
  out_for_delivery: { label: "Confirmed", tone: "info" },
  delivered: { label: "Completed", tone: "ok" },
  delayed: { label: "Delayed", tone: "warn" },
  cancelled: { label: "Cancelled", tone: "muted" },
  return_initiated: { label: "Refund requested", tone: "violet" },
  refunded: { label: "Refunded", tone: "ok" },
};

/** The composer prompt for an availability or pacing alert; the same words on every surface. */
export function inventoryPrompt(kind: InventoryAlert["kind"], ref: string, t: Translate): string {
  return kind === "low_stock"
    ? t("What are my options for {ref}? It is running tight on availability.", { ref })
    : t("Plan rates for {ref}, which is pacing soft.", { ref });
}
