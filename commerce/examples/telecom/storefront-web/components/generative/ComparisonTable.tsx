// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** Renders present_comparison for devices; plans use plan_matrix. */

import type { CSSProperties } from "react";
import { useT } from "web-shared";
import { formatPrice, formatPriceWithUnit, plateGlyph, plateTint } from "@/lib/format";
import type { ComparisonPayload } from "@/lib/types";
import { Frame, Rating } from "./shared";

const RECOMMENDED_LABEL = "Recommended";

/** The sign holds its own column so text shares a left edge. */
function TermRow({ sign, text }: { sign: "+" | "−"; text: string }) {
  return (
    <div className="grid grid-cols-[1.1rem_1fr] text-[14px] leading-normal text-(--ink)">
      <span
        aria-hidden
        className={`am-mono font-bold ${sign === "+" ? "am-tick" : "text-(--ink-soft)"}`}
      >
        {sign}
      </span>
      <span>{text}</span>
    </div>
  );
}

export default function ComparisonTable({
  payload,
  partial,
}: {
  payload: ComparisonPayload;
  partial?: boolean;
}) {
  const t = useT();
  const recommended = payload.recommended_product_id;
  const entries = payload.entries ?? [];
  const delta = payload.price_delta;
  const columns = entries.length + (partial ? 1 : 0);
  // Each pro/con line is a subgrid row, padded to the longest list, so rows align across cards.
  const maxPros = Math.max(0, ...entries.map((entry) => (entry.pros ?? []).length));
  const maxCons = Math.max(0, ...entries.map((entry) => (entry.cons ?? []).length));
  const cardRows = { "--cmp-rows": `span ${3 + maxPros + maxCons}` } as CSSProperties;
  return (
    <Frame
      component="comparison"
      label={payload.title ?? t("Side by side")}
      flush
    >
      <div className={`grid gap-px bg-(--line) ${columns > 2 ? "sm:grid-cols-3" : "sm:grid-cols-2"}`}>
        {entries.map(({ product, pros, cons, best_for }, index) => {
          const isRec = product.product_id === recommended;
          const prosList = pros ?? [];
          const consList = cons ?? [];
          return (
            <article
              key={product.product_id}
              className={`am-reveal-item relative grid content-start gap-2 bg-(--surface) p-4 sm:grid-rows-subgrid sm:[grid-row:var(--cmp-rows)] ${
                isRec ? "outline outline-1 -outline-offset-1 outline-(--accent)" : ""
              }`}
              style={{ ...cardRows, animationDelay: `${index * 80}ms` }}
            >
              {isRec ? (
                <span className="am-tag am-tag--accent absolute right-3 top-3 z-10">
                  ✓ {t(RECOMMENDED_LABEL)}
                </span>
              ) : null}
              <div className="am-plate relative h-[72px] w-full">
                <div className="absolute inset-0" style={{ background: plateTint(product) }} aria-hidden />
                <span className="am-plate-glyph" style={{ fontSize: 28 }}>
                  {plateGlyph(product)}
                </span>
              </div>
              <div>
                <h3 className="text-[15px] font-bold leading-tight text-(--ink)">
                  {product.title}
                </h3>
                <div className="mt-0.5 flex items-baseline justify-between gap-2">
                  <span className="am-mono text-[15px] font-semibold text-(--ink)">
                    {formatPriceWithUnit(product)}
                  </span>
                  <Rating rating={product.rating} count={product.review_count} />
                </div>
              </div>
              {prosList.map((pro) => (
                <TermRow key={pro} sign="+" text={pro} />
              ))}
              {/* Pads keep a shorter pros list from pulling its cons up. */}
              {Array.from({ length: maxPros - prosList.length }, (_, padIndex) => (
                <div key={`pro-pad-${padIndex}`} className="hidden sm:block" aria-hidden />
              ))}
              {consList.map((con) => (
                <TermRow key={con} sign="−" text={con} />
              ))}
              {Array.from({ length: maxCons - consList.length }, (_, padIndex) => (
                <div key={`con-pad-${padIndex}`} className="hidden sm:block" aria-hidden />
              ))}
              <div className="self-end">
                {best_for ? (
                  <p className="am-rule pt-2 text-[13px] font-medium text-(--ink-soft)">
                    {t("Best for: ")}<span className="text-(--ink)">{best_for}</span>
                  </p>
                ) : null}
              </div>
            </article>
          );
        })}
        {partial ? (
          <div
            style={cardRows}
            className="flex flex-col gap-2 bg-(--surface) p-4 sm:[grid-row:var(--cmp-rows)]"
          >
            <div className="am-shimmer h-[72px] w-full" />
            <div className="am-shimmer h-4 w-3/4" />
            <div className="am-shimmer h-3 w-1/2" />
            <div className="am-shimmer h-3 w-2/3" />
          </div>
        ) : null}
      </div>
      {delta || payload.dimensions?.length ? (
        <div className="border-t border-(--line) px-4 py-2.5">
          {delta ? (
            <p className="text-[13px] text-(--ink)">
              {t("Price difference: ")}
              <span className="am-mono font-semibold">{formatPrice(delta.amount)}</span>{" "}
              <span className="am-mono text-(--ink-soft)">
                {t("({low} vs {high})", { low: formatPrice(delta.low_price), high: formatPrice(delta.high_price) })}
              </span>
            </p>
          ) : null}
          {payload.dimensions?.length ? (
            <p className="mt-0.5 text-[12px] text-(--ink-soft)">
              {t("Compared on: {dimensions}", { dimensions: payload.dimensions.join(" · ") })}
            </p>
          ) : null}
        </div>
      ) : null}
    </Frame>
  );
}
