// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import type { CSSProperties } from "react";
import { formatMoney, useT } from "web-shared";
import { rich } from "@/lib/rich";
import type { ComparisonPayload } from "@/lib/types";
import { ProductImage, ProductTitle, Rating } from "../ProductTile";

const RECOMMENDED_LABEL = "Recommended";

/** The sign has its own column so text shares a left edge across rows. */
function TermRow({ sign, text }: { sign: "+" | "−"; text: string }) {
  return (
    <div className="grid grid-cols-[1.1rem_1fr] text-sm leading-normal text-(--ink)">
      <span aria-hidden className={sign === "+" ? "text-(--ok)" : "text-(--ink-soft)"}>
        {sign}
      </span>
      <span>{text}</span>
    </div>
  );
}

export default function ComparisonGrid({
  payload,
  partial,
}: {
  payload: ComparisonPayload;
  partial?: boolean;
}) {
  const t = useT();
  const entries = payload.entries ?? [];
  const delta = payload.price_delta;
  // Each pro/con line is a subgrid row, padded to the longest list, so the k-th line of
  // every card shares a baseline.
  const maxPros = Math.max(0, ...entries.map((entry) => (entry.pros ?? []).length));
  const maxCons = Math.max(0, ...entries.map((entry) => (entry.cons ?? []).length));
  const cardRows = { "--cmp-rows": `span ${2 + maxPros + maxCons}` } as CSSProperties;
  return (
    <section className="rounded-2xl border border-(--line) bg-(--card) p-4 shadow-(--shadow-sm)">
      {payload.title ? <h3 className="mb-3 text-[15px] font-semibold text-(--ink)">{payload.title}</h3> : null}
      <div className="grid gap-3 sm:grid-cols-2">
        {entries.map((entry) => {
          const recommended = payload.recommended_product_id === entry.product_id;
          const pros = entry.pros ?? [];
          const cons = entry.cons ?? [];
          return (
            <div
              key={entry.product_id}
              style={cardRows}
              className={`grid content-start gap-2 rounded-xl border p-4 sm:grid-rows-subgrid sm:[grid-row:var(--cmp-rows)] ${
                recommended ? "border-(--accent) bg-(--accent-soft)/60" : "border-(--line)"
              }`}
            >
              <div className="flex items-center gap-3">
                <ProductImage product={entry.product} className="h-14 w-14 rounded-lg" />
                <div className="min-w-0">
                  {recommended ? (
                    <div className="text-[11px] font-bold uppercase tracking-wide text-(--ink)">
                      {t(RECOMMENDED_LABEL)}
                    </div>
                  ) : null}
                  <ProductTitle
                    title={entry.product.title}
                    className="line-clamp-2 text-sm font-medium leading-snug"
                  />
                  <div className="flex items-center gap-2 text-sm">
                    <span className="font-semibold">{formatMoney(entry.product.price)}</span>
                    <Rating rating={entry.product.rating} count={entry.product.review_count} />
                  </div>
                </div>
              </div>
              <div>
                {entry.best_for ? (
                  <div className="rounded-md bg-(--well) px-2 py-1 text-[13px] text-(--ink)">
                    {t("Best for: {text}", { text: entry.best_for })}
                  </div>
                ) : null}
              </div>
              {pros.map((pro) => (
                <TermRow key={pro} sign="+" text={pro} />
              ))}
              {/* Pads keep a shorter pros list from pulling its cons up. */}
              {Array.from({ length: maxPros - pros.length }, (_, index) => (
                <div key={`pro-pad-${index}`} className="hidden sm:block" aria-hidden />
              ))}
              {cons.map((con) => (
                <TermRow key={con} sign="−" text={con} />
              ))}
              {Array.from({ length: maxCons - cons.length }, (_, index) => (
                <div key={`con-pad-${index}`} className="hidden sm:block" aria-hidden />
              ))}
            </div>
          );
        })}
        {partial ? (
          <div style={cardRows} className="ac-skeleton h-36 rounded-xl sm:[grid-row:var(--cmp-rows)]" />
        ) : null}
      </div>
      {delta ? (
        <p className="mt-3 text-[13px] text-(--ink)">
          {rich(t("Price difference: {amount} {range}"), {
            amount: <span className="font-semibold">{formatMoney(delta.amount)}</span>,
            range: (
              <span className="text-(--ink-soft)">
                {t("({low} vs {high})", { low: formatMoney(delta.low_price), high: formatMoney(delta.high_price) })}
              </span>
            ),
          })}
        </p>
      ) : null}
      {payload.dimensions?.length ? (
        <p className="mt-3 text-xs text-(--ink-soft)/80">{t("Compared on: {dimensions}", { dimensions: payload.dimensions.join(" · ") })}</p>
      ) : null}
    </section>
  );
}
