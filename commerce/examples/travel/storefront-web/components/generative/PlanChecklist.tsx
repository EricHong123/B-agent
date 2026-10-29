// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useT } from "web-shared";
import type { PlanPayload } from "@/lib/types";
import {
  BODY,
  CARD,
  DISPLAY,
  META,
  MiniProductCard,
  display,
} from "./shared";

export default function PlanChecklist({
  payload,
  partial,
}: {
  payload: PlanPayload;
  partial?: boolean;
}) {
  const t = useT();
  const steps = payload.steps ?? [];
  return (
    <section className="al-reveal" style={{ ...CARD, padding: 24 }}>
      <h3 style={display(22, 600)}>{payload.title}</h3>
      {payload.intro ? (
        <p
          className="mt-1"
          style={{
            fontFamily: DISPLAY,
            fontStyle: "italic",
            fontWeight: 300,
            fontSize: 15,
            lineHeight: 1.5,
            color: "var(--ink-soft)",
          }}
        >
          {payload.intro}
        </p>
      ) : null}

      <ol className="mt-5">
        {steps.map((step, i) => {
          const last = i === steps.length - 1 && !partial;
          const products = step.products ?? [];
          return (
            <li
              key={`${step.label}-${i}`}
              className="al-reveal-item grid grid-cols-[36px_1fr] gap-x-3.5"
              style={{ animationDelay: `${i * 70}ms` }}
            >
              <div className="flex flex-col items-center">
                <span
                  className="flex h-9 w-9 shrink-0 items-center justify-center rounded-full"
                  style={{
                    fontFamily: DISPLAY,
                    fontWeight: 700,
                    fontSize: 17,
                    color: "var(--accent)",
                    background: "var(--accent-soft)",
                  }}
                >
                  {i + 1}
                </span>
                {!last ? (
                  <span aria-hidden className="mt-1.5 w-px flex-1" style={{ background: "var(--line)" }} />
                ) : null}
              </div>

              <div className={last ? "pt-1.5" : "pb-6 pt-1.5"}>
                <div style={{ fontFamily: BODY, fontWeight: 600, fontSize: 15, color: "var(--ink)" }}>
                  {step.label}
                </div>
                {step.detail ? (
                  <p
                    className="mt-0.5"
                    style={{ fontFamily: BODY, fontSize: 15, lineHeight: 1.5, color: "var(--ink-soft)" }}
                  >
                    {step.detail}
                  </p>
                ) : null}
                {products.length ? (
                  <div className="mt-2.5 flex flex-wrap gap-2.5">
                    {products.map((product) => (
                      <MiniProductCard key={product.product_id} product={product} />
                    ))}
                  </div>
                ) : null}
              </div>
            </li>
          );
        })}
        {partial ? (
          <li className="grid grid-cols-[36px_1fr] gap-x-3.5" aria-hidden>
            <div className="flex flex-col items-center">
              <span className="al-shimmer h-9 w-9 shrink-0 !rounded-full" />
            </div>
            <div className="flex flex-col gap-2 pt-1.5">
              <div className="al-shimmer h-4 w-2/5" />
              <div className="al-shimmer h-3.5 w-4/5" />
            </div>
          </li>
        ) : null}
      </ol>

      {!partial && steps.length ? (
        <p style={{ ...META, fontSize: 11, marginTop: 4 }}>
          {steps.length === 1 ? t("{n} step to ready", { n: steps.length }) : t("{n} steps to ready", { n: steps.length })}
        </p>
      ) : null}
    </section>
  );
}
