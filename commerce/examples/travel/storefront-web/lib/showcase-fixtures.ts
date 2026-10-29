// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** Products mirror data/catalog.json rows; api/tests/test_showcase_fixtures.py checks them. */

import type { Product } from "./types";

const GUESTHOUSE_ALFAMA: Product = {
  product_id: "AL-STAY-101",
  title: "ACME Guesthouses Alfama",
  brand: "ACME Guesthouses",
  price: 214.0,
  currency: "USD",
  rating: 4.8,
  review_count: 412,
  category: "stays",
  labels: ["Top rated", "Near old town"],
  attributes: {
    city: "Lisbon",
    neighborhood: "Alfama",
    room_type: "queen room",
    breakfast_included: "yes",
    refundable: "no",
    typical_rate_band: "225-285",
    price_unit: "per_night",
    date_flex:
      "2026-10-12:225|2026-10-13:215|2026-10-14:217|2026-10-15*:214|2026-10-16:251|2026-10-17:266|2026-10-18:240",
    units_left_for_dates: "2",
  },
  in_stock: true,
  short_description:
    "An eight-room townhouse folded into Alfama's stairstep lanes, with azulejo-lined hallways and breakfast under a lemon tree.",
};

const ROOFTOP_SUITES: Product = {
  product_id: "AL-STAY-104",
  title: "ACME Suites Graca Rooftop",
  brand: "ACME Suites",
  price: 268.0,
  currency: "USD",
  rating: 4.7,
  review_count: 356,
  category: "stays",
  labels: ["Free cancellation"],
  attributes: {
    city: "Lisbon",
    neighborhood: "Graca",
    room_type: "rooftop suite",
    breakfast_included: "yes",
    refundable: "yes",
    free_cancellation_until: "2026-10-13",
    typical_rate_band: "225-310",
    price_unit: "per_night",
    date_flex:
      "2026-10-12:287|2026-10-13:267|2026-10-14:279|2026-10-15*:268|2026-10-16:318|2026-10-17:341|2026-10-18:290",
    units_left_for_dates: "2",
  },
  in_stock: true,
  short_description:
    "Six rooftop suites in hilltop Graca, each with a private terrace looking over the whole amphitheater of Lisbon.",
};

const FADO_WALK: Product = {
  product_id: "AL-EXP-301",
  title: "Alfama at Dusk: Fado & Petiscos Evening Walk",
  brand: "ACME Tours",
  price: 86.0,
  currency: "USD",
  rating: 4.8,
  review_count: 927,
  category: "experiences",
  labels: ["Free cancellation", "Top rated"],
  attributes: {
    city: "Lisbon",
    neighborhood: "Alfama",
    duration_hours: "3",
    price_unit: "per_person",
    refundable: "yes",
    free_cancellation_until: "2026-10-15",
  },
  in_stock: true,
  short_description:
    "Wind through Alfama as the lamps come on, grazing on petiscos before ending at a live fado set in a family-run tavern.",
};

const TILE_WORKSHOP: Product = {
  product_id: "AL-EXP-302",
  title: "Hands-On Azulejo Tile-Painting Workshop",
  brand: "ACME Tours",
  price: 54.0,
  currency: "USD",
  rating: 4.7,
  review_count: 463,
  category: "experiences",
  labels: ["Small group"],
  attributes: {
    city: "Lisbon",
    neighborhood: "Baixa",
    duration_hours: "2",
    price_unit: "per_person",
    refundable: "no",
  },
  in_stock: true,
  short_description:
    "Paint your own azulejo tile in a working Baixa atelier, guided by a ceramicist — fired, glazed, and shipped to you.",
};

const SINTRA_TRIP: Product = {
  product_id: "AL-EXP-303",
  title: "Sintra Palaces & Wild Coast Day Trip",
  brand: "ACME Tours",
  price: 118.0,
  currency: "USD",
  rating: 4.6,
  review_count: 1388,
  category: "experiences",
  labels: ["Free cancellation"],
  attributes: {
    city: "Lisbon",
    neighborhood: "Sintra",
    duration_hours: "8",
    price_unit: "per_person",
    refundable: "yes",
    free_cancellation_until: "2026-10-15",
  },
  in_stock: true,
  short_description:
    "A full day among Sintra's storybook palaces and gardens, ending with cliffs and salt spray on the wild Atlantic coast.",
};

const FLIGHT_ECONOMY: Product = {
  product_id: "AL-FLT-201",
  title: "New York to Lisbon Nonstop — Economy",
  brand: "ACME Air Atlantic",
  price: 498.0,
  currency: "USD",
  rating: 4.3,
  review_count: 1856,
  category: "flights",
  labels: ["Nonstop"],
  attributes: {
    origin_city: "New York",
    destination_city: "Lisbon",
    cabin: "economy",
    departure_time_local: "18:40",
    duration: "6h 55m",
    refundable: "no",
    price_unit: "per_person",
  },
  in_stock: true,
  short_description:
    "ACME Air Atlantic's evening nonstop to Lisbon — leave after work, land with the whole morning ahead.",
};

const FLIGHT_PREMIUM: Product = {
  product_id: "AL-FLT-202",
  title: "New York to Lisbon Nonstop — Premium Economy",
  brand: "ACME Air Atlantic",
  price: 1120.0,
  currency: "USD",
  rating: 4.6,
  review_count: 642,
  category: "flights",
  labels: ["Nonstop", "Free cancellation"],
  attributes: {
    origin_city: "New York",
    destination_city: "Lisbon",
    cabin: "premium economy",
    departure_time_local: "18:40",
    duration: "6h 55m",
    refundable: "yes",
    free_cancellation_until: "2026-10-14",
    price_unit: "per_person",
  },
  in_stock: true,
  short_description:
    "The same overnight Lisbon nonstop with a wider seat, deeper recline, and a fully refundable fare.",
};

export const SHOWCASE = {
  itinerary: {
    title: "Your Lisbon long weekend",
    // Three nights, so the footer total matches the checkout fixture for the same trip.
    travel_dates: "Thu 15 Oct — Sun 18 Oct",
    days: [
      {
        label: "Day 1 — Arrive & settle into Alfama",
        note: "Check in, shake off the flight. Wander the stairstep lanes at golden hour, grab a vinho verde at a miradouro, find a local tasca for dinner.",
        products: [GUESTHOUSE_ALFAMA],
      },
      {
        label: "Day 2 — Old city on foot + azulejo workshop",
        note: "Morning: get lost in Alfama and Mouraria. Afternoon: tile-painting atelier in Baixa — small group, tiles fired and shipped home.",
        products: [TILE_WORKSHOP],
      },
      {
        label: "Day 3 — Sintra day trip",
        note: "Storybook palaces, lush gardens, and wild Atlantic cliffs. Back by early evening — a good night to splurge on a long dinner.",
        products: [SINTRA_TRIP],
      },
      {
        label: "Day 3 Evening — Fado in a family tavern",
        note: "As the sun drops: a guided evening walk through Alfama grazing on petiscos, ending at a live fado set.",
        products: [FADO_WALK],
      },
      {
        label: "Day 4 — Slow morning, head home",
        note: "Breakfast under the lemon tree, a last espresso on a miradouro, then check out. October light in Lisbon is golden — worth every minute before the taxi.",
        products: [],
      },
    ],
  },

  // Two stays on the same arrival day are alternatives, so the footer prices the pick.
  itinerary_alternatives: {
    title: "Lisbon, two ways to stay",
    travel_dates: "Thu 15 Oct — Sun 18 Oct",
    days: [
      {
        label: "Day 1 — Arrive, pick your base",
        note: "Two homes for the same three nights: the lemon-tree townhouse is an advance-saver rate — non-refundable — while the Graca rooftop cancels free until two days before check-in. The $54-a-night gap is what flexibility costs here.",
        products: [GUESTHOUSE_ALFAMA, ROOFTOP_SUITES],
      },
      {
        label: "Day 2 — Old city on foot + azulejo workshop",
        note: "Morning: get lost in Alfama and Mouraria. Afternoon: tile-painting atelier in Baixa.",
        products: [TILE_WORKSHOP],
      },
      {
        label: "Day 3 — Sintra day trip",
        note: "Storybook palaces and wild Atlantic cliffs. Back by early evening.",
        products: [SINTRA_TRIP],
      },
      {
        label: "Day 4 — Slow morning, head home",
        note: "A last espresso on a miradouro, then check out.",
        products: [],
      },
    ],
  },

  comparison: {
    title: "Flexibility, priced",
    entries: [
      {
        product_id: FLIGHT_ECONOMY.product_id,
        product: FLIGHT_ECONOMY,
        pros: ["Nonstop overnight — land at 06:35", "Saves $622 per person", "Same departure time"],
        cons: ["Non-refundable — changes cost a fee", "Tighter seat for 7 hours"],
        best_for: "Locked-in dates and a carry-on mindset",
      },
      {
        product_id: FLIGHT_PREMIUM.product_id,
        product: FLIGHT_PREMIUM,
        pros: ["Fully refundable fare", "Wider seat, deeper recline", "Two checked bags included"],
        cons: ["$622 more per person"],
        best_for: "Plans that might move — or anyone who wants to sleep",
      },
    ],
    dimensions: ["price", "refundability", "comfort", "baggage"],
    recommended_product_id: FLIGHT_PREMIUM.product_id,
    // The price spread the server attaches to every comparison.
    price_delta: {
      amount: 622.0,
      low_product_id: FLIGHT_ECONOMY.product_id,
      low_price: 498.0,
      high_product_id: FLIGHT_PREMIUM.product_id,
      high_price: 1120.0,
    },
  },

  products: {
    title: "Boutique stays in Alfama & Graca",
    layout: "carousel" as const,
    items: [
      { product: GUESTHOUSE_ALFAMA, reason: "Best-loved townhouse in the old town" },
      { product: ROOFTOP_SUITES, reason: "Private rooftop, castle-to-river views" },
      { product: FADO_WALK, reason: "Pairs perfectly with either stay" },
    ],
  },

  checkout: {
    note: "Three nights at ACME Guesthouses, a Sintra day, and a fado evening for two — confirmation lands by email within a minute of booking.",
    fulfillment_method: "delivery" as const,
    cart: {
      items: [
        {
          product_id: GUESTHOUSE_ALFAMA.product_id,
          title: GUESTHOUSE_ALFAMA.title,
          price: 214.0,
          quantity: 3,
          line_total: 642.0,
        },
        {
          product_id: FADO_WALK.product_id,
          title: FADO_WALK.title,
          price: 86.0,
          quantity: 2,
          line_total: 172.0,
        },
        {
          product_id: SINTRA_TRIP.product_id,
          title: SINTRA_TRIP.title,
          price: 118.0,
          quantity: 2,
          line_total: 236.0,
        },
      ],
      item_count: 7,
      subtotal: 1050.0,
      currency: "USD",
    },
  },

  order_status: {
    order_id: "AL-30418",
    summary:
      "Your Kyoto trip is processing — the flight is ticketed and ACME Ryokan is confirming your three nights now. Everything lands in one email when it clears.",
    next_step: "No action needed; confirmation usually clears within a few hours.",
    order: {
      order_id: "AL-30418",
      status: "processing",
      placed_at: "2026-05-30T22:41:00Z",
      items: [
        { product_id: "AL-FLT-204", title: "San Francisco to Kyoto — Economy, One Stop", quantity: 1, price: 812.0 },
        { product_id: "AL-STAY-108", title: "ACME Ryokan Higashiyama Annex", quantity: 3, price: 358.0 },
      ],
      total: 1886.0,
      currency: "USD",
      estimated_delivery: "2026-11-06",
      tracking_url: "https://trips.example.com/AL-30418",
    },
  },
} as const;

export const SHOWCASE_PRODUCT_INDEX: Record<string, Product> = Object.fromEntries(
  [
    GUESTHOUSE_ALFAMA,
    ROOFTOP_SUITES,
    FADO_WALK,
    TILE_WORKSHOP,
    SINTRA_TRIP,
    FLIGHT_ECONOMY,
    FLIGHT_PREMIUM,
  ].map((product) => [product.product_id, product]),
);
