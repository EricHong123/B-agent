// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** Payloads for /showcase in post-enrichment shape; values follow data/ and MockTelecom. */

import type {
  AccountContext,
  CheckoutPayload,
  ComparisonPayload,
  DisclosurePayload,
  GuidePayload,
  OrderStatusPayload,
  PlanMatrixPayload,
  Product,
  ProductsPayload,
} from "./types";

/** The live API anchors contract dates to the boot date; these are fixed. */
const ACCOUNT: AccountContext = {
  current_plan: {
    product_id: "AM-PLAN-101",
    name: "Essential 5GB",
    price_per_month: 35.0,
    data_allowance_gb: "5",
  },
  contract: {
    started: "2024-08-14",
    month: 23,
    of_months: 24,
    ends: "2026-08-14",
    early_upgrade_on: "2026-06-14",
  },
  device: {
    product_id: "AM-DEV-201",
    name: "ACME Phone 4",
    installments_remaining: 1,
    installment_usd: 29.13,
  },
  upgrade_eligibility: {
    eligible: true,
    kind: "early-with-trade-in",
    reason:
      "month 23 of 24; early upgrade available with a qualifying trade-in; outright upgrade on 2026-08-14",
  },
  trade_in_estimate: {
    device: "ACME Phone 4",
    tier: "B",
    estimated_credit_usd: 200,
    condition_assumption:
      "assumes qualifying condition: powers on, screen intact, activation lock removed",
    quote_valid_through: "2026-08-13",
    note: "applied as 24 monthly bill credits; estimate re-runs on arrival if the device condition differs",
  },
  monthly_bill_usd: 64.13,
  recent_usage: {
    avg_gb_per_month_last_3: 14.2,
    cycles_gb_last_3: [13.4, 14.9, 14.3],
    top_ups_last_3_months: 4,
    top_up_spend_usd_last_3_months: 40.0,
    note: "hit the 5GB allowance in each of the last 3 cycles",
  },
};

const PLAN_102: Product = {
  product_id: "AM-PLAN-102",
  title: "Plus 15GB",
  brand: "ACME Mobile",
  price: 50.0,
  currency: "USD",
  rating: 4.4,
  review_count: 2210,
  category: "plans",
  labels: ["Fits most people"],
  attributes: {
    price_unit: "per_month",
    price_qualifier: "+ taxes & fees · incl. $5 AutoPay discount",
    data_allowance_gb: "15",
    hotspot_gb: "10",
    video_quality: "1080p",
    intl_roaming: "pay-per-day",
    contract_term: "none",
    price_guarantee: "2-year price guarantee",
  },
  in_stock: true,
  short_description:
    "15GB of high-speed data with 10GB of hotspot — the sweet spot for commuters and podcast people.",
};

const PLAN_103: Product = {
  product_id: "AM-PLAN-103",
  title: "Unlimited",
  brand: "ACME Mobile",
  price: 65.0,
  currency: "USD",
  rating: 4.6,
  review_count: 5320,
  category: "plans",
  labels: ["Most popular"],
  attributes: {
    price_unit: "per_month",
    price_qualifier: "+ taxes & fees · incl. $5 AutoPay discount",
    data_allowance_gb: "unlimited",
    hotspot_gb: "25",
    video_quality: "1080p",
    intl_roaming: "Canada & Mexico included",
    contract_term: "none",
    price_guarantee: "3-year price guarantee",
  },
  in_stock: true,
  short_description:
    "Unlimited data with 25GB of hotspot and a 3-year price guarantee — the plan most ACME Mobile customers land on.",
};

const PLAN_104: Product = {
  product_id: "AM-PLAN-104",
  title: "Unlimited Plus",
  brand: "ACME Mobile",
  price: 85.0,
  currency: "USD",
  rating: 4.7,
  review_count: 3105,
  category: "plans",
  labels: ["Best for heavy data + perks"],
  attributes: {
    price_unit: "per_month",
    price_qualifier: "+ taxes & fees · incl. $5 AutoPay discount",
    data_allowance_gb: "unlimited",
    hotspot_gb: "60",
    video_quality: "4K",
    intl_roaming: "90+ countries included",
    contract_term: "none",
    price_guarantee: "3-year price guarantee",
  },
  in_stock: true,
  short_description:
    "Everything turned up: premium network priority, 60GB hotspot, 4K streaming, 90+ country roaming, and ACME Streaming on us.",
};

const DEV_202: Product = {
  product_id: "AM-DEV-202",
  title: "ACME Phone 5",
  brand: "ACME",
  price: 949.0,
  currency: "USD",
  rating: 4.7,
  review_count: 1640,
  category: "devices",
  labels: ["New", "Top trade-in value"],
  attributes: {
    price_unit: "one_time",
    storage_gb: "256",
    screen_in: "6.7 unfolded / 4.0 cover",
    battery_hours: "29",
    connectivity: "5G",
    monthly_installment: "39.54 for 24 months",
    trade_in_tier: "A",
  },
  in_stock: true,
  short_description:
    "The new Phone: bigger cover screen, two more hours of battery than anything ACME has made, same pocketability.",
};

const DEV_203: Product = {
  product_id: "AM-DEV-203",
  title: "ACME Phone 5 Pro",
  brand: "ACME",
  price: 1099.0,
  currency: "USD",
  rating: 4.8,
  review_count: 2230,
  category: "devices",
  labels: ["Flagship camera"],
  attributes: {
    price_unit: "one_time",
    screen_in: "6.8",
    battery_hours: "31",
    connectivity: "5G",
    monthly_installment: "45.79 for 24 months",
    trade_in_tier: "A",
  },
  in_stock: true,
  short_description:
    "ACME's slab flagship: the best camera system in the lineup and a battery that ignores the day.",
  options: { storage: ["256 GB", "512 GB"], color: ["graphite", "glacier"] },
};

const DEV_204: Product = {
  product_id: "AM-DEV-204",
  title: "ACME Phone 5 Lite",
  brand: "ACME",
  price: 799.0,
  currency: "USD",
  rating: 4.5,
  review_count: 1985,
  category: "devices",
  labels: [],
  attributes: {
    price_unit: "one_time",
    storage_gb: "128",
    screen_in: "6.4",
    battery_hours: "26",
    connectivity: "5G",
    monthly_installment: "33.29 for 24 months",
    trade_in_tier: "B",
  },
  in_stock: true,
  short_description:
    "The sensible flagship: clean software, seven years of updates, and a camera that just gets it right.",
};

const DEV_206: Product = {
  product_id: "AM-DEV-206",
  title: "ACME Phone 3",
  brand: "ACME",
  price: 249.0,
  currency: "USD",
  rating: 4.2,
  review_count: 3320,
  category: "devices",
  labels: ["Best under $250"],
  attributes: {
    price_unit: "one_time",
    storage_gb: "128",
    screen_in: "6.5",
    battery_hours: "33",
    connectivity: "5G",
    trade_in_tier: "C",
  },
  in_stock: true,
  short_description:
    "The budget phone that quietly does 90% of what flagships do, with the longest battery in the store.",
};

const plan_matrix: PlanMatrixPayload = {
  title: "Plans that fit a 15GB month",
  plans: [PLAN_102, PLAN_103, PLAN_104],
  rows: [
    { key: "price", label: "Price", values: ["$50/mo", "$65/mo", "$85/mo"] },
    { key: "data_allowance_gb", label: "High-speed data", values: ["15 GB", "Unlimited", "Unlimited"] },
    { key: "hotspot_gb", label: "Hotspot data", values: ["10 GB", "25 GB", "60 GB"] },
    { key: "video_quality", label: "Video streaming", values: ["1080p", "1080p", "4K"] },
    {
      key: "intl_roaming",
      label: "International roaming",
      values: ["pay-per-day", "Canada & Mexico included", "90+ countries included"],
    },
    {
      key: "price_guarantee",
      label: "Price guarantee",
      values: ["2-year price guarantee", "3-year price guarantee", "3-year price guarantee"],
    },
  ],
  annotations: [
    { plan_id: "AM-PLAN-102", best_for: "predictable months under 15GB" },
    { plan_id: "AM-PLAN-103", best_for: "stop thinking about data" },
    { plan_id: "AM-PLAN-104", best_for: "hotspot-heavy work + travel" },
  ],
  recommended_plan_id: "AM-PLAN-103",
  current_plan: ACCOUNT.current_plan,
  account_usage: ACCOUNT.recent_usage,
};

/** best_for is written in preference terms, which shows the preference tag. */
const plan_matrix_memory: PlanMatrixPayload = {
  ...plan_matrix,
  title: "Plans with a locked-in price",
  annotations: [
    { plan_id: "AM-PLAN-102", best_for: "predictable months under 15GB" },
    {
      plan_id: "AM-PLAN-103",
      best_for: "your predictable-bill preference: 3-year price guarantee",
    },
    { plan_id: "AM-PLAN-104", best_for: "hotspot-heavy work + travel" },
  ],
};

const disclosure_plan: DisclosurePayload = {
  title: "Essential 5GB: service facts",
  product_id: "AM-PLAN-101",
  rows: [
    { label: "Monthly price", value: "$35", note: "includes the $5/mo AutoPay & paperless discount" },
    {
      label: "Additional monthly fees",
      value: "$1.45/line Network Compliance Surcharge",
      note: "an ACME Mobile charge, not a government tax; taxes vary by location",
    },
    { label: "One-time fees", value: "$35 activation, waived online" },
    { label: "Early termination fee", value: "$0" },
    { label: "High-speed data", value: "5 GB", note: "then 512 Kbps, no overage charges" },
    { label: "Network management", value: "may be deprioritized past 5 GB during congestion" },
    { label: "Video resolution", value: "480p" },
    {
      label: "Price guarantee",
      value: "1-year price guarantee",
      note: "covers the plan price; taxes, fees, and add-ons excluded",
    },
    {
      label: "Estimated all-in",
      value: "$36.45/mo",
      note: "plan + ACME surcharge, before location taxes",
    },
  ],
  sources: [
    "plan-pricing-disclosures",
    "network-management-disclosure",
    "data-top-ups-and-overage",
    "early-termination",
  ],
  footnotes: [
    "Prices shown include the AutoPay and paperless billing discount.",
    "Typical speeds are medians measured across the network in the last quarter.",
  ],
};

const disclosure: DisclosurePayload = {
  title: "Home Fiber 1 Gig: service facts",
  product_id: "AM-NET-302",
  rows: [
    { label: "Monthly price", value: "$70", note: "includes the $5/mo AutoPay & paperless discount" },
    {
      label: "Additional monthly fees",
      value: "$1.45/line Network Compliance Surcharge",
      note: "an ACME Mobile charge, not a government tax; taxes vary by location",
    },
    { label: "One-time fees", value: "$35 activation, waived online" },
    { label: "Early termination fee", value: "$0" },
    { label: "Typical download speed", value: "940 Mbps" },
    { label: "Typical upload speed", value: "880 Mbps" },
    { label: "Typical latency", value: "11 ms" },
    { label: "Data included", value: "Unlimited", note: "no overage charges" },
    { label: "Equipment fee", value: "$0, gateway included" },
    {
      label: "Price guarantee",
      value: "2-year price guarantee",
      note: "covers the plan price; taxes, fees, and add-ons excluded",
    },
    {
      label: "Estimated all-in",
      value: "$71.45/mo",
      note: "plan + ACME surcharge, before location taxes",
    },
  ],
  sources: [
    "plan-pricing-disclosures",
    "network-management-disclosure",
    "data-top-ups-and-overage",
    "early-termination",
  ],
  footnotes: [
    "Prices shown include the AutoPay and paperless billing discount.",
    "Typical speeds are medians measured across the network in the last quarter.",
  ],
};

const products: ProductsPayload = {
  title: "Upgrade picks for a Phone 4 trade-in",
  layout: "carousel",
  items: [
    { product: DEV_202, reason: "The direct upgrade — same pocket, two more hours of battery." },
    { product: DEV_203, reason: "If you'd trade the fold for the best camera in the lineup." },
    { product: DEV_204, reason: "The sensible pick: seven years of updates, $200 less." },
    { product: DEV_206, reason: "The budget reset — pay off the line, pocket the difference." },
  ],
};

const comparison: ComparisonPayload = {
  title: "Phone 5 vs Phone 5 Pro vs ACME Phone 5 Lite",
  entries: [
    {
      product_id: "AM-DEV-202",
      product: DEV_202,
      pros: ["Pockets like nothing else", "Cover screen runs full apps", "Tier-A trade-in value"],
      cons: ["Camera trails the Phone 5 Pro"],
      best_for: "Phone 4 owners who love the shape",
    },
    {
      product_id: "AM-DEV-203",
      product: DEV_203,
      pros: ["Best camera in the lineup", "31-hour battery", "Brightest display"],
      cons: ["Big in the pocket", "$100 more"],
      best_for: "photo-first buyers",
    },
    {
      product_id: "AM-DEV-204",
      product: DEV_204,
      pros: ["7 years of updates", "Cleanest software", "$200 cheaper"],
      cons: ["Slower charging", "No fold tricks"],
      best_for: "keep-it-five-years pragmatists",
    },
  ],
  recommended_product_id: "AM-DEV-202",
};

const guide: GuidePayload = {
  title: "Your early-upgrade math, grounded",
  sections: [
    {
      heading: "You're eligible now",
      body: "You're in month 23 of 24 on the ACME Phone 4 agreement — early upgrade is open now with a qualifying trade-in. Outright upgrade (no trade-in needed) unlocks next month.",
    },
    {
      heading: "What the trade-in gets you",
      body: "The Phone 4 is a tier-B device: $200 in credit, applied as 24 monthly bill credits. The up-to-$350 installment waiver applies only to tier-A trade-ins, so your last Phone 4 installment still comes due.",
    },
    {
      heading: "The fine print that matters",
      body: "Trade-in must power on with an intact screen and activation lock removed. Leave ACME Mobile before the 24 credits finish and the remainder is forfeited.",
    },
  ],
  related_products: [DEV_202],
  sources: ["upgrade-eligibility", "trade-in-program", "device-financing"],
};

const checkout: CheckoutPayload = {
  note: "Switching from Essential 5GB to Unlimited takes effect immediately, prorated — no plan-change fee. The Phone 5 ships free 2-day with signature.",
  fulfillment_method: "shipping",
  cart: {
    items: [
      { product_id: "AM-PLAN-103", title: "Unlimited", price: 65.0, quantity: 1, line_total: 65.0 },
      { product_id: "AM-DEV-202", title: "ACME Phone 5", price: 949.0, quantity: 1, line_total: 949.0 },
      { product_id: "AM-ADD-401", title: "Data Top-Up 5GB", price: 10.0, quantity: 1, line_total: 10.0 },
    ],
    item_count: 3,
    subtotal: 1024.0,
    currency: "USD",
  },
};

const order_status: OrderStatusPayload = {
  order_id: "AM-91920",
  summary:
    "Your Roaming Day Passes are processing — they'll attach to your line before your trip and only bill on days you actually use them abroad.",
  next_step: "Nothing to do: passes activate automatically the first time your phone touches a partner network.",
  order: {
    order_id: "AM-91920",
    status: "processing",
    placed_at: "2026-05-28T15:48:00Z",
    items: [{ product_id: "AM-ADD-402", title: "Roaming Day Pass", quantity: 3, price: 9.0 }],
    total: 27.0,
    currency: "USD",
    estimated_delivery: "2026-06-08",
  },
};

export const SHOWCASE = {
  plan_matrix,
  plan_matrix_memory,
  disclosure,
  disclosure_plan,
  products,
  comparison,
  guide,
  checkout,
  order_status,
  account: ACCOUNT,
};
