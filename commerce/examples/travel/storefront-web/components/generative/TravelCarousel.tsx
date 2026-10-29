// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { type CSSProperties, useCallback, useEffect, useRef, useState } from "react";
import { type Translate, useT } from "web-shared";
import { formatPrice, productCity, productPlace, productPriceUnit } from "@/lib/format";
import type { Product, ProductsPayload } from "@/lib/types";
import { PostcardWindow } from "../PostcardWindow";
import {
  BODY,
  CARD,
  DISPLAY,
  DateFlexStrip,
  HOVER_LIFT,
  META,
  RateGauge,
  ScarcityChip,
  Stars,
  display,
} from "./shared";

const HIDDEN_ATTRS = new Set([
  "city",
  "destination_city",
  // The postcard window already shows the neighborhood.
  "neighborhood",
  "price_unit",
  "availability_from",
  "availability_to",
  // Rendered by the strip, gauge, and scarcity chip instead.
  "date_flex",
  "typical_rate_band",
  "units_left_for_dates",
]);

function specChips(product: Product, t: Translate): string[] {
  return Object.entries(product.attributes ?? {})
    .filter(([key]) => !HIDDEN_ATTRS.has(key) && !/cancel|refund/i.test(key))
    .map(([key, value]) => {
      if (/^(yes|true)$/i.test(value)) return t(key.replace(/_/g, " ").replace(/\bincluded\b/, "incl."));
      if (/^(no|false)$/i.test(value)) return null;
      if (key === "duration_hours") return t("{n} hrs", { n: value });
      if (key === "group_size_max") return t("groups of {n}", { n: value });
      return value;
    })
    .filter((chip): chip is string => Boolean(chip))
    .slice(0, 3);
}

function hasFreeCancellation(product: Product): boolean {
  if (product.labels?.some((label) => /free.?cancel/i.test(label))) return true;
  return Object.entries(product.attributes ?? {}).some(
    ([key, value]) => /cancel|refund/i.test(key) && /free|yes|true|full/i.test(value),
  );
}

const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"];

/** From the string parts, so no timezone shifts the day. */
function cancellationDeadline(product: Product): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(
    product.attributes?.free_cancellation_until ?? "",
  );
  if (!match) return null;
  const month = MONTHS[Number(match[2]) - 1];
  return month ? `${month} ${Number(match[3])}` : null;
}

function isNonRefundable(product: Product): boolean {
  if (hasFreeCancellation(product)) return false;
  return Object.entries(product.attributes ?? {}).some(
    ([key, value]) => /cancel|refund/i.test(key) && /^(no|false|none)$/i.test(value.trim()),
  );
}

function SoldOutBand() {
  const t = useT();
  return (
    <span
      className="absolute inset-x-0 top-1/2 z-10 -translate-y-1/2 py-1.5 text-center"
      style={{ ...META, fontSize: 11, color: "var(--surface)", background: "rgba(31,61,51,0.82)" }}
    >
      {t("Sold out for these dates")}
    </span>
  );
}

export function TravelCard({
  product,
  reason,
  horizontal = false,
  className = "",
  style,
}: {
  product: Product;
  reason?: string | null;
  horizontal?: boolean;
  className?: string;
  style?: CSSProperties;
}) {
  const t = useT();
  const city = productCity(product);
  const unit = productPriceUnit(product, t);
  const chips = specChips(product, t);
  const soldOut = product.in_stock === false;
  const deadline = cancellationDeadline(product);

  const window_ = (
    <div className={`relative ${horizontal ? "w-36 shrink-0 self-stretch" : ""}`}>
      <PostcardWindow
        city={productPlace(product)}
        title={product.title}
        className={horizontal ? "h-full min-h-[90px] w-full" : "aspect-[16/10] w-full"}
      />
      {soldOut ? <SoldOutBand /> : null}
    </div>
  );

  const body = (
    <div className="flex min-w-0 flex-1 flex-col gap-1.5 p-3">
      <div className="line-clamp-2" style={display(18, 600)}>
        {product.title}
      </div>
      <div className="line-clamp-1" style={META}>
        {[product.brand, city].filter(Boolean).join(" · ")}
      </div>
      {chips.length ||
      hasFreeCancellation(product) ||
      isNonRefundable(product) ||
      product.attributes?.units_left_for_dates ? (
        <div className="flex flex-wrap items-center gap-1.5">
          {chips.map((chip) => (
            <span
              key={chip}
              className="rounded-full px-2 py-0.5"
              style={{
                fontFamily: BODY,
                fontSize: 11,
                color: "var(--ink-soft)",
                background: "var(--well)",
              }}
            >
              {chip}
            </span>
          ))}
          {hasFreeCancellation(product) ? (
            <span
              className="rounded-full px-2 py-0.5"
              style={{
                fontFamily: BODY,
                fontSize: 11,
                fontWeight: 600,
                color: "var(--accent)",
                background: "var(--accent-soft)",
              }}
            >
              {deadline ? t("✓ Free cancellation until {date}", { date: deadline }) : t("✓ Free cancellation")}
            </span>
          ) : isNonRefundable(product) ? (
            <span
              className="rounded-full px-2 py-0.5"
              style={{
                fontFamily: BODY,
                fontSize: 11,
                fontWeight: 600,
                color: "var(--ink-soft)",
                background: "var(--well)",
              }}
            >
              {t("Non-refundable")}
            </span>
          ) : null}
          <ScarcityChip unitsLeft={product.attributes?.units_left_for_dates} />
        </div>
      ) : null}
      <div className="mt-auto flex flex-wrap items-end justify-between gap-x-2 gap-y-0.5 pt-1">
        <Stars rating={product.rating} count={product.review_count} />
        <span className="ml-auto whitespace-nowrap text-right">
          <span style={{ fontFamily: DISPLAY, fontSize: 18, fontWeight: 700, color: "var(--accent)" }}>
            {formatPrice(product.price)}
          </span>
          {unit ? (
            <span style={{ ...META, fontSize: 11, marginLeft: 3 }}>
              {t("{unit} · all-in", { unit })}
            </span>
          ) : null}
        </span>
      </div>
      <RateGauge price={product.price} band={product.attributes?.typical_rate_band} />
      <DateFlexStrip raw={product.attributes?.date_flex} />
      {reason ? (
        <p
          style={{
            fontFamily: DISPLAY,
            fontStyle: "italic",
            fontWeight: 300,
            fontSize: 13,
            lineHeight: 1.45,
            color: "var(--ink-soft)",
          }}
        >
          {reason}
        </p>
      ) : null}
    </div>
  );

  return (
    <div
      className={`flex overflow-hidden ${horizontal ? "flex-row" : "flex-col"} ${HOVER_LIFT} ${className}`}
      style={{
        background: "var(--surface)",
        border: "1px solid var(--line)",
        borderRadius: "var(--radius)",
        boxShadow: "0 1px 3px rgba(31,61,51,0.06)",
        ...style,
      }}
    >
      {window_}
      {body}
    </div>
  );
}

/** Sized to match TravelCard so streaming does not reflow. */
function SkeletonCard({ horizontal = false }: { horizontal?: boolean }) {
  return (
    <div
      className={`flex overflow-hidden ${horizontal ? "w-full flex-row" : "w-60 shrink-0 flex-col"}`}
      style={{
        background: "var(--surface)",
        border: "1px solid var(--line)",
        borderRadius: "var(--radius)",
        boxShadow: "0 1px 3px rgba(31,61,51,0.06)",
      }}
      aria-hidden
    >
      <div
        className={`al-shimmer !rounded-none ${horizontal ? "w-36 shrink-0 self-stretch" : "aspect-[16/10] w-full"}`}
      />
      <div className="flex min-w-0 flex-1 flex-col gap-2 p-3">
        <div className="al-shimmer h-[18px] w-4/5" />
        <div className="al-shimmer h-3 w-3/5" />
        <div className="al-shimmer h-5 w-2/5" />
        <div className="mt-auto flex items-end justify-between gap-2 pt-1">
          <div className="al-shimmer h-3 w-12" />
          <div className="al-shimmer h-5 w-16" />
        </div>
      </div>
    </div>
  );
}

export default function TravelCarousel({
  payload,
  partial,
}: {
  payload: ProductsPayload;
  partial?: boolean;
}) {
  const layout = payload.layout ?? "carousel";
  const items = payload.items ?? [];

  // A right-edge fade and chevron show whenever more cards sit off-screen.
  const scrollerRef = useRef<HTMLDivElement>(null);
  const [moreRight, setMoreRight] = useState(false);
  const updateFade = useCallback(() => {
    const el = scrollerRef.current;
    if (!el) return;
    setMoreRight(el.scrollWidth - el.clientWidth - el.scrollLeft > 12);
  }, []);
  useEffect(() => {
    // Re-measure whenever the row's content changes (streaming adds cards).
    void items.length;
    void partial;
    updateFade();
    window.addEventListener("resize", updateFade);
    return () => window.removeEventListener("resize", updateFade);
  }, [items.length, partial, updateFade]);

  return (
    <section className="al-reveal" style={{ ...CARD, padding: 20 }}>
      {payload.title ? (
        <h3 className="mb-3" style={display(22, 600)}>
          {payload.title}
        </h3>
      ) : null}
      <div className="relative">
        <div
          ref={scrollerRef}
          onScroll={updateFade}
          className={
            layout === "grid"
              ? "grid grid-cols-2 gap-3 sm:grid-cols-3"
              : layout === "list"
                ? "flex flex-col gap-3"
                : "flex gap-3 overflow-x-auto pb-1"
          }
        >
          {items.map(({ product, reason }, i) => (
            <TravelCard
              key={product.product_id}
              product={product}
              reason={reason}
              horizontal={layout === "list"}
              className={layout === "carousel" ? "al-reveal-item w-60 shrink-0" : "al-reveal-item"}
              style={{ animationDelay: `${i * 70}ms` }}
            />
          ))}
          {partial ? <SkeletonCard horizontal={layout === "list"} /> : null}
        </div>
        {layout === "carousel" && moreRight ? (
          <div
            aria-hidden
            className="pointer-events-none absolute inset-y-0 right-0 flex w-16 items-center justify-end pb-1"
            style={{ background: "linear-gradient(90deg, transparent, var(--surface) 80%)" }}
          >
            <span style={{ fontFamily: DISPLAY, fontSize: 24, color: "var(--ink-soft)" }}>›</span>
          </div>
        ) : null}
      </div>
    </section>
  );
}
