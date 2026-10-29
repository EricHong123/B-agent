// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** Mirrors merchant_agent/types.py and tools/presentation.py; overview shapes are the vertical's api/. */

// --- Listings (the supplier's view of the property catalog) ---

export type ListingStatus = "active" | "paused" | "draft" | "out_of_stock";
export type ContentQuality = "good" | "needs_work" | "poor";

export interface Listing {
  listing_id: string;
  title: string;
  status: ListingStatus;
  price: number;
  currency?: string;
  stock: number;
  category?: string | null;
  content_quality?: ContentQuality | null;
  attributes?: Record<string, string>;
  image_url?: string | null;
  short_description?: string | null;
  /** Options a family listing is sold by; price and stock then live on its variants. */
  options?: Record<string, string[]>;
  /** A variant's value for each option, and its family's id. */
  option_values?: Record<string, string>;
  variant_of?: string | null;
}

export interface ListingDetails extends Listing {
  long_description?: string | null;
  /** Guest-authored; render as quoted third-party text. */
  review_snippets?: string[];
  sales_last_30d?: number | null;
  return_rate_pct?: number | null;
  missing_attributes?: string[];
  variants?: Listing[];
}

export interface PricingContext {
  listing_id: string;
  current_price: number;
  currency?: string;
  unit_cost?: number | null;
  margin_pct?: number | null;
  min_price?: number | null;
  max_price?: number | null;
  min_price_basis?: "cost" | "policy" | null;
  demand_signal?: "rising" | "steady" | "falling" | null;
  last_changed?: string | null;
  option_values?: Record<string, string>;
  /** One context per variant when the listing is a family. */
  variants?: PricingContext[];
}

// --- Business metrics ---

export interface AlertCounts {
  low_stock?: number;
  slow_movers?: number;
  order_issues?: number;
  pending_changes?: number;
}

export interface BusinessSnapshot {
  period: string;
  compare_to?: string | null;
  sales: number;
  orders: number;
  traffic?: number | null;
  conversion_rate?: number | null;
  average_order_value?: number | null;
  sales_change_pct?: number | null;
  orders_change_pct?: number | null;
  traffic_change_pct?: number | null;
  conversion_change_pct?: number | null;
  currency?: string;
  alerts?: AlertCounts;
  note?: string | null;
}

export interface MetricPoint {
  date: string;
  value: number;
}

export interface MetricSeries {
  metric: string;
  unit?: string | null;
  granularity?: "day" | "week" | "month";
  period?: string | null;
  segment?: string | null;
  points: MetricPoint[];
  note?: string | null;
}

// --- Inventory and booking health ---

export interface InventoryAlert {
  listing_id: string;
  title: string;
  kind: "low_stock" | "slow_mover";
  /** Set when the alert is for one variant: its option values and its family's id. */
  option_values?: Record<string, string>;
  variant_of?: string | null;
  stock: number;
  threshold?: number | null;
  days_of_cover?: number | null;
  sales_last_30d?: number | null;
}

export interface OrderIssue {
  issue_id: string;
  order_id: string;
  kind: "delayed" | "return_spike" | "buyer_message" | "damaged";
  summary: string;
  listing_id?: string | null;
  /** Guest-authored; render as quoted third-party text. */
  buyer_message_excerpt?: string | null;
  opened_at?: string | null;
}

// --- Staged changes (propose → preview → approve → apply) ---

export type ChangeKind =
  | "listing_update"
  | "price_update"
  | "inventory_action"
  | "promotion"
  | "campaign";

export type ChangeStatus = "staged" | "applied" | "discarded" | "expired";

export interface ChangeItem {
  target: string;
  field: string;
  before?: unknown;
  after?: unknown;
}

export interface StagedChange {
  change_id: string;
  kind: ChangeKind;
  status: ChangeStatus;
  summary: string;
  items: ChangeItem[];
  created_at: string;
  created_by: string;
  created_by_kind?: "operator" | "agent";
  applied_at?: string | null;
  applied_by?: string | null;
  discarded_at?: string | null;
  discarded_by?: string | null;
  discarded_by_kind?: "operator" | "agent" | null;
  expired_at?: string | null;
  guardrail_notes?: string[];
  currency?: string | null;
  margin_impact?: number | null;
  /** Set only for single-listing rate moves. */
  margin_before_pct?: number | null;
  margin_after_pct?: number | null;
}

// --- Portal data-plane responses ---

export interface RecentOrder {
  order_id: string;
  status: string;
  placed_at: string;
  total: number;
  items: number;
}

export interface TodayMovement {
  count: number;
  properties: string[];
}

export interface TodaySnapshot {
  arrivals: TodayMovement;
  departures: TodayMovement;
  new_bookings: TodayMovement;
}

export interface OverviewResponse {
  snapshot: BusinessSnapshot;
  needs_attention: {
    inventory: InventoryAlert[];
    order_issues: OrderIssue[];
    pending_changes: StagedChange[];
  };
  recent_orders: RecentOrder[];
  /** Newest first. */
  recent_changes: StagedChange[];
  today?: TodaySnapshot | null;
}

export interface StagedWindow {
  change_id: string;
  name?: string | null;
  starts?: string | null;
  ends?: string | null;
  nights?: string[] | null;
  listing_ids: string[];
}

export interface OccupancyOverviewResponse {
  window: { from: string; to: string };
  properties: OccupancyListing[];
  staged_windows: StagedWindow[];
}

export interface ListingsResponse {
  /** Count before paging. */
  total?: number;
  listings: Listing[];
}

export interface ListingDetailResponse {
  listing: ListingDetails;
  pricing: PricingContext | null;
}

export interface AlertsResponse {
  inventory: InventoryAlert[];
  order_issues: OrderIssue[];
}

// --- Presentation payloads (enriched server-side before the `ui` event is emitted) ---

export interface MetricEntry {
  metric: string;
  value?: number | null;
  change_pct?: number | null;
  currency?: string | null;
  note?: string | null;
  series?: MetricSeries | null;
}

export interface MetricsPayload {
  title?: string | null;
  period?: string | null;
  metrics: MetricEntry[];
}

export interface DigestEntry {
  kind: "low_stock" | "slow_mover" | "order_issue" | "metric" | "pending_change" | "note";
  ref_id?: string | null;
  headline: string;
  why_it_matters?: string | null;
  listing?: Listing | null;
  change?: StagedChange | null;
}

export interface DigestPayload {
  title?: string | null;
  items: DigestEntry[];
}

export interface ChangePreviewPayload {
  change_id: string;
  headline?: string | null;
  note?: string | null;
  change: StagedChange;
}

// --- Occupancy calendar (the travel PresentationExtension) ---
// The payload examples/travel/api/occupancy.py builds; every field is optional on the client.

export interface OccupancyOverride {
  starts?: string | null;
  ends?: string | null;
  nightly_rate?: number | null;
  change_id?: string | null;
}

export interface OccupancyWeek {
  week_start?: string | null;
  /** The override rate when one applies. */
  nightly_rate?: number | null;
  /** 0–100; values ≤ 1 are fractions. */
  occupancy_pct?: number | null;
  midweek_occupancy_pct?: number | null;
  weekend_occupancy_pct?: number | null;
  /** Signed percent vs the comparable period. */
  on_the_books_pace_pct?: number | null;
  override?: OccupancyOverride | null;
}

export interface OccupancyListing {
  listing_id?: string | null;
  title?: string | null;
  rooms?: number | null;
  base_nightly_rate?: number | null;
  currency?: string | null;
  /** Model-supplied. */
  note?: string | null;
  weeks?: OccupancyWeek[];
}

export interface OccupancyCalendarPayload {
  start?: string | null;
  end?: string | null;
  grain?: string | null;
  listings?: OccupancyListing[];
  title?: string | null;
  period?: string | null;
}
