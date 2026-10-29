// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** Renders present_plan_comparison; cell values come from the server. */

import { useRef } from "react";
import { type Translate, useT } from "web-shared";
import { formatPrice, formatPriceWithUnit } from "@/lib/format";
import { useOverflow } from "@/lib/overflow";
import type { AccountUsage, PlanMatrixPayload, Product } from "@/lib/types";
import { Frame } from "./shared";

function vsTodayDelta(
  plan: Product,
  current: PlanMatrixPayload["current_plan"],
  t: Translate,
): string | null {
  const currentPrice = current?.price_per_month;
  if (currentPrice == null || plan.attributes?.price_unit !== "per_month") return null;
  if (plan.product_id === current?.product_id) return t("your plan today");
  // Round to cents so float subtraction does not leak into the label.
  const delta = Math.round((plan.price - currentPrice) * 100) / 100;
  if (delta === 0) return t("same price as today");
  return t("{sign}{amount}/mo vs today", { sign: delta > 0 ? "+" : "−", amount: formatPrice(Math.abs(delta)) });
}

function fitsUsage(plan: Product, avgGb: number): boolean | null {
  const allowance = plan.attributes?.data_allowance_gb;
  if (!allowance) return null;
  if (allowance.trim().toLowerCase() === "unlimited") return true;
  const numeric = Number(allowance);
  return Number.isFinite(numeric) ? numeric >= avgGb : null;
}

/** The preference tag renders only when best_for is written in preference terms. */
const PREFERENCE_FLAVOR = /\b(your?|prefers?|preference|saved|remembered)\b/i;

function UsageBand({
  usage,
  current,
}: {
  usage: AccountUsage;
  current: PlanMatrixPayload["current_plan"];
}) {
  const t = useT();
  const cycles = usage.cycles_gb_last_3 ?? [];
  if (cycles.length === 0) return null;
  const allowanceRaw = current?.data_allowance_gb;
  const allowance =
    allowanceRaw && allowanceRaw.trim().toLowerCase() !== "unlimited"
      ? Number(allowanceRaw)
      : null;
  // Headroom above the tallest bar so an over-allowance bar is not clipped.
  const scaleMax = Math.max(...cycles, allowance ?? 0) * 1.18;
  const spend = usage.top_up_spend_usd_last_3_months;

  return (
    <div className="flex flex-wrap items-end justify-between gap-x-6 gap-y-2 border-b border-(--line) bg-(--well)/50 px-4 py-3">
      <div className="flex items-end gap-3">
        <div
          className="relative h-[46px] w-[76px]"
          role="img"
          aria-label={usage.note ?? t("Data used in each of the last 3 billing cycles")}
        >
          <div className="absolute inset-0 flex items-end justify-between">
            {cycles.map((gb, index) => {
              const over = allowance != null && gb > allowance;
              return (
                <span
                  key={index}
                  className={`am-reveal-item w-[18px] ${over ? "bg-(--warn)/70" : "bg-(--accent)/80"}`}
                  style={{
                    height: `${Math.min((gb / scaleMax) * 100, 100)}%`,
                    animationDelay: `${index * 80}ms`,
                  }}
                />
              );
            })}
          </div>
          {allowance != null ? (
            <span
              aria-hidden
              className="absolute inset-x-[-4px] border-t border-dashed border-(--ink)"
              style={{ bottom: `${Math.min((allowance / scaleMax) * 100, 100)}%` }}
            />
          ) : null}
        </div>
        <div>
          <p className="am-meta">{t("Your last 3 cycles")}</p>
          {allowance != null ? (
            <p className="am-mono mt-0.5 text-[11px] leading-snug text-(--ink-soft)">
              {current?.name
                ? t("---- {gb} GB allowance ({name})", { gb: allowanceRaw ?? "", name: current.name })
                : t("---- {gb} GB allowance", { gb: allowanceRaw ?? "" })}
            </p>
          ) : null}
        </div>
      </div>
      <p className="am-mono text-[12px] font-semibold text-(--ink)">
        {t("Avg {avg} GB/mo", { avg: usage.avg_gb_per_month_last_3 })}
        {usage.top_ups_last_3_months > 0 && spend != null ? (
          <span className="text-(--warn)">
            {" "}
            · {t("{n} top-ups ≈ {amount} in 3 months", { n: usage.top_ups_last_3_months, amount: formatPrice(spend) })}
          </span>
        ) : null}
      </p>
    </div>
  );
}

function MatrixSkeleton() {
  const t = useT();
  return (
    <div aria-label={t("Building the plan comparison")} className="p-4">
      <div className="flex gap-3">
        <div className="w-[110px] shrink-0" />
        {[0, 1, 2, 3].map((column) => (
          <div key={column} className="flex flex-1 flex-col gap-2">
            <div className="am-shimmer h-4 w-3/4" />
            <div className="am-shimmer h-6 w-1/2" />
          </div>
        ))}
      </div>
      {[0, 1, 2, 3, 4].map((row) => (
        <div key={row} className="mt-3 border-t border-(--line) pt-3">
          <div className="am-shimmer h-3.5 w-full" style={{ animationDelay: `${row * 90}ms` }} />
        </div>
      ))}
    </div>
  );
}

export default function PlanMatrix({ payload }: { payload: PlanMatrixPayload }) {
  const t = useT();
  const { plans, rows, annotations, recommended_plan_id: recommended } = payload;
  const bestFor = (planId: string) => annotations?.find((a) => a.plan_id === planId)?.best_for;
  const avgGb = payload.account_usage?.avg_gb_per_month_last_3;

  const scrollerRef = useRef<HTMLDivElement>(null);
  const { overflow, sync: syncOverflow } = useOverflow(scrollerRef, plans.length);
  const nudge = (direction: 1 | -1) => {
    const node = scrollerRef.current;
    node?.scrollBy({ left: direction * 160, behavior: "smooth" });
  };

  // The price row already renders in the header.
  const bodyRows = (rows ?? []).filter((row) => row.key !== "price");

  if (plans.length === 0) {
    return (
      <Frame component="plan_matrix" label={payload.title ?? t("Plan comparison")} flush>
        <MatrixSkeleton />
      </Frame>
    );
  }

  return (
    <Frame
      component="plan_matrix"
      label={payload.title ?? t("Plan comparison")}
      flush
    >
      {payload.account_usage ? (
        <UsageBand usage={payload.account_usage} current={payload.current_plan} />
      ) : null}
      <div className="relative">
        <div ref={scrollerRef} onScroll={syncOverflow} className="panel-scroll overflow-x-auto">
          <table className="w-full border-collapse text-left" style={{ minWidth: plans.length * 150 + 130 }}>
          <thead>
            <tr className="align-bottom">
              <th className="sticky left-0 z-10 w-[130px] min-w-[130px] bg-(--surface) p-3 pb-4" aria-label={t("dimension")} />
              {plans.map((plan) => {
                const isRec = plan.product_id === recommended;
                const delta = vsTodayDelta(plan, payload.current_plan, t);
                const fits = avgGb != null ? fitsUsage(plan, avgGb) : null;
                const annotationText = bestFor(plan.product_id) ?? "";
                const matchesPreference = isRec && PREFERENCE_FLAVOR.test(annotationText);
                return (
                  <th
                    key={plan.product_id}
                    className={`relative p-3 pb-4 font-normal ${isRec ? "bg-(--accent-soft)/40" : ""}`}
                  >
                    {isRec ? (
                      <span className="am-tag am-tag--accent absolute -top-0 left-3 translate-y-[-0%]">
                        ✓ {t("Recommended")}
                      </span>
                    ) : null}
                    <p className="mt-5 text-[15px] font-bold leading-tight text-(--ink)">
                      {plan.title}
                    </p>
                    <p className="am-mono mt-1.5 text-[22px] font-semibold leading-none tracking-tight text-(--ink)">
                      {formatPriceWithUnit(plan)}
                    </p>
                    {plan.attributes?.price_qualifier ? (
                      <p className="am-mono mt-1 text-[11px] leading-snug text-(--ink-soft)">
                        {plan.attributes.price_qualifier}
                      </p>
                    ) : null}
                    {delta ? (
                      <p className="am-mono mt-1 text-[11px] font-semibold leading-snug text-(--ink-soft)">
                        {delta}
                      </p>
                    ) : null}
                    {fits != null ? (
                      <p
                        className={`am-mono mt-1 text-[11px] font-semibold leading-snug ${
                          fits ? "text-(--accent)" : "text-(--warn)"
                        }`}
                      >
                        {fits ? t("✓ fits your {avg} GB avg", { avg: avgGb ?? "" }) : t("⚠ under your {avg} GB avg", { avg: avgGb ?? "" })}
                      </p>
                    ) : null}
                    {bestFor(plan.product_id) ? (
                      <p className="mt-1.5 text-[11.5px] font-medium leading-snug text-(--ink-soft)">
                        {bestFor(plan.product_id)}
                      </p>
                    ) : null}
                    {matchesPreference ? (
                      <span className="am-tag mt-1.5">
                        <b aria-hidden className="text-(--accent)">
                          ●
                        </b>{" "}
                        {t("matches a saved preference")}
                      </span>
                    ) : null}
                  </th>
                );
              })}
            </tr>
          </thead>
          <tbody>
            {bodyRows.map((row, rowIndex) => (
              <tr
                key={row.key}
                className="am-reveal-item border-t border-(--line)"
                style={{ animationDelay: `${rowIndex * 60}ms` }}
              >
                <th className="am-meta sticky left-0 z-10 w-[130px] min-w-[130px] bg-(--surface) p-3 align-top font-semibold">
                  {row.label}
                </th>
                {row.values.map((value, columnIndex) => {
                  const isRec = plans[columnIndex]?.product_id === recommended;
                  return (
                    <td
                      key={columnIndex}
                      className={`am-mono p-3 align-top text-[13px] text-(--ink) ${
                        isRec ? "bg-(--accent-soft)/40 font-semibold" : ""
                      }`}
                    >
                      {value === "Unlimited" ? (
                        <span>
                          <span className="am-tick">✓</span> {t("Unlimited")}
                        </span>
                      ) : value === "—" ? (
                        <span className="text-(--ink-soft)/60">—</span>
                      ) : (
                        value
                      )}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
          </table>
        </div>
        {overflow.left ? (
          <>
            <div
              aria-hidden
              className="pointer-events-none absolute inset-y-0 left-[130px] w-8 bg-gradient-to-r from-(--surface) to-transparent"
            />
            <button
              onClick={() => nudge(-1)}
              aria-label={t("Scroll to previous plans")}
              className="am-mono absolute left-[134px] top-10 rounded-(--radius) border border-(--line) bg-(--surface) px-2 py-1 text-sm text-(--ink) shadow-md transition hover:border-(--accent)"
            >
              ‹
            </button>
          </>
        ) : null}
        {overflow.right ? (
          <>
            <div
              aria-hidden
              className="pointer-events-none absolute inset-y-0 right-0 w-8 bg-gradient-to-l from-(--surface) to-transparent"
            />
            <button
              onClick={() => nudge(1)}
              aria-label={t("Scroll to more plans")}
              className="am-mono absolute right-1 top-10 rounded-(--radius) border border-(--line) bg-(--surface) px-2 py-1 text-sm text-(--ink) shadow-md transition hover:border-(--accent)"
            >
              ›
            </button>
          </>
        ) : null}
      </div>
    </Frame>
  );
}
