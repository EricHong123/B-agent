// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** Copied from ../data/policies.json; keep in sync with it. */
export const STORE_POLICY = {
  returnsShort: "30-day returns",
  returnsLine: "Most items can be returned within 30 days of delivery for a refund to your original payment method.",
  freeShippingThreshold: 49,
  standardShippingEta: "3–5 business days",
} as const;
