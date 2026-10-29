// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { dateBlock, statusPill } from "@/lib/format";
import type { PlanPayload, Product } from "@/lib/types";
import { AllInPrice, Pill, Stub } from "./shared";

function StepProduct({ product }: { product: Product }) {
  const attrs = product.attributes ?? {};
  const date = dateBlock(attrs.event_date);
  return (
    <div className="flex items-center gap-2.5 rounded-(--radius) border border-(--line) bg-(--well)/40 px-2.5 py-2">
      {date ? (
        <span className="at-mono shrink-0 text-[11px] font-semibold text-(--accent)">
          {date.mon} {date.day}
        </span>
      ) : null}
      <span className="min-w-0 flex-1 truncate text-[13px] text-(--ink)">
        {attrs.event_name ?? product.title}
        {attrs.tier ? (
          <span className="at-mono ml-1.5 text-[11px] text-(--ink-soft)">{attrs.tier}</span>
        ) : null}
      </span>
      <Pill pill={statusPill(product)} />
      <AllInPrice price={product.price} currency={product.currency} size="sm" />
    </div>
  );
}

export default function PlanCard({
  payload,
  partial,
}: {
  payload: PlanPayload;
  partial?: boolean;
}) {
  return (
    <Stub component="plan" label={payload.title}>
      {payload.intro ? (
        <p className="mb-3 text-[14px] leading-snug text-(--ink-soft)">{payload.intro}</p>
      ) : null}
      <ol className="space-y-3">
        {(payload.steps ?? []).map((step, index) => (
          <li key={`${step.label}-${index}`} className="at-reveal-item flex gap-3">
            <span className="at-mono mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border border-(--line) text-[11px] font-semibold text-(--ink-soft)">
              {index + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[15px] font-semibold text-(--ink)">{step.label}</p>
              {step.detail ? (
                <p className="mt-0.5 text-[13px] leading-snug text-(--ink-soft)">
                  {step.detail}
                </p>
              ) : null}
              {step.products?.length ? (
                <div className="mt-1.5 space-y-1.5">
                  {step.products.map((product) => (
                    <StepProduct key={product.product_id} product={product} />
                  ))}
                </div>
              ) : null}
            </div>
          </li>
        ))}
      </ol>
      {partial ? (
        <div className="mt-3 flex gap-3">
          <div className="at-skeleton h-5 w-5 shrink-0 rounded-full" />
          <div className="flex min-w-0 flex-1 flex-col gap-1.5">
            <div className="at-skeleton h-4 w-1/2" />
            <div className="at-skeleton h-8 w-full" />
          </div>
        </div>
      ) : null}
    </Stub>
  );
}
