// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { formatMoney, useT } from "web-shared";
import { rich } from "@/lib/rich";
import type { PlanPayload, Product } from "@/lib/types";
import ProductTile, { ProductRow } from "../ProductTile";

const SEGMENT_CLASSES = ["bg-sky-400", "bg-emerald-400", "bg-violet-400", "bg-amber-400", "bg-rose-400"];

/** Each priced step contributes its cheapest option. */
function BudgetBar({ steps }: { steps: PlanPayload["steps"] }) {
  const t = useT();
  const priced = steps.map((step) =>
    step.products.length ? Math.min(...step.products.map((product) => product.price)) : 0,
  );
  const total = priced.reduce((sum, price) => sum + price, 0);
  // A step arrives without products when the model attached none or the server dropped them.
  const withoutItems = steps.filter((step) => step.products.length === 0).length;
  if (total <= 0 || steps.length < 2) return null;
  return (
    <div data-plan-budget className="mt-2.5">
      <div className="flex h-2 w-full gap-px overflow-hidden rounded-full bg-(--well)">
        {steps.map((step, index) =>
          priced[index] > 0 ? (
            <div
              key={`${step.label}-${index}`}
              className={`h-full ${SEGMENT_CLASSES[index % SEGMENT_CLASSES.length]}`}
              style={{ width: `${(priced[index] / total) * 100}%` }}
              title={`${step.label} · ${formatMoney(priced[index])}`}
            />
          ) : null,
        )}
      </div>
      <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-0.5 text-[11px] text-(--ink-soft)">
        <span>
          {rich(
            t(steps.some((step) => step.products.length > 1) ? "Planned picks {amount} (cheapest option per step)" : "Planned picks {amount}"),
            { amount: <span className="font-semibold text-(--ink)">{formatMoney(total)}</span> },
          )}
        </span>
        {withoutItems > 0 ? (
          <span>
            {t(withoutItems === 1 ? "{count} step with no items to show" : "{count} steps with no items to show", { count: withoutItems })}
          </span>
        ) : null}
      </div>
    </div>
  );
}

export default function PlanChecklist({
  payload,
  onAdd,
  partial,
}: {
  payload: PlanPayload;
  onAdd?: (product: Product) => boolean | void | Promise<boolean | void>;
  partial?: boolean;
}) {
  const t = useT();
  const steps = payload.steps ?? [];
  return (
    <section className="rounded-2xl border border-(--line) bg-(--card) p-3.5 shadow-(--shadow-sm)">
      <h3 className="text-[15px] font-semibold text-(--ink)">{payload.title}</h3>
      {payload.intro ? <p className="mt-1 text-[15px] text-(--ink-soft)">{payload.intro}</p> : null}
      {partial ? null : <BudgetBar steps={steps} />}
      <ol className="mt-2.5 space-y-3">
        {steps.map((step, index) => (
          <li key={`${step.label}-${index}`} className="ac-reveal flex gap-3">
            <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-(--accent-soft) text-[13px] font-bold text-(--ink)">
              {index + 1}
            </div>
            <div className="min-w-0 flex-1">
              <div className="text-[15px] font-medium text-(--ink)">{step.label}</div>
              {step.detail ? <div className="text-[13px] text-(--ink-soft)">{step.detail}</div> : null}
              {step.products.length === 1 ? (
                <div className="mt-1.5">
                  <ProductRow product={step.products[0]} onAdd={onAdd} />
                </div>
              ) : step.products.length ? (
                <div className="panel-scroll mt-1.5 flex gap-2.5 overflow-x-auto pb-1">
                  {step.products.map((product) => (
                    <ProductTile key={product.product_id} product={product} compact onAdd={onAdd} />
                  ))}
                </div>
              ) : partial ? null : (
                <div className="mt-1 text-[13px] text-(--ink-soft)/80">{t("No items to show for this step.")}</div>
              )}
            </div>
          </li>
        ))}
        {partial ? (
          <li className="flex gap-3">
            <div className="ac-skeleton h-6 w-6 shrink-0 rounded-full" />
            <div className="min-w-0 flex-1 space-y-1.5">
              <div className="ac-skeleton h-4 w-2/5 rounded" />
              <div className="ac-skeleton h-[88px] w-full rounded-xl" />
            </div>
          </li>
        ) : null}
      </ol>
    </section>
  );
}
