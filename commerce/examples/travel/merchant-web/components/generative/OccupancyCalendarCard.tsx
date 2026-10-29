// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import { formatChangePct, formatDayMonth, formatMoney, formatNumber, formatPeriodLabel, formatRate, GenCard, GenCardHeader, Pill, useT } from "web-shared";
import type { OccupancyCalendarPayload, OccupancyListing, OccupancyWeek } from "@/lib/types";

/** Payload shape: examples/travel/api/occupancy.py; every field is optional. */

function clampPct(raw: number | null | undefined): number | null {
  if (raw == null || Number.isNaN(raw)) return null;
  const pct = raw > 0 && raw <= 1 ? raw * 100 : raw;
  return Math.max(0, Math.min(100, pct));
}

function rate(value: number | null | undefined): string | null {
  if (value == null) return null;
  return formatMoney(value, "USD", { whole: Number.isInteger(value) });
}

function PaceChip({ pacePct }: { pacePct: number | null | undefined }) {
  const t = useT();
  if (pacePct == null) return null;
  // The week's on-the-books pace, distinct from the 30-day pace the pricing summary quotes.
  return (
    <Pill tone={pacePct >= 0 ? "ok" : "danger"} title={t("On-the-books pace for this week against the comparable period")}>
      {t("{change} pace", { change: formatChangePct(pacePct) })}
    </Pill>
  );
}

function WeekStrip({ children }: { children: React.ReactNode }) {
  const t = useT();
  const ref = useRef<HTMLDivElement>(null);
  const [clippedLeft, setClippedLeft] = useState(false);
  const [clippedRight, setClippedRight] = useState(false);

  const update = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    setClippedLeft(el.scrollLeft > 2);
    setClippedRight(el.scrollLeft + el.clientWidth < el.scrollWidth - 2);
  }, []);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver(update);
    observer.observe(el);
    return () => observer.disconnect();
  }, [update]);

  // scrollWidth grows when week cells arrive without the container resizing, which the
  // ResizeObserver does not see; setState bails out when the value is unchanged.
  useEffect(update);

  return (
    <div className="relative mt-2">
      <div ref={ref} onScroll={update} className="panel-scroll flex gap-1.5 overflow-x-auto pb-1">
        {children}
      </div>
      {clippedLeft ? (
        <div
          aria-hidden
          className="pointer-events-none absolute inset-y-0 left-0 w-8"
          style={{ background: "linear-gradient(to right, var(--card), transparent)" }}
        />
      ) : null}
      {clippedRight ? (
        <>
          <div
            aria-hidden
            className="pointer-events-none absolute inset-y-0 right-0 w-10"
            style={{ background: "linear-gradient(to left, var(--card), transparent)" }}
          />
          <button
            type="button"
            aria-label={t("Scroll to later weeks")}
            onClick={() => ref.current?.scrollBy({ left: 200, behavior: "smooth" })}
            className="absolute right-0.5 top-1/2 -translate-y-1/2 rounded-full border border-(--line-strong) bg-(--card) px-1.5 pb-0.5 text-[13px] leading-none text-(--ink-soft) shadow-(--shadow-sm) transition hover:text-(--ink)"
          >
            ›
          </button>
        </>
      ) : null}
    </div>
  );
}

function WeekCell({ week, baseRate }: { week: OccupancyWeek; baseRate?: number | null }) {
  const t = useT();
  const occupancy = clampPct(week.occupancy_pct);
  const midweek = clampPct(week.midweek_occupancy_pct);
  const weekend = clampPct(week.weekend_occupancy_pct);
  const override = week.override ?? null;
  const weekRate = rate(week.nightly_rate);
  return (
    <div
      className={`flex w-[108px] shrink-0 flex-col gap-1 rounded-[9px] px-2 py-1.5 ${
        override ? "bg-(--accent-soft) shadow-[inset_0_0_0_1px_var(--accent)]" : "bg-(--ground)"
      }`}
    >
      <div className="text-[11px] font-medium text-(--ink-soft)">
        {week.week_start ? t("Week of {date}", { date: formatDayMonth(week.week_start) }) : "—"}
      </div>
      <div className="flex items-baseline gap-1.5">
        <span className="text-[13px] font-semibold tabular-nums leading-none text-(--ink)">
          {weekRate ?? "—"}
        </span>
        {override && baseRate != null && week.nightly_rate !== baseRate ? (
          <span className="text-[11px] tabular-nums text-(--ink-soft) line-through">
            {rate(baseRate)}
          </span>
        ) : null}
      </div>
      {occupancy != null ? (
        <div>
          <div className="h-1 w-full overflow-hidden rounded-full bg-(--line)">
            <div
              className={occupancy >= 85 ? "h-full bg-(--ink)" : "h-full bg-(--ink)/55"}
              style={{ width: `${occupancy}%` }}
            />
          </div>
          <div className="mt-0.5 text-[11px] tabular-nums text-(--ink-soft)">
            {t("{pct} booked", { pct: formatRate(occupancy) })}
          </div>
        </div>
      ) : null}
      {midweek != null || weekend != null ? (
        <div className="text-[11px] tabular-nums text-(--ink-soft)">
          {midweek != null ? t("MW {pct}%", { pct: Math.round(midweek) }) : null}
          {midweek != null && weekend != null ? " · " : null}
          {weekend != null ? t("WE {pct}%", { pct: Math.round(weekend) }) : null}
        </div>
      ) : null}
      <PaceChip pacePct={week.on_the_books_pace_pct} />
      {override ? (
        <div className="flex items-center gap-1 text-[11px] font-semibold text-(--accent-ink)">
          <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-(--accent)" aria-hidden />
          <span className="truncate">
            {override.ends ? t("Override to {date}", { date: formatDayMonth(override.ends) }) : t("Override")}
          </span>
        </div>
      ) : null}
    </div>
  );
}

function ListingStrip({ listing }: { listing: OccupancyListing }) {
  const t = useT();
  const weeks = listing.weeks ?? [];
  const baseRate = rate(listing.base_nightly_rate);
  return (
    <div className="border-t border-(--line) px-3.5 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1">
        <div className="min-w-0">
          <div className="truncate text-[13px] font-semibold text-(--ink)">
            {listing.title ?? listing.listing_id ?? t("Property")}
          </div>
          <div className="text-[12px] tabular-nums text-(--ink-soft)">
            {[
              listing.listing_id,
              listing.rooms != null ? t("{count} rooms", { count: formatNumber(listing.rooms) }) : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </div>
        </div>
        {baseRate ? <div className="text-[12px] tabular-nums text-(--ink-soft)">{t("Base {rate} / night", { rate: baseRate })}</div> : null}
      </div>
      {listing.note ? (
        <p className="mt-1 text-[12px] leading-snug text-(--ink-soft)">{listing.note}</p>
      ) : null}
      {weeks.length ? (
        <WeekStrip>
          {weeks.map((week, index) => (
            <WeekCell
              key={week.week_start ?? index}
              week={week}
              baseRate={listing.base_nightly_rate}
            />
          ))}
        </WeekStrip>
      ) : (
        <p className="mt-2 text-[12px] text-(--ink-soft)">
          {t("No weeks in this window for this property.")}
        </p>
      )}
    </div>
  );
}

export default function OccupancyCalendarCard({ payload }: { payload: OccupancyCalendarPayload }) {
  const t = useT();
  const listings = payload.listings ?? [];
  const calendarWindow = payload.period
    ? formatPeriodLabel(payload.period)
    : payload.start && payload.end
      ? `${formatDayMonth(payload.start)} – ${formatDayMonth(payload.end)}`
      : null;
  const anyOverride = listings.some((listing) =>
    (listing.weeks ?? []).some((week) => week.override),
  );

  return (
    <GenCard>
      <GenCardHeader title={payload.title ?? t("Occupancy & pacing")} aside={calendarWindow} />
      {listings.length ? (
        <div className="mt-2.5">
          {listings.map((listing, index) => (
            <ListingStrip key={listing.listing_id ?? index} listing={listing} />
          ))}
        </div>
      ) : (
        <p className="px-3.5 pb-3.5 pt-2 text-[13px] text-(--ink-soft)">{t("No occupancy data was returned for this window.")}</p>
      )}
      {anyOverride ? (
        <div className="flex items-center gap-1.5 border-t border-(--line) px-3.5 py-2 text-[11.5px] text-(--ink-soft)">
          <span className="h-1.5 w-1.5 rounded-full bg-(--accent)" aria-hidden />
          {t("Weeks with an applied rate override")}
        </div>
      ) : null}
    </GenCard>
  );
}
