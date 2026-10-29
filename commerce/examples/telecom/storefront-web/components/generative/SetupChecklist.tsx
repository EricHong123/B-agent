// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** Renders present_plan. */

import { useT } from "web-shared";
import PlanTile from "@/components/PlanTile";
import { formatPriceWithUnit } from "@/lib/format";
import type { PlanPayload } from "@/lib/types";
import { Frame } from "./shared";

export default function SetupChecklist({
  payload,
  partial,
}: {
  payload: PlanPayload;
  partial?: boolean;
}) {
  const t = useT();
  const steps = payload.steps ?? [];
  return (
    <Frame component="plan" label={payload.title ?? t("Setup plan")}>
      {payload.intro ? (
        <p className="mb-3 text-[15px] leading-relaxed text-(--ink-soft)">{payload.intro}</p>
      ) : null}
      <ol className="space-y-0">
        {steps.map((step, index) => (
          <li
            key={`${step.label}-${index}`}
            className={`am-reveal-item flex gap-4 py-3 ${index > 0 ? "am-rule" : ""}`}
            style={{ animationDelay: `${index * 70}ms` }}
          >
            <span className="am-mono w-8 shrink-0 text-[22px] font-light leading-none text-(--ink-soft)">
              {String(index + 1).padStart(2, "0")}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-[15px] font-bold leading-tight text-(--ink)">{step.label}</p>
              {step.detail ? (
                <p className="mt-1 text-[13px] leading-snug text-(--ink-soft)">{step.detail}</p>
              ) : null}
              {step.products.length ? (
                <div className="mt-2 space-y-2">
                  {step.products.map((product) => (
                    <PlanTile
                      key={product.product_id}
                      product={product}
                      note={product.product_id}
                      trailing={
                        <span className="am-mono shrink-0 text-[13px] font-semibold text-(--ink)">
                          {formatPriceWithUnit(product)}
                        </span>
                      }
                    />
                  ))}
                </div>
              ) : null}
            </div>
          </li>
        ))}
        {partial ? (
          <li className={`flex gap-4 py-3 ${steps.length ? "am-rule" : ""}`}>
            <span className="am-mono w-8 shrink-0 text-[22px] font-light leading-none text-(--ink-soft)/50">
              {String(steps.length + 1).padStart(2, "0")}
            </span>
            <div className="flex min-w-0 flex-1 flex-col gap-2">
              <div className="am-shimmer h-4 w-1/2" />
              <div className="am-shimmer h-3 w-3/4" />
            </div>
          </li>
        ) : null}
      </ol>
    </Frame>
  );
}
