// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import type { CSSProperties } from "react";
import { useLocale, useT } from "web-shared";
import { formatPrice, productPlace, productPriceUnit } from "@/lib/format";
import type { Product } from "@/lib/types";
import { PostcardWindow } from "../PostcardWindow";

// --- Typography + surface helpers (token layer lives in globals.css :root) ---

export const DISPLAY = "var(--font-display), 'Fraunces', Georgia, serif";
export const BODY = "var(--font-body), 'Archivo', ui-sans-serif, system-ui, sans-serif";

export function display(px: number, weight = 600, italic = false): CSSProperties {
  return {
    fontFamily: DISPLAY,
    fontSize: px,
    fontWeight: weight,
    fontStyle: italic ? "italic" : "normal",
    color: "var(--ink)",
    lineHeight: 1.15,
  };
}

export const META: CSSProperties = {
  fontFamily: BODY,
  fontSize: 12,
  fontWeight: 600,
  textTransform: "uppercase",
  letterSpacing: "0.08em",
  color: "var(--ink-soft)",
};

export const CARD: CSSProperties = {
  background: "var(--surface)",
  border: "1px solid var(--line)",
  borderRadius: "var(--radius-lg)",
  boxShadow: "var(--shadow)",
};

export const HOVER_LIFT =
  "transition-[transform,box-shadow] duration-[180ms] ease-out hover:-translate-y-[2px] hover:shadow-[0_10px_32px_rgba(31,61,51,0.14)]";

// --- Date-aware stay signals (attributes stamped by examples/travel/api) ---

const WEEKDAYS = ["Sunday", "Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday"];

export interface DateFlexCell {
  iso: string;
  day: number;
  weekday: string;
  rate: number;
  chosen: boolean;
}

/** Stamp format "2026-10-14:189|2026-10-15*:214|…"; Date.UTC keeps the weekday timezone-stable. */
function parseDateFlex(raw?: string): DateFlexCell[] | null {
  if (!raw) return null;
  const cells: DateFlexCell[] = [];
  for (const cell of raw.split("|")) {
    const match = /^(\d{4})-(\d{2})-(\d{2})(\*?):(\d+)$/.exec(cell);
    if (!match) return null;
    const [, year, month, day, chosen, rate] = match;
    const utc = new Date(Date.UTC(Number(year), Number(month) - 1, Number(day)));
    cells.push({
      iso: `${year}-${month}-${day}`,
      day: Number(day),
      weekday: WEEKDAYS[utc.getUTCDay()],
      rate: Number(rate),
      chosen: chosen === "*",
    });
  }
  return cells.length >= 3 && cells.some((cell) => cell.chosen) ? cells : null;
}

export function DateFlexStrip({ raw }: { raw?: string }) {
  const { locale, t } = useLocale();
  const cells = parseDateFlex(raw);
  if (!cells) return null;
  const cheapest = Math.min(...cells.map((cell) => cell.rate));
  const chosen = cells.find((cell) => cell.chosen);
  const bestCell = cells.find((cell) => cell.rate === cheapest);
  const savings = chosen && bestCell && !bestCell.chosen ? chosen.rate - cheapest : 0;
  return (
    <div className="mt-1.5">
      <div className="flex gap-[3px]">
        {cells.map((cell) => {
          const tinted = cell.rate === cheapest;
          return (
            <span
              key={cell.iso}
              title={t("{day}: ${rate}/night", { day: t(cell.weekday), rate: cell.rate })}
              className="flex min-w-0 flex-1 flex-col items-center rounded-md py-1"
              style={{
                fontFamily: BODY,
                background: tinted ? "var(--accent-soft)" : "var(--well)",
                boxShadow: cell.chosen ? "inset 0 0 0 1.5px var(--ink)" : undefined,
              }}
            >
              <span style={{ fontSize: 11, fontWeight: 600, color: "var(--ink-soft)" }}>
                {locale === "zh" ? t(cell.weekday).slice(-1) : cell.weekday[0]}
                <span style={{ fontWeight: 400 }}>{cell.day}</span>
              </span>
              <span
                style={{
                  fontSize: 11,
                  fontWeight: tinted || cell.chosen ? 700 : 500,
                  color: tinted ? "var(--accent)" : "var(--ink)",
                }}
              >
                ${cell.rate}
              </span>
            </span>
          );
        })}
      </div>
      {savings >= 15 && bestCell ? (
        <p className="mt-1" style={{ fontFamily: BODY, fontSize: 11, fontWeight: 600, color: "var(--accent)" }}>
          {t("Save ${savings} by arriving {day}", { savings, day: t(bestCell.weekday) })}
        </p>
      ) : null}
    </div>
  );
}

export interface RatePosition {
  low: number;
  high: number;
  position: "lower" | "typical" | "higher";
}

/** Band format: "225-285". */
function ratePosition(price: number, band?: string): RatePosition | null {
  const match = /^(\d+)-(\d+)$/.exec(band ?? "");
  if (!match) return null;
  const low = Number(match[1]);
  const high = Number(match[2]);
  if (low <= 0 || high <= low) return null;
  return { low, high, position: price < low ? "lower" : price > high ? "higher" : "typical" };
}

const RATE_POSITION_LABELS: Record<RatePosition["position"], string> = {
  lower: "Lower than typical",
  typical: "Typical rate",
  higher: "Above typical",
};

export function RateGauge({ price, band }: { price: number; band?: string }) {
  const t = useT();
  const parsed = ratePosition(price, band);
  if (!parsed) return null;
  const span = parsed.high - parsed.low;
  const min = parsed.low - span / 2;
  const max = parsed.high + span / 2;
  const percent = Math.max(3, Math.min(97, ((price - min) / (max - min)) * 100));
  const lower = parsed.position === "lower";
  return (
    <div className="mt-1 flex items-center gap-2">
      <span
        aria-hidden
        className="relative h-[5px] w-[72px] shrink-0 overflow-visible rounded-full"
        style={{
          // A half-span margin each side of the band.
          background:
            "linear-gradient(90deg, var(--well) 0 25%, rgba(31,61,51,0.16) 25% 75%, var(--well) 75% 100%)",
        }}
      >
        <span
          className="absolute top-1/2 h-[9px] w-[9px] -translate-x-1/2 -translate-y-1/2 rounded-full"
          style={{
            left: `${percent}%`,
            background: lower ? "var(--accent)" : "var(--ink)",
            boxShadow: "0 0 0 1.5px var(--surface)",
          }}
        />
      </span>
      <span
        style={{
          fontFamily: BODY,
          fontSize: 11,
          fontWeight: 600,
          color: lower ? "var(--accent)" : "var(--ink-soft)",
        }}
      >
        {t(RATE_POSITION_LABELS[parsed.position])}
      </span>
    </div>
  );
}

export function ScarcityChip({ unitsLeft }: { unitsLeft?: string }) {
  const t = useT();
  const count = Number(unitsLeft);
  if (!unitsLeft || !Number.isInteger(count) || count < 1) return null;
  return (
    <span
      className="rounded-full px-2 py-0.5"
      style={{
        fontFamily: BODY,
        fontSize: 11,
        fontWeight: 600,
        color: "var(--ink)",
        border: "1px solid var(--line)",
        background: "var(--surface)",
      }}
    >
      {t("{n} left for your dates", { n: count })}
    </span>
  );
}

// --- Small shared pieces ---

export function Stars({ rating, count }: { rating?: number | null; count?: number | null }) {
  if (rating == null) return null;
  return (
    <span style={{ fontFamily: BODY, fontSize: 13, color: "var(--ink-soft)", whiteSpace: "nowrap" }}>
      <span aria-hidden style={{ color: "var(--star)" }}>
        ★
      </span>{" "}
      {rating.toFixed(1)}
      {count ? ` (${count.toLocaleString()})` : ""}
    </span>
  );
}

export function MiniProductCard({ product }: { product: Product }) {
  const t = useT();
  const unit = productPriceUnit(product, t);
  return (
    <div
      className={`flex shrink-0 items-center gap-2.5 p-2 pr-3 ${HOVER_LIFT}`}
      style={{
        background: "var(--surface)",
        border: "1px solid var(--line)",
        borderRadius: "var(--radius)",
      }}
    >
      <PostcardWindow
        city={productPlace(product)}
        title={product.title}
        className="h-[60px] w-[96px] shrink-0 overflow-hidden rounded-lg"
      />
      <div className="min-w-0">
        <div
          className="line-clamp-2 max-w-[200px]"
          style={{ fontFamily: BODY, fontSize: 15, fontWeight: 600, color: "var(--ink)", lineHeight: 1.3 }}
        >
          {product.title}
        </div>
        <div className="mt-0.5 flex items-baseline gap-1.5">
          <span style={{ fontFamily: DISPLAY, fontSize: 16, fontWeight: 700, color: "var(--ink)" }}>
            {formatPrice(product.price)}
          </span>
          {unit ? <span style={{ ...META, fontSize: 11 }}>{unit}</span> : null}
          {product.rating ? (
            <span style={{ ...META, fontSize: 11, color: "var(--star)" }}>★ {product.rating}</span>
          ) : null}
        </div>
      </div>
    </div>
  );
}
