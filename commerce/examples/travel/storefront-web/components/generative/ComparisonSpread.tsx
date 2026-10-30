// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import type { CSSProperties } from "react";
import { type Translate, useT } from "web-shared";
import {
  formatPrice,
  priceUnitLabel,
  productPlace,
  productPriceUnit,
  shortDate,
} from "@/lib/format";
import type { ComparisonPayload, Product } from "@/lib/types";
import { PostcardWindow } from "../PostcardWindow";
import {
  BODY,
  CARD,
  DISPLAY,
  META,
  RateGauge,
  Stars,
  display,
} from "./shared";

const RECOMMENDED_LABEL = "Recommended";

function TermRow({ kind, text }: { kind: "pro" | "con"; text?: string }) {
  if (!text) return <div aria-hidden />;
  return (
    <div
      className="grid grid-cols-[1.1rem_1fr]"
      style={{ fontFamily: BODY, fontSize: 14, lineHeight: 1.45, color: "var(--ink)" }}
    >
      <span
        aria-hidden
        style={{ color: kind === "pro" ? "var(--accent)" : "var(--ink-soft)" }}
      >
        {kind === "pro" ? "✓" : "–"}
      </span>
      <span>{text}</span>
    </div>
  );
}

// --- Attribute matrix -------------------------------------------------------

// Catalog keys that are plumbing or already rendered elsewhere on the column.
const MATRIX_HIDDEN = new Set([
  "price_unit",
  "availability_from",
  "availability_to",
  "date_flex",
  "typical_rate_band",
  "units_left_for_dates",
  // Folded into the Refundable row as its "until …" detail.
  "free_cancellation_until",
]);

const MATRIX_LABELS: Record<string, string> = {
  refundable: "Refundable",
  room_type: "Room",
  breakfast_included: "Breakfast",
  neighborhood: "Neighborhood",
  city: "City",
  origin_city: "From",
  destination_city: "To",
  cabin: "Cabin",
  departure_time_local: "Departure",
  duration: "Duration",
  duration_hours: "Duration",
  group_size_max: "Group size",
};

// Refundability leads (it's the travel decision), places close.
const MATRIX_ORDER = [
  "refundable",
  "room_type",
  "cabin",
  "breakfast_included",
  "duration",
  "duration_hours",
  "departure_time_local",
  "group_size_max",
  "neighborhood",
  "city",
];

const MAX_MATRIX_ROWS = 6;

function matrixLabel(key: string, t: Translate): string {
  const mapped = MATRIX_LABELS[key];
  if (mapped) return t(mapped);
  const spaced = key.replace(/_/g, " ");
  return t(spaced.charAt(0).toUpperCase() + spaced.slice(1));
}

type MatrixCell =
  | { kind: "yes"; detail?: string }
  | { kind: "no" }
  | { kind: "value"; text: string };

function matrixCell(product: Product, key: string, t: Translate): MatrixCell {
  const raw = product.attributes?.[key];
  if (raw == null) return { kind: "no" };
  if (key === "refundable") {
    if (!/^(yes|true)$/i.test(raw)) return { kind: "no" };
    const until = shortDate(product.attributes?.free_cancellation_until);
    return { kind: "yes", detail: until ? t("until {date}", { date: until }) : undefined };
  }
  if (/^(yes|true)$/i.test(raw)) return { kind: "yes" };
  if (/^(no|false|none)$/i.test(raw)) return { kind: "no" };
  if (key === "duration_hours") return { kind: "value", text: t("{n} hrs", { n: raw }) };
  return { kind: "value", text: raw };
}

function matrixKeys(products: Product[]): string[] {
  const seen: string[] = [];
  for (const product of products) {
    for (const key of Object.keys(product.attributes ?? {})) {
      if (!MATRIX_HIDDEN.has(key) && !seen.includes(key)) seen.push(key);
    }
  }
  seen.sort((a, b) => {
    const ai = MATRIX_ORDER.indexOf(a);
    const bi = MATRIX_ORDER.indexOf(b);
    return (ai < 0 ? MATRIX_ORDER.length : ai) - (bi < 0 ? MATRIX_ORDER.length : bi);
  });
  return seen.slice(0, MAX_MATRIX_ROWS);
}

function MatrixRow({ label, cell }: { label: string; cell: MatrixCell }) {
  return (
    <div className="flex items-baseline justify-between gap-2">
      <span style={{ ...META, fontSize: 11 }}>{label}</span>
      {cell.kind === "value" ? (
        <span
          className="text-right"
          style={{ fontFamily: BODY, fontSize: 13, fontWeight: 600, color: "var(--ink)" }}
        >
          {cell.text}
        </span>
      ) : (
        <span
          className="text-right"
          style={{
            fontFamily: BODY,
            fontSize: 13,
            fontWeight: 700,
            color: cell.kind === "yes" ? "var(--accent)" : "var(--ink-soft)",
          }}
        >
          {cell.kind === "yes" ? `✓${cell.detail ? ` ${cell.detail}` : ""}` : "–"}
        </span>
      )}
    </div>
  );
}

/** What the pricier entry has that the cheaper one lacks. */
function deltaBuys(high: Product, low: Product, keys: string[], t: Translate): string[] {
  const buys: string[] = [];
  for (const key of keys) {
    const highCell = matrixCell(high, key, t);
    const lowCell = matrixCell(low, key, t);
    if (highCell.kind === "yes" && lowCell.kind === "no") {
      buys.push(key === "refundable" ? t("full refundability") : matrixLabel(key, t).toLowerCase());
    } else if (
      highCell.kind === "value" &&
      (lowCell.kind !== "value" || lowCell.text !== highCell.text)
    ) {
      buys.push(highCell.text);
    }
  }
  return buys.slice(0, 3);
}

function SkeletonColumn({ first, rowSpan }: { first: boolean; rowSpan: number }) {
  return (
    <div
      className={`flex min-w-0 flex-col gap-2 pt-2.5 ${first ? "sm:pr-4" : "sm:border-l sm:px-4"} border-(--line)`}
      style={{ gridRow: `span ${rowSpan}` }}
      aria-hidden
    >
      <div className="h-4" />
      <div className="al-shimmer aspect-[16/10] w-full !rounded-[10px]" />
      <div className="al-shimmer h-4 w-4/5" />
      <div className="al-shimmer h-4 w-3/5" />
      <div className="al-shimmer h-3 w-full" />
      <div className="al-shimmer h-3 w-5/6" />
    </div>
  );
}

export default function ComparisonSpread({
  payload,
  partial,
}: {
  payload: ComparisonPayload;
  partial?: boolean;
}) {
  const t = useT();
  const entries = payload.entries ?? [];
  const skeletons = partial ? (entries.length === 0 ? 2 : entries.length < 4 ? 1 : 0) : 0;
  const columns = Math.max(1, Math.min(entries.length + skeletons, 4));

  // Fewer than two shared rows means the catalog is too thin here; use the pro/con terms.
  const keys = matrixKeys(entries.map((entry) => entry.product));
  const useMatrix = keys.length >= 2 && entries.length >= 2;
  const maxPros = useMatrix ? 0 : Math.max(0, ...entries.map((entry) => entry.pros?.length ?? 0));
  const maxCons = useMatrix ? 0 : Math.max(0, ...entries.map((entry) => entry.cons?.length ?? 0));
  // Six fixed rows (tag, postcard, title, price, gauge, quote), then the matrix or pro/con rows.
  const rowSpan = 6 + (useMatrix ? keys.length : maxPros + maxCons);

  const delta = payload.price_delta;
  const highEntry = delta
    ? entries.find((entry) => entry.product_id === delta.high_product_id)
    : undefined;
  const lowEntry = delta
    ? entries.find((entry) => entry.product_id === delta.low_product_id)
    : undefined;
  const buys =
    useMatrix && delta && highEntry && lowEntry
      ? deltaBuys(highEntry.product, lowEntry.product, keys, t)
      : [];
  const deltaUnit = highEntry ? priceUnitLabel(highEntry.product.attributes?.price_unit, t) : null;

  return (
    <section className="al-reveal" style={{ ...CARD, padding: 24 }}>
      {payload.title ? (
        <h3 className="mb-4" style={display(22, 600)}>
          {payload.title}
        </h3>
      ) : null}

      <div
        className="grid grid-cols-1 gap-y-2 sm:[grid-template-columns:var(--comp-cols)]"
        style={{ "--comp-cols": `repeat(${columns}, minmax(0, 1fr))` } as CSSProperties}
      >
        {entries.map((entry, i) => {
          const recommended = payload.recommended_product_id === entry.product_id;
          const product = entry.product;
          const unit = productPriceUnit(product, t);
          return (
            <div
              key={entry.product_id}
              className={`al-reveal-item grid min-w-0 gap-y-2 pt-2.5 [grid-template-rows:subgrid] ${
                i === 0 ? "sm:pr-4" : "max-sm:mt-4 max-sm:border-t max-sm:pt-4 sm:border-l sm:px-4"
              } border-(--line)`}
              style={{
                animationDelay: `${i * 70}ms`,
                gridRow: `span ${rowSpan}`,
                // The recommended accent rides an inset shadow, leaving border-top free for the
                // stacked-mobile hairline between columns.
                boxShadow: recommended ? "inset 0 3px 0 var(--accent)" : undefined,
              }}
            >
              {/* Fixed height keeps columns aligned without a tag. */}
              <div className="h-4">
                {recommended ? (
                  <span style={{ ...META, fontSize: 11, letterSpacing: "0.1em", color: "var(--accent)" }}>
                    ◈ {t(RECOMMENDED_LABEL)}
                  </span>
                ) : null}
              </div>

              <PostcardWindow
                city={productPlace(product)}
                title={product.title}
                className="aspect-[16/10] w-full overflow-hidden rounded-[10px]"
              />

              <div className="line-clamp-2" style={display(17, 600)}>
                {product.title}
              </div>
              <div className="flex flex-wrap items-baseline gap-x-2 gap-y-0.5">
                <span>
                  <span style={{ fontFamily: DISPLAY, fontSize: 16, fontWeight: 700, color: "var(--ink)" }}>
                    {formatPrice(product.price)}
                  </span>
                  {unit ? <span style={{ ...META, fontSize: 11, marginLeft: 3 }}>{unit}</span> : null}
                </span>
                <Stars rating={product.rating} count={product.review_count} />
              </div>

              {/* The empty slot keeps rows below aligned. */}
              {product.attributes?.typical_rate_band ? (
                <RateGauge price={product.price} band={product.attributes.typical_rate_band} />
              ) : (
                <div aria-hidden />
              )}

              {entry.best_for ? (
                <p
                  style={{
                    fontFamily: DISPLAY,
                    fontStyle: "italic",
                    fontWeight: 300,
                    fontSize: 14.5,
                    lineHeight: 1.45,
                    color: "var(--ink)",
                  }}
                >
                  <span
                    aria-hidden
                    style={{ color: "var(--accent)", fontStyle: "normal", fontWeight: 700, fontSize: 18 }}
                  >
                    “
                  </span>
                  {entry.best_for}
                </p>
              ) : (
                <div aria-hidden />
              )}

              {useMatrix
                ? keys.map((key) => (
                    <MatrixRow key={key} label={matrixLabel(key, t)} cell={matrixCell(product, key, t)} />
                  ))
                : [
                    // Padded to the longest column so the k-th pro / k-th con of every
                    // column share a baseline.
                    ...Array.from({ length: maxPros }, (_, k) => (
                      <TermRow key={`pro-${k}`} kind="pro" text={entry.pros?.[k]} />
                    )),
                    ...Array.from({ length: maxCons }, (_, k) => (
                      <TermRow key={`con-${k}`} kind="con" text={entry.cons?.[k]} />
                    )),
                  ]}
            </div>
          );
        })}
        {Array.from({ length: skeletons }, (_, i) => (
          <SkeletonColumn key={`skeleton-${i}`} first={entries.length + i === 0} rowSpan={rowSpan} />
        ))}
      </div>

      {delta && buys.length ? (
        <p
          className="mt-4 border-t pt-3 border-(--line)"
          style={{ fontFamily: BODY, fontSize: 14, color: "var(--ink)" }}
        >
          <span style={{ fontWeight: 700, color: "var(--accent)" }}>
            {deltaUnit
              ? t("+{amount} {unit} buys:", { amount: formatPrice(delta.amount), unit: deltaUnit })
              : t("+{amount} buys:", { amount: formatPrice(delta.amount) })}
          </span>{" "}
          {buys.join(" · ")}
        </p>
      ) : null}

      {payload.dimensions?.length ? (
        <p className="mt-4" style={{ ...META, fontSize: 12 }}>
          {t("Compared on: {dimensions}", { dimensions: payload.dimensions.join(" · ") })}
        </p>
      ) : null}
    </section>
  );
}
