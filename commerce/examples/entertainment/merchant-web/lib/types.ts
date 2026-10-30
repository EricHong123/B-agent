// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** Mirrors merchant_agent/types.py and tools/presentation.py; overview shapes are the vertical's api/. */

// --- Listings (the box office's view of the tier catalog) ---

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
  /** Fan-authored; render as quoted third-party content. */
  review_snippets?: string[];
  sales_last_30d?: number | null;
  return_rate_pct?: number | null;
  missing_attributes?: string[];
  variants?: Listing[];
}

/** Only promoter and production holds are releasable. */
export interface HoldBuckets {
  promoter_hold?: number;
  production_hold?: number;
  comps?: number;
  kills?: number;
}

export interface ActivePromotion {
  name?: string | null;
  starts?: string | null;
  ends?: string | null;
  change_id?: string | null;
}

/** Mirrors mock_merchant.TierPricingContext. */
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
  price_unit?: string | null;
  event_id?: string | null;
  event_date?: string | null;
  days_to_event?: number | null;
  capacity?: number | null;
  sold?: number | null;
  remaining?: number | null;
  sell_through_pct?: number | null;
  baseline_pct?: number | null;
  pace_vs_baseline_pts?: number | null;
  waitlist_depth?: number | null;
  holds?: HoldBuckets;
  /** Pass-through fees; the floor under any price move. */
  fees_usd?: number | null;
  active_promotions?: ActivePromotion[];
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

// --- Inventory and order health ---

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
  /** Fan-authored; render as quoted third-party content. */
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

/** Counts are summed across tiers. */
export interface UpcomingShow {
  event_id: string;
  event_name: string;
  venue?: string | null;
  event_date: string;
  days_to_event: number;
  sold: number;
  capacity: number;
  remaining: number;
  waitlist_depth: number;
}

export interface TodaySnapshot {
  upcoming: UpcomingShow[];
}

export interface OverviewResponse {
  snapshot: BusinessSnapshot;
  needs_attention: {
    inventory: InventoryAlert[];
    order_issues: OrderIssue[];
    pending_changes: StagedChange[];
  };
  recent_orders: RecentOrder[];
  /** Applied or discarded, newest first. */
  recent_changes: StagedChange[];
  today?: TodaySnapshot | null;
}

export interface StagedWindow {
  change_id: string;
  name?: string | null;
  starts?: string | null;
  ends?: string | null;
  listing_ids: string[];
}

export interface WeeklySoldPoint {
  week_start: string;
  sold_cum: number;
}

export interface PacingTier {
  product_id: string;
  tier?: string | null;
  price?: number | null;
  currency?: string | null;
  capacity?: number | null;
  sold?: number | null;
  remaining?: number | null;
  sell_through_pct?: number | null;
  baseline_pct?: number | null;
  pace_vs_baseline_pts?: number | null;
  waitlist_depth?: number | null;
  holds?: HoldBuckets;
  weekly_sold_cum?: WeeklySoldPoint[];
  /** Index-aligned with weekly_sold_cum. */
  weekly_baseline_pct?: number[] | null;
  /** Joins VenueSection.tier_code. */
  tier_code?: string | null;
  /** Mean tickets/week over the last four weeks. */
  recent_weekly_sales?: number | null;
}

export interface PacingEvent {
  event_id: string;
  event_name?: string | null;
  venue?: string | null;
  city?: string | null;
  event_date?: string | null;
  on_sale_date?: string | null;
  days_to_event?: number | null;
  baseline_kind?: string | null;
  venue_id?: string | null;
  tiers: PacingTier[];
  /** event_pacing payload only. */
  note?: string | null;
}

/** Geometry is served only by /api/merchant/pacing. */
export interface VenueSection {
  section_id: string;
  label: string;
  short_label?: string | null;
  /** null for the stage. */
  tier_code: string | null;
  kind: string;
  x: number;
  y: number;
  w: number;
  h: number;
}

export interface VenueRecord {
  venue_id: string;
  name: string;
  city?: string | null;
  viewbox: { width: number; height: number };
  sections: VenueSection[];
}

export interface PacingOverviewResponse {
  events: PacingEvent[];
  staged_windows: StagedWindow[];
  venues?: Record<string, VenueRecord>;
}

export interface ListingDetailResponse {
  listing: ListingDetails;
  pricing: PricingContext | null;
}

// --- Presentation payloads ---

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

// --- Event pacing (the entertainment PresentationExtension) ---

/** Same rows as /api/merchant/pacing. */
export interface EventPacingPayload {
  grain?: string | null;
  events?: PacingEvent[];
  title?: string | null;
}
