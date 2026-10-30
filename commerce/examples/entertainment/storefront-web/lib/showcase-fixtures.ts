// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** Records are copied from data/catalog.json and data/inventory.json. */

import type {
  CheckoutPayload,
  ComparisonPayload,
  DisclosurePayload,
  GuidePayload,
  HoldPayload,
  OrderStatusPayload,
  PlanPayload,
  Product,
  ProductsPayload,
  ReturnOffer,
  VenueMapPayload,
  WalletTicket,
} from "./types";

// --- Box-office tiers: The Headliner at ACME Amphitheater, Fri Aug 14 ------------

const HEADLINER_PIT: Product = {
  product_id: "AT-TIX-101-PIT",
  title: "The Headliner — Summer Tour · Fri Aug 14 · GA Pit",
  brand: "The Headliner",
  price: 112.0,
  currency: "USD",
  category: "tickets",
  labels: ["Selling fast, 6 left"],
  attributes: {
    event_name: "The Headliner — Summer Tour",
    venue: "ACME Amphitheater",
    city: "Springfield",
    event_date: "2026-08-14",
    event_time: "19:30",
    tier: "GA Pit",
    admission: "general",
    face_price_usd: "89.00",
    service_fee_usd: "14.50",
    facility_fee_usd: "6.00",
    processing_fee_usd: "2.50",
    tickets_remaining: "6",
  },
  in_stock: true,
};

const HEADLINER_LOWER: Product = {
  product_id: "AT-TIX-101-LOW",
  title: "The Headliner — Summer Tour · Fri Aug 14 · Lower Bowl",
  brand: "The Headliner",
  price: 89.0,
  currency: "USD",
  category: "tickets",
  attributes: {
    event_name: "The Headliner — Summer Tour",
    venue: "ACME Amphitheater",
    city: "Springfield",
    event_date: "2026-08-14",
    event_time: "19:30",
    tier: "Lower Bowl",
    admission: "reserved",
    face_price_usd: "69.00",
    service_fee_usd: "11.50",
    facility_fee_usd: "6.00",
    processing_fee_usd: "2.50",
    tickets_remaining: "385",
  },
  in_stock: true,
};

const HEADLINER_TERRACE: Product = {
  product_id: "AT-TIX-101-TER",
  title: "The Headliner — Summer Tour · Fri Aug 14 · Upper Terrace",
  brand: "The Headliner",
  price: 54.5,
  currency: "USD",
  category: "tickets",
  attributes: {
    event_name: "The Headliner — Summer Tour",
    venue: "ACME Amphitheater",
    city: "Springfield",
    event_date: "2026-08-14",
    event_time: "19:30",
    tier: "Upper Terrace",
    admission: "reserved",
    face_price_usd: "39.00",
    service_fee_usd: "7.00",
    facility_fee_usd: "6.00",
    processing_fee_usd: "2.50",
    tickets_remaining: "552",
  },
  in_stock: true,
};

// --- Fan-resale listings ---------------------------------------------------------

const RESALE_SYNTH_PIT: Product = {
  product_id: "AT-RSL-201",
  title: "Resale · The Synth-Pop Act — Fall Tour · Fri Aug 28 · GA Pit (pair)",
  brand: "The Synth-Pop Act",
  price: 165.0,
  currency: "USD",
  category: "resale",
  labels: ["Selling fast, 2 left"],
  attributes: {
    event_name: "The Synth-Pop Act — Fall Tour",
    venue: "ACME Amphitheater",
    city: "Springfield",
    event_date: "2026-08-28",
    event_time: "20:00",
    tier: "GA Pit",
    admission: "general",
    sold_together: "2",
    seller_price_usd: "142.00",
    service_fee_usd: "14.50",
    facility_fee_usd: "6.00",
    processing_fee_usd: "2.50",
    tickets_remaining: "2",
    value_score: "4",
    value_verdict: "red",
    vs_box_office: "+34%",
    box_office_all_in_usd: "123.50",
  },
  in_stock: true,
};

const RESALE_SYNTH_TERRACE: Product = {
  product_id: "AT-RSL-202",
  title: "Resale · The Synth-Pop Act — Fall Tour · Fri Aug 28 · Upper Terrace (pair)",
  brand: "The Synth-Pop Act",
  price: 72.0,
  currency: "USD",
  category: "resale",
  labels: ["Selling fast, 2 left"],
  attributes: {
    event_name: "The Synth-Pop Act — Fall Tour",
    venue: "ACME Amphitheater",
    city: "Springfield",
    event_date: "2026-08-28",
    event_time: "20:00",
    tier: "Upper Terrace",
    admission: "reserved",
    sold_together: "2",
    seller_price_usd: "58.00",
    service_fee_usd: "5.50",
    facility_fee_usd: "6.00",
    processing_fee_usd: "2.50",
    tickets_remaining: "2",
    value_score: "7",
    value_verdict: "amber",
    vs_box_office: "+9%",
    box_office_all_in_usd: "66.00",
  },
  in_stock: true,
};

const RESALE_HEADLINER_LOWER: Product = {
  product_id: "AT-RSL-203",
  title: "Resale · The Headliner — Summer · Fri Aug 14 · Lower Bowl (pair)",
  brand: "The Headliner",
  price: 64.0,
  currency: "USD",
  category: "resale",
  labels: ["Selling fast, 2 left"],
  attributes: {
    event_name: "The Headliner — Summer Tour",
    venue: "ACME Amphitheater",
    city: "Springfield",
    event_date: "2026-08-14",
    event_time: "19:30",
    tier: "Lower Bowl",
    admission: "reserved",
    sold_together: "2",
    seller_price_usd: "50.50",
    service_fee_usd: "5.00",
    facility_fee_usd: "6.00",
    processing_fee_usd: "2.50",
    tickets_remaining: "2",
    value_score: "10",
    value_verdict: "green",
    vs_box_office: "-28%",
    box_office_all_in_usd: "89.00",
  },
  in_stock: true,
};

// --- Payloads ------------------------------------------------------------------

const products: ProductsPayload = {
  title: "The Headliner at ACME Amphitheater — Friday, every way in",
  items: [
    {
      product: HEADLINER_PIT,
      reason: "Standing rail spot — 6 pit tickets left for Friday, per live inventory.",
    },
    {
      product: HEADLINER_LOWER,
      reason: "Reserved covered seats facing the stage dead-on.",
    },
    {
      product: HEADLINER_TERRACE,
      reason: "Open-air rows with the harbor sunset behind the stage.",
    },
    { product: RESALE_HEADLINER_LOWER },
  ],
};

const resale: ProductsPayload = {
  title: "The Synth-Pop Act is sold out — your real options",
  items: [
    { product: RESALE_SYNTH_TERRACE },
    { product: RESALE_SYNTH_PIT },
    { product: RESALE_HEADLINER_LOWER },
  ],
};

const comparison: ComparisonPayload = {
  title: "Friday at ACME Amphitheater — GA Pit vs Lower Bowl vs Upper Terrace",
  entries: [
    {
      product_id: "AT-TIX-101-PIT",
      product: HEADLINER_PIT,
      best_for: "Being at the rail",
      pros: ["Standing room at the stage rail", "Own entrance, wristbanded re-entry"],
      cons: ["On your feet all night", "Only 6 tickets left"],
    },
    {
      product_id: "AT-TIX-101-LOW",
      product: HEADLINER_LOWER,
      best_for: "Best view per dollar",
      pros: ["Reserved seats, covered rows", "Faces the stage dead-on"],
      cons: ["$34.50 more than terrace"],
    },
    {
      product_id: "AT-TIX-101-TER",
      product: HEADLINER_TERRACE,
      best_for: "The sunset postcard",
      pros: ["Harbor sunset behind the stage", "Cheapest way in — $54.50 all-in"],
      cons: ["Open air, furthest back"],
    },
  ],
  dimensions: ["View", "Seating", "All-in price", "Availability"],
  recommended_product_id: "AT-TIX-101-LOW",
};

const plan: PlanPayload = {
  title: "Your Summer Tour Friday",
  intro: "Three beats for the ACME Amphitheater closing weekend, all prices all-in.",
  steps: [
    {
      label: "Lock the seats",
      detail: "Lower Bowl faces the stage straight-on; a hold keeps them 8 minutes while you decide.",
      products: [HEADLINER_LOWER],
    },
    {
      label: "Or chase the rail",
      detail: "The pit is down to its last 6 — a live count, not urgency copy.",
      products: [HEADLINER_PIT],
    },
    {
      label: "The fallback pair",
      detail: "A fan-listed Lower Bowl pair below box office, sold together.",
      products: [RESALE_HEADLINER_LOWER],
    },
  ],
};

const guide: GuidePayload = {
  title: "How holds and the waitlist work",
  sections: [
    {
      heading: "Ticket holds and the hold timer",
      body: "Adding tickets to your order places a hold: the seats are reserved for you for 8 minutes while you review the fee breakdown and check out. When the timer runs out the hold expires automatically and the tickets return to open sale — nothing is charged, ever, until you complete purchase on the payment page.",
    },
    {
      heading: "Waitlist and return offers",
      body: "When a tier is sold out you can join its waitlist. When a fan returns tickets, the returned quantity is offered to the front of the line as a return offer with a 10-minute claim window. Claiming a return offer places a normal 8-minute hold — you still review the price and fee breakdown before anything is charged.",
    },
  ],
  sources: ["ticket-holds", "waitlist-return-offers"],
};

/** As get_disclosure emits it. */
const disclosure: DisclosurePayload = {
  title: "The Headliner — Summer Tour · Fri Aug 14 · Lower Bowl: price and terms",
  product_id: "AT-TIX-101-LOW",
  rows: [
    {
      label: "All-in price",
      value: "$89.00",
      note: "per ticket; what you actually pay, no fees added later",
    },
    { label: "Face value", value: "$69.00" },
    { label: "Service fee", value: "$11.50" },
    { label: "Facility fee", value: "$6.00" },
    { label: "Order processing", value: "$2.50", note: "per ticket in this demo catalog" },
    {
      label: "Hold policy",
      value: "8-minute hold, then tickets return to sale",
      note: "nothing is charged until you complete purchase",
    },
    { label: "Delivery", value: "mobile ticket, rotating barcode" },
  ],
  sources: ["all-in-pricing", "ticket-holds", "mobile-entry", "refunds-event-changes"],
  footnotes: [
    "All prices are all-in: face value plus every fee, itemized above.",
    "Availability counts are live inventory numbers, never marketing copy.",
  ],
};

const disclosure_resale: DisclosurePayload = {
  title: "Resale · The Synth-Pop Act — Fall Tour · Fri Aug 28 · GA Pit (pair): price and terms",
  product_id: "AT-RSL-201",
  rows: [
    {
      label: "All-in price",
      value: "$165.00",
      note: "per ticket; what you actually pay, no fees added later",
    },
    {
      label: "Seller price",
      value: "$142.00",
      note: "the fan seller's asking price for this listing",
    },
    { label: "Service fee", value: "$14.50" },
    { label: "Facility fee", value: "$6.00" },
    { label: "Order processing", value: "$2.50", note: "per ticket in this demo catalog" },
    {
      label: "Box-office all-in price",
      value: "$123.50",
      note: "same tier, sold by the venue — currently sold out",
    },
    {
      label: "Value score",
      value: "4/10 (red)",
      note: "listing is +34% vs the box-office all-in price",
    },
    {
      label: "Hold policy",
      value: "8-minute hold, then tickets return to sale",
      note: "nothing is charged until you complete purchase",
    },
    { label: "Delivery", value: "mobile ticket, rotating barcode" },
  ],
  sources: ["all-in-pricing", "ticket-holds", "resale-value-scores", "refunds-event-changes"],
  footnotes: [
    "All prices are all-in: face value plus every fee, itemized above.",
    "Availability counts are live inventory numbers, never marketing copy.",
  ],
};

const checkout: CheckoutPayload = {
  note: "Two Lower Bowl seats for Friday, held while you decide.",
  fulfillment_method: "delivery",
  cart: {
    items: [
      {
        product_id: "AT-TIX-101-LOW",
        title: "The Headliner — Summer Tour · Fri Aug 14 · Lower Bowl",
        price: 89.0,
        quantity: 2,
        line_total: 178.0,
      },
    ],
    item_count: 2,
    subtotal: 178.0,
    currency: "USD",
  },
};

const hold: HoldPayload = {
  note: "Holding the pair while you compare — the timer is the real server expiry.",
  cart: checkout.cart,
  hold: { seconds_remaining: 412, hold_minutes: 8 },
};

const order_status: OrderStatusPayload = {
  order_id: "AT-ORD-9002",
  summary:
    "Two Lower Bowl tickets for The Headliner on Friday Aug 14 — delivered to your ACME Tickets wallet on July 1.",
  next_step: "Your mobile tickets are in the wallet; the barcode rotates on its own.",
  order: {
    order_id: "AT-ORD-9002",
    status: "delivered",
    placed_at: "2026-07-01T09:15:00Z",
    items: [
      {
        product_id: "AT-TIX-101-LOW",
        title: "The Headliner — Summer Tour · Fri Aug 14 · Lower Bowl",
        quantity: 2,
        price: 89.0,
      },
    ],
    total: 178.0,
    currency: "USD",
    estimated_delivery: "delivered to your ACME Tickets wallet",
  },
};

/** Sections from data/venues.json; tier state from data/inventory.json. */
const venue_map: VenueMapPayload = {
  title: "ACME Amphitheater — the room for Friday",
  event: {
    event_id: "AT-EVT-101",
    name: "The Headliner — Summer Tour",
    date: "2026-08-14",
    time: "19:30",
  },
  venue: {
    venue_id: "AT-VEN-01",
    name: "ACME Amphitheater",
    city: "Springfield",
    viewbox: { width: 100, height: 62 },
  },
  sections: [
    { section_id: "STAGE", label: "Stage", kind: "stage", x: 30, y: 2, w: 40, h: 8 },
    {
      section_id: "PIT",
      label: "GA Pit",
      kind: "floor",
      x: 32,
      y: 12,
      w: 36,
      h: 10,
      product_id: "AT-TIX-101-PIT",
      tier: "GA Pit",
      price_all_in: 112.0,
      currency: "USD",
      remaining: 6,
      status: "on_sale",
      highlighted: false,
    },
    {
      section_id: "LOWER-L",
      label: "Lower Bowl 101–103",
      short_label: "101–103",
      kind: "bowl",
      x: 8,
      y: 14,
      w: 20,
      h: 16,
      product_id: "AT-TIX-101-LOW",
      tier: "Lower Bowl",
      price_all_in: 89.0,
      currency: "USD",
      remaining: 385,
      status: "on_sale",
      highlighted: false,
    },
    {
      section_id: "LOWER-C",
      label: "Lower Bowl 104–105",
      kind: "bowl",
      x: 30,
      y: 26,
      w: 40,
      h: 10,
      product_id: "AT-TIX-101-LOW",
      tier: "Lower Bowl",
      price_all_in: 89.0,
      currency: "USD",
      remaining: 385,
      status: "on_sale",
      highlighted: false,
    },
    {
      section_id: "LOWER-R",
      label: "Lower Bowl 106–108",
      short_label: "106–108",
      kind: "bowl",
      x: 72,
      y: 14,
      w: 20,
      h: 16,
      product_id: "AT-TIX-101-LOW",
      tier: "Lower Bowl",
      price_all_in: 89.0,
      currency: "USD",
      remaining: 385,
      status: "on_sale",
      highlighted: false,
    },
    {
      section_id: "TERRACE",
      label: "Upper Terrace",
      kind: "terrace",
      x: 10,
      y: 40,
      w: 80,
      h: 16,
      product_id: "AT-TIX-101-TER",
      tier: "Upper Terrace",
      price_all_in: 54.5,
      currency: "USD",
      remaining: 552,
      status: "on_sale",
      highlighted: false,
    },
  ],
  recommended_product_id: "AT-TIX-101-LOW",
};

export const SHOWCASE = {
  venue_map,
  products,
  resale,
  comparison,
  plan,
  guide,
  disclosure,
  disclosure_resale,
  checkout,
  hold,
  order_status,
};

// --- Panel, wallet, and banner fixtures (data/tickets.json records in the /api response shapes) --

/** As /api/tickets serves it. */
export const SHOWCASE_WALLET_ACTIVE: WalletTicket = {
  ticket_id: "AT-TKT-7003",
  event: "The Headliner — Summer Tour",
  date: "2026-08-14",
  venue: "ACME Amphitheater",
  tier: "Lower Bowl",
  seat: "Section 104, Row J, Seat 12",
  status: "active",
  entry_code: "B75BF84509",
  entry_code_rotates_s: 60,
  transfer_recipient: null,
};

export const SHOWCASE_WALLET_PENDING: WalletTicket = {
  ...SHOWCASE_WALLET_ACTIVE,
  ticket_id: "AT-TKT-7004",
  seat: "Section 104, Row J, Seat 13",
  status: "transfer_pending",
  transfer_recipient: "Sam",
};

export const SHOWCASE_TONIGHT = {
  product: HEADLINER_LOWER,
  quantity: 2,
  total: 178.0,
  seconds_remaining: 412,
};

/** As /api/waitlist serves it. */
export const SHOWCASE_OFFER: ReturnOffer & { product: Product } = {
  offer_id: "offer-0001",
  product_id: "AT-TIX-101-LOW",
  quantity: 2,
  expires_at: "2026-08-14T18:00:00Z",
  seconds_remaining: 540,
  product: HEADLINER_LOWER,
};
