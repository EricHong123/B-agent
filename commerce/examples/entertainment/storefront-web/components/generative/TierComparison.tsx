// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import type { CSSProperties } from "react";
import { formatMoney, useT } from "web-shared";
import { scarcityLine, statusPill } from "@/lib/format";
import type { ComparisonPayload } from "@/lib/types";
import { Rich } from "@/lib/i18n-helpers";
import { AllInPrice, Pill, RECOMMENDED_LABEL, Stub } from "./shared";

const RIBBON_PAIR_QTY = 2;

interface DeltaRibbon {
  cheaperLabel: string;
  pricierLabel: string;
  perTicket: number;
  cheaperIsLeft: boolean;
}

/** Recommended vs cheapest; the two cheapest when nothing is recommended. */
function deltaRibbon(
  shown: ComparisonPayload["entries"],
  recommendedId: string | null | undefined,
): DeltaRibbon | null {
  const entries = shown.filter((entry) => entry.product.price > 0);
  if (entries.length < 2) return null;
  const byPrice = [...entries].sort((a, b) => a.product.price - b.product.price);
  const cheapest = byPrice[0];
  const recommended = recommendedId
    ? entries.find((entry) => entry.product_id === recommendedId)
    : undefined;
  const pricier = recommended && recommended !== cheapest ? recommended : byPrice[1];
  const perTicket = pricier.product.price - cheapest.product.price;
  if (perTicket <= 0) return null;
  const label = (entry: (typeof entries)[number]) =>
    entry.product.attributes?.tier ?? entry.product.title;
  return {
    cheaperLabel: label(cheapest),
    pricierLabel: label(pricier),
    perTicket,
    cheaperIsLeft: entries.indexOf(cheapest) < entries.indexOf(pricier),
  };
}

/** The sign gets its own column so the text shares a left edge. */
function TermRow({ sign, text }: { sign: "+" | "−"; text: string }) {
  return (
    <div className="grid grid-cols-[1.1rem_1fr] text-[14px] leading-normal text-(--ink)">
      <span
        aria-hidden
        className={`font-bold ${sign === "+" ? "text-(--ok)" : "text-(--ink-soft)"}`}
      >
        {sign === "+" ? "✓" : "−"}
      </span>
      <span>{text}</span>
    </div>
  );
}

export default function TierComparison({
  payload,
  partial,
}: {
  payload: ComparisonPayload;
  partial?: boolean;
}) {
  const t = useT();
  const entries = (payload.entries ?? []).slice(0, 4);
  // Computed from the entries shown, so the ribbon cannot cite a clipped card.
  const ribbon = deltaRibbon(entries, payload.recommended_product_id);
  const columns = Math.min(Math.max(entries.length + (partial ? 1 : 0), 1), 4);
  const maxPros = Math.max(0, ...entries.map((entry) => (entry.pros ?? []).length));
  const maxCons = Math.max(0, ...entries.map((entry) => (entry.cons ?? []).length));
  // 5 shared header rows (tag, name, price, status, best-for) + the padded terms.
  const cardRows = { "--tc-rows": `span ${5 + maxPros + maxCons}` } as CSSProperties;

  return (
    <Stub component="comparison" label={payload.title ?? t("Tier comparison")}>
      <div
        className="grid grid-cols-1 gap-2.5 sm:grid-cols-2 lg:[grid-template-columns:repeat(var(--tc-cols),minmax(0,1fr))]"
        style={{ "--tc-cols": columns } as CSSProperties}
      >
        {entries.map((entry) => {
          const recommended = payload.recommended_product_id === entry.product_id;
          const attrs = entry.product.attributes ?? {};
          const scarce = scarcityLine(entry.product, t);
          const pros = entry.pros ?? [];
          const cons = entry.cons ?? [];
          return (
            <div
              key={entry.product_id}
              style={cardRows}
              className={`at-reveal-item grid content-start gap-1.5 rounded-(--radius) border p-4 sm:grid-rows-subgrid sm:[grid-row:var(--tc-rows)] ${
                recommended
                  ? "border-(--accent)/70 bg-(--accent-soft)"
                  : "border-(--line) bg-(--well)/40"
              }`}
            >
              <div className="min-h-[20px]">
                {recommended ? (
                  <span className="at-pill at-pill--accent">{t(RECOMMENDED_LABEL)}</span>
                ) : null}
              </div>
              <h4 className="at-display text-[17px] uppercase leading-tight text-(--ink)">
                {attrs.tier ?? entry.product.title}
              </h4>
              <div className="self-end">
                <AllInPrice price={entry.product.price} currency={entry.product.currency} size="xl" />
              </div>
              <div className="flex flex-wrap items-center gap-1.5">
                <Pill pill={statusPill(entry.product)} />
                {scarce ? (
                  <span className="at-mono text-[11px] font-semibold text-(--warn)">
                    {scarce}
                  </span>
                ) : null}
              </div>
              <div>
                {entry.best_for ? (
                  <p className="rounded bg-(--card) px-2 py-1 text-[13px] leading-snug text-(--ink)">
                    {t("Best for: {text}", { text: entry.best_for })}
                  </p>
                ) : null}
              </div>
              {pros.map((pro) => (
                <TermRow key={pro} sign="+" text={pro} />
              ))}
              {/* Invisible pads keep a shorter pros list from pulling its cons up. */}
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
          // Exact-size skeleton: a tier-card-shaped column.
          <div
            style={cardRows}
            className="flex flex-col gap-2 rounded-(--radius) border border-(--line) p-4 sm:[grid-row:var(--tc-rows)]"
          >
            <div className="at-skeleton h-5 w-4/5" />
            <div className="at-skeleton h-6 w-3/5" />
            <div className="at-skeleton h-3 w-full" />
            <div className="at-skeleton h-3 w-2/3" />
          </div>
        ) : null}
      </div>
      {!partial && ribbon ? (
        <div className="at-reveal mt-2.5 flex flex-wrap items-center justify-center gap-x-2 gap-y-1 rounded-(--radius) border border-(--line) bg-(--well)/60 px-3 py-2">
          <span aria-hidden className="at-mono text-[13px] font-bold text-(--ok)">
            {ribbon.cheaperIsLeft ? "←" : "→"}
          </span>
          <span className="text-[13px] leading-snug text-(--ink)">
            <Rich
              text="{cheaper} saves {delta} per ticket · {pair} for a pair vs {pricier}"
              vars={{
                cheaper: <b>{ribbon.cheaperLabel}</b>,
                delta: <span className="at-mono font-bold">Δ {formatMoney(ribbon.perTicket)}</span>,
                pair: (
                  <span className="at-mono font-bold">
                    {formatMoney(ribbon.perTicket * RIBBON_PAIR_QTY)}
                  </span>
                ),
                pricier: ribbon.pricierLabel,
              }}
            />
          </span>
        </div>
      ) : null}
      {payload.dimensions?.length ? (
        <p className="at-eyebrow mt-3 !text-[12px] !normal-case !tracking-normal">
          {t("Compared on: {dimensions}", { dimensions: payload.dimensions.join(" · ") })}
        </p>
      ) : null}
    </Stub>
  );
}
