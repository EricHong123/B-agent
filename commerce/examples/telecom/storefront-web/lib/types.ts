// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** Mirrors shopping_agent/types.py and tools/presentation.py; detail extras are the vertical's api/. */

import type { TermsEvidence } from "web-shared";

export interface Product {
  product_id: string;
  title: string;
  brand?: string | null;
  price: number;
  currency?: string;
  rating?: number | null;
  review_count?: number | null;
  image_url?: string | null;
  category?: string | null;
  labels?: string[];
  attributes?: Record<string, string>;
  in_stock?: boolean;
  short_description?: string | null;
  /** Options still to choose on a family record; the cart takes one of its variants. */
  options?: Record<string, string[]>;
  /** A variant's value for each option. */
  option_values?: Record<string, string>;
  variant_of?: string | null;
}

export interface CartItem {
  product_id: string;
  title: string;
  price: number;
  quantity: number;
  image_url?: string | null;
  option_values?: Record<string, string>;
  variant_of?: string | null;
  line_total: number;
}

export interface CartPayload {
  items: CartItem[];
  item_count: number;
  subtotal: number;
  currency: string;
}

// --- Presentation payloads, as streamed after server enrichment ---

export interface ProductsPayload {
  title?: string;
  layout?: "carousel" | "grid" | "list";
  items: { product: Product; reason?: string | null }[];
}

export interface ComparisonPayload {
  title?: string;
  entries: {
    product_id: string;
    product: Product;
    pros?: string[];
    cons?: string[];
    best_for?: string | null;
  }[];
  dimensions?: string[];
  recommended_product_id?: string | null;
  // Stamped by the server: the spread between the cheapest and dearest compared items.
  price_delta?: {
    amount: number;
    low_product_id: string;
    low_price: number;
    high_product_id: string;
    high_price: number;
  };
}

export interface PlanPayload {
  title: string;
  intro?: string;
  steps: { label: string; detail?: string | null; products: Product[] }[];
}

export interface GuidePayload {
  title: string;
  sections: { heading: string; body: string }[];
  related_products?: Product[];
  sources?: string[];
  evidence?: TermsEvidence[];
}

export interface OrderStatusPayload {
  order_id: string;
  summary: string;
  next_step?: string;
  order?: {
    order_id: string;
    status: string;
    placed_at: string;
    items: { product_id: string; title: string; quantity: number; price: number }[];
    total: number;
    currency?: string;
    estimated_delivery?: string;
    tracking_url?: string;
  };
}

export interface CheckoutHandoff {
  url: string;
  label?: string;
  seller?: string;
}

export interface CheckoutPayload {
  /** Where payment happens when it is not a route in this app; filled by the backend. */
  handoffs?: CheckoutHandoff[];
  note?: string;
  fulfillment_method?: "delivery" | "pickup" | "shipping";
  cart: CartPayload;
}

/** Built by api/plan_matrix.py; cells are server-side, the model supplies ids and keys. */
export interface PlanMatrixPayload {
  title?: string;
  plans: Product[];
  rows: { key: string; label: string; values: string[] }[];
  annotations: { plan_id: string; best_for?: string }[];
  recommended_plan_id?: string;
  /** Absent for prospects. */
  current_plan?: {
    product_id?: string;
    name?: string;
    price_per_month?: number | null;
    data_allowance_gb?: string | null;
  };
  /** Absent for prospects. */
  account_usage?: AccountUsage;
}

export interface AccountUsage {
  avg_gb_per_month_last_3: number;
  cycles_gb_last_3?: number[];
  top_ups_last_3_months: number;
  top_up_spend_usd_last_3_months?: number;
  note?: string;
}

/** `GET /api/account`. */
export interface AccountContext {
  current_plan: {
    product_id: string;
    name: string;
    price_per_month: number | null;
    data_allowance_gb?: string | null;
  };
  contract: {
    started: string;
    month: number;
    of_months: number;
    ends: string;
    early_upgrade_on?: string;
  };
  device: {
    product_id: string;
    name: string;
    installments_remaining: number;
    installment_usd?: number;
  };
  upgrade_eligibility: { eligible: boolean; kind: string; reason: string };
  trade_in_estimate: {
    device: string;
    tier: string;
    estimated_credit_usd: number;
    condition_assumption: string;
    quote_valid_through: string;
    note?: string;
  } | null;
  monthly_bill_usd: number;
  recent_usage: AccountUsage;
}

/** Rows come from `StorefrontBackend.get_disclosure`. */
export interface DisclosurePayload {
  title: string;
  product_id: string;
  rows: { label: string; value: string; note?: string }[];
  sources?: string[];
  footnotes?: string[];
  evidence?: TermsEvidence[];
}
