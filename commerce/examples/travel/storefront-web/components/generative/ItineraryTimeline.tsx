// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useT } from "web-shared";
import { formatPrice } from "@/lib/format";
import type { ItineraryPayload } from "@/lib/types";
import { CARD, DISPLAY, META, display } from "./shared";
import { TravelCard } from "./TravelCarousel";

/** travel_dates is free text: "2026-09-14 to 2026-09-17", "Oct 12 to Oct 16", "12-16 Oct", or no range. */
function parseNights(travelDates?: string): number | null {
  if (!travelDates) return null;
  const isoDates = travelDates.match(/\d{4}-\d{2}-\d{2}/g);
  if (isoDates && isoDates.length >= 2) {
    const nights = Math.round(
      (Date.parse(isoDates[1]) - Date.parse(isoDates[0])) / 86_400_000,
    );
    return nights > 0 && nights <= 30 ? nights : null;
  }
  const dayPair = /(\d{1,2})(?:\s+[A-Za-z]+)?\s*[–—-]\s*(?:[A-Za-z]+\s+)*(\d{1,2})/.exec(
    travelDates,
  );
  if (dayPair) {
    const nights = Number(dayPair[2]) - Number(dayPair[1]);
    return nights > 0 && nights <= 30 ? nights : null;
  }
  return null;
}

export default function ItineraryTimeline({
  payload,
  partial,
}: {
  payload: ItineraryPayload;
  partial?: boolean;
}) {
  const t = useT();
  const days = payload.days ?? [];

  // Day numbers parsed from labels ("Day 3 Evening" -> 3), else the sequence position.
  const parsedDays = days.map((day, i) => {
    const match = /day\s+(\d+)/i.exec(day.label);
    return match ? Number(match[1]) : i + 1;
  });

  // The footer prices the stay as a total. Nights come from the plan's own day span, with
  // the free-text date range as the fallback.
  const daySpan = parsedDays.length >= 2 ? Math.max(...parsedDays) - Math.min(...parsedDays) : 0;
  const parsedNights = parseNights(payload.travel_dates);
  const totalNights = daySpan > 0 ? daySpan : parsedNights;

  // Stays starting on the same day are alternatives and the footer prices the pick. Stays
  // starting on different days are a split stay; each covers the nights until the next begins.
  const stayStarts = new Map<string, { price: number; startDay: number }>();
  days.forEach((day, i) => {
    for (const product of day.products ?? []) {
      if (product.attributes?.price_unit === "per_night" && !stayStarts.has(product.product_id)) {
        stayStarts.set(product.product_id, { price: product.price, startDay: parsedDays[i] });
      }
    }
  });
  const groupStarts = [...new Set([...stayStarts.values()].map((s) => s.startDay))].sort(
    (a, b) => a - b,
  );
  const lastDay = parsedDays.length ? Math.max(...parsedDays) : 0;
  const stayGroups = groupStarts
    .map((start, gi) => {
      const structuralNights =
        gi + 1 < groupStarts.length ? groupStarts[gi + 1] - start : lastDay - start;
      // Only a single group may fall back to the date range; in a split stay a zero-span
      // group is malformed payload.
      const nights =
        structuralNights > 0 ? structuralNights : groupStarts.length === 1 ? (totalNights ?? 0) : 0;
      const prices = [...stayStarts.values()]
        .filter((stay) => stay.startDay === start)
        .map((stay) => stay.price)
        .sort((a, b) => a - b);
      return { nights, prices };
    })
    .filter((group) => group.nights > 0 && group.prices.length > 0);
  const hasAlternatives = stayGroups.some((group) => group.prices.length > 1);
  // With alternatives in play the exact total depends on the pick, so the footer
  // quotes the cheapest combination and says so.
  const stayTotal = stayGroups.reduce((sum, group) => sum + group.nights * group.prices[0], 0);

  // The date range arrives in the first frames, so it sizes the skeleton rail and the day
  // counter before the last day closes.
  const expectedDays = parsedNights != null ? parsedNights + 1 : null;
  const lastKnownDay = parsedDays.length ? Math.max(...parsedDays) : 0;
  const skeletonDays =
    expectedDays != null
      ? Array.from(
          { length: Math.max(0, expectedDays - lastKnownDay) },
          (_, i) => lastKnownDay + i + 1,
        )
      : [];

  // The rail shows the parsed day numbers; a second entry for the same day gets a
  // diamond instead of repeating the numeral.
  const dayNumbers: (number | null)[] = [];
  let lastSeen: number | null = null;
  for (const parsed of parsedDays) {
    dayNumbers.push(parsed === lastSeen ? null : parsed);
    lastSeen = parsed;
  }

  return (
    <section className="al-reveal" style={{ ...CARD, padding: 28 }}>
      <div className="flex items-start justify-between gap-3">
        {payload.title ? (
          <h3 style={display(24, 600)}>{payload.title}</h3>
        ) : (
          <span className="al-shimmer h-7 w-2/5" aria-hidden />
        )}
        {payload.travel_dates ? (
          <span
            className="shrink-0 rounded-full px-3 py-1.5"
            style={{ ...META, color: "var(--surface)", background: "var(--ink)" }}
          >
            {payload.travel_dates}
          </span>
        ) : null}
      </div>

      <ol className="mt-6">
        {days.map((day, i) => {
          const last = i === days.length - 1;
          const products = day.products ?? [];
          return (
            <li
              key={`${day.label}-${i}`}
              className="al-reveal-item grid grid-cols-[56px_1fr] gap-x-4"
              style={{ animationDelay: `${i * 70}ms` }}
            >
              <div className="flex flex-col items-center">
                <span
                  aria-label={day.label}
                  style={{
                    fontFamily: DISPLAY,
                    fontWeight: 700,
                    fontSize: dayNumbers[i] === null ? 22 : 40,
                    lineHeight: dayNumbers[i] === null ? 1.8 : 1,
                    color: i === 0 ? "var(--accent)" : "var(--ink)",
                    opacity: dayNumbers[i] === null ? 0.45 : 1,
                  }}
                >
                  {dayNumbers[i] ?? "\u25c8"}
                </span>
                {!last || partial ? (
                  <span aria-hidden className="mt-2 w-px flex-1" style={{ background: "var(--line)" }} />
                ) : null}
              </div>

              <div className={last ? "pt-1" : "pb-7 pt-1"}>
                <div style={display(19, 600)}>{day.label}</div>
                {day.note ? (
                  <p
                    className="mt-1"
                    style={{
                      fontFamily: DISPLAY,
                      fontStyle: "italic",
                      fontWeight: 400,
                      fontSize: 16,
                      lineHeight: 1.55,
                      color: "var(--ink-soft)",
                    }}
                  >
                    {day.note}
                  </p>
                ) : null}
                {products.length ? (
                  <div className="mt-3 flex flex-wrap gap-3">
                    {products.map((product) => (
                      <TravelCard key={product.product_id} product={product} className="w-60 shrink-0" />
                    ))}
                  </div>
                ) : null}
              </div>
            </li>
          );
        })}
        {/* Skeletons carry the real numerals so finished days do not reflow. */}
        {partial
          ? Array.from({ length: Math.max(1, skeletonDays.length) }, (_, i) => {
              const dayNumber = skeletonDays[i];
              const last = i === Math.max(1, skeletonDays.length) - 1;
              return (
                <li
                  aria-hidden
                  key={`skeleton-${dayNumber ?? "next"}-${i}`}
                  className="grid grid-cols-[56px_1fr] gap-x-4"
                >
                  <div className="flex flex-col items-center">
                    {dayNumber != null ? (
                      <span
                        style={{
                          fontFamily: DISPLAY,
                          fontWeight: 700,
                          fontSize: 40,
                          lineHeight: 1,
                          color: "var(--ink)",
                          opacity: 0.25,
                        }}
                      >
                        {dayNumber}
                      </span>
                    ) : (
                      <span className="al-shimmer h-9 w-7" />
                    )}
                    {!last ? (
                      <span className="mt-2 w-px flex-1" style={{ background: "var(--line)" }} />
                    ) : null}
                  </div>
                  <div className={last ? "pt-1.5" : "pb-7 pt-1.5"}>
                    <div className="al-shimmer h-[18px] w-2/5" />
                    <div className="al-shimmer mt-2 h-3.5 w-3/4" />
                    <div className="al-shimmer mt-3 h-[150px] w-60 !rounded-[14px]" />
                  </div>
                </li>
              );
            })
          : null}
      </ol>

      {partial ? (
        <p className="mt-3" style={{ ...META, fontSize: 11 }} aria-live="polite">
          {expectedDays == null
            ? t("Planning day {n}…", { n: days.length + 1 })
            : days.length < expectedDays
              ? t("Planning day {n} of {total}…", { n: days.length + 1, total: expectedDays })
              : t("Finishing the plan…")}
        </p>
      ) : null}

      {!partial && stayGroups.length > 0 && stayTotal > 0 ? (
        <div
          className="mt-4 flex flex-wrap items-baseline justify-between gap-2 border-t pt-3 border-(--line)"
          style={{ borderColor: "var(--line)" }}
        >
          <span style={META}>
            {stayGroups
              .map((group) => {
                const prices = group.prices.map((price) => formatPrice(price)).join(` ${t("or")} `);
                return group.nights === 1
                  ? t("{n} night · {prices}/night", { n: group.nights, prices })
                  : t("{n} nights · {prices}/night", { n: group.nights, prices });
              })
              .join(" + ")}
          </span>
          <span className="text-right">
            <span style={{ fontFamily: DISPLAY, fontSize: 20, fontWeight: 700, color: "var(--ink)" }}>
              {stayGroups.length === 1 && stayGroups[0].prices.length === 2
                ? t("{low} or {high}", {
                    low: formatPrice(stayGroups[0].nights * stayGroups[0].prices[0]),
                    high: formatPrice(stayGroups[0].nights * stayGroups[0].prices[1]),
                  })
                : hasAlternatives
                  ? t("from {price}", { price: formatPrice(stayTotal) })
                  : formatPrice(stayTotal)}
            </span>
            <span style={{ ...META, fontSize: 11, marginLeft: 5 }}>
              {hasAlternatives
                ? t("stay total · your pick of stay · all-in")
                : t("stay total · all-in, fees included")}
            </span>
          </span>
        </div>
      ) : null}
    </section>
  );
}
