// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** Renders from fixtures; no API needed. */

import type { ReactNode } from "react";
import { type UISlotStatus, useT } from "web-shared";
import TripPanel from "@/components/TripPanel";
import GenerativeBlock from "@/components/generative";
import { SHOWCASE, SHOWCASE_PRODUCT_INDEX } from "@/lib/showcase-fixtures";
import type { CartPayload } from "@/lib/types";

/** `id` sets the data-component when a component repeats. */
const SECTIONS: { component: string; id?: string; payload: unknown; status?: UISlotStatus }[] = [
  { component: "itinerary", payload: SHOWCASE.itinerary },
  // Two stays on one arrival day are alternatives, so the footer prices the pick.
  {
    component: "itinerary",
    id: "itinerary-alternatives",
    payload: SHOWCASE.itinerary_alternatives,
  },
  // The first two days frozen mid-stream: skeleton days plus the "Planning day 3 of 4" counter.
  {
    component: "itinerary",
    id: "itinerary-streaming",
    payload: { ...SHOWCASE.itinerary, days: SHOWCASE.itinerary.days.slice(0, 2) },
    status: "partial",
  },
  { component: "comparison", payload: SHOWCASE.comparison },
  { component: "products", payload: SHOWCASE.products },
  { component: "checkout", payload: SHOWCASE.checkout },
  { component: "order_status", payload: SHOWCASE.order_status },
];

function Section({ name, children }: { name: string; children: ReactNode }) {
  return (
    <section className="mt-10">
      <h2 className="al-display mb-3 text-[16px] font-semibold italic text-(--ink-soft)">{name}</h2>
      <div data-component={name}>{children}</div>
    </section>
  );
}

export default function ShowcasePage() {
  const t = useT();
  return (
    <main className="relative z-[2] mx-auto max-w-3xl px-6 py-14">
      <p className="text-[11px] font-semibold uppercase tracking-[0.08em] text-(--ink-soft)">
        {t("ACME Travel component showcase (fixture data)")}
      </p>
      {SECTIONS.map(({ component, id = component, payload, status = "final" }) => (
        <Section key={id} name={id}>
          <GenerativeBlock block={{ component, payload }} status={status} />
        </Section>
      ))}
      <Section name="trip">
        <div className="flex h-[440px] max-w-[380px] flex-col overflow-hidden rounded-(--radius-lg) border border-(--line) bg-(--card) shadow-(--shadow)">
          <TripPanel cart={SHOWCASE.checkout.cart as unknown as CartPayload} productIndex={SHOWCASE_PRODUCT_INDEX} />
        </div>
      </Section>
    </main>
  );
}
