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

// --- Ticketing state served by the vertical's own routes -------------------

/** The client converts seconds_remaining to a local deadline. */
export interface Hold {
  hold_id: string;
  product_id: string;
  quantity: number;
  expires_at: string;
  seconds_remaining: number;
}

export interface WaitlistEntry {
  product_id: string;
  quantity: number;
  position: number;
}

export interface ReturnOffer {
  offer_id: string;
  product_id: string;
  quantity: number;
  expires_at: string;
  seconds_remaining: number;
}

export interface WalletTicket {
  ticket_id: string;
  event: string | null;
  date: string | null;
  venue: string | null;
  tier: string | null;
  seat: string;
  status: string;
  entry_code: string;
  entry_code_rotates_s: number;
  /** Set only while a transfer is pending. */
  transfer_recipient?: string | null;
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

/** present_hold (api/hold_view.py); the card ticks against the /api/holds deadlines. */
export interface HoldPayload {
  note?: string;
  cart: CartPayload;
  hold: { seconds_remaining: number; hold_minutes: number };
}

/** present_disclosure; rows come from the backend's get_disclosure. */
export interface DisclosurePayload {
  title: string;
  product_id: string;
  rows: { label: string; value: string; note?: string }[];
  sources?: string[];
  footnotes?: string[];
  evidence?: TermsEvidence[];
}

/** present_venue_map (api/venue_map.py). */
export interface VenueMapSection {
  section_id: string;
  label: string;
  short_label?: string;
  kind: string;
  x: number;
  y: number;
  w: number;
  h: number;
  product_id?: string;
  tier?: string;
  price_all_in?: number;
  currency?: string;
  remaining?: number;
  status?: "on_sale" | "sold_out";
  highlighted?: boolean;
}

export interface VenueMapPayload {
  title?: string;
  event: { event_id: string; name?: string | null; date?: string | null; time?: string | null };
  venue: {
    venue_id: string;
    name: string;
    city: string;
    viewbox: { width: number; height: number };
  };
  sections: VenueMapSection[];
  recommended_product_id?: string;
}
