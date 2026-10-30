// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** Shared by the Events view, the Holds view, and the event_pacing card. */

import { formatNumber, Pill, type Translate, useT } from "web-shared";
import type { HoldBuckets, WeeklySoldPoint } from "@/lib/types";
import { formatPacePts } from "@/lib/format";

/** Mirrors the backend's slow-mover threshold, in points vs baseline. */
export const UNDER_PACE_ALERT_PTS = -15;

function clampPct(raw: number | null | undefined): number | null {
  if (raw == null || Number.isNaN(raw)) return null;
  return Math.max(0, Math.min(100, raw));
}

export function SellThroughBar({
  sellThroughPct,
  baselinePct,
}: {
  sellThroughPct: number | null | undefined;
  baselinePct: number | null | undefined;
}) {
  const t = useT();
  const sold = clampPct(sellThroughPct);
  const baseline = clampPct(baselinePct);
  if (sold == null) return null;
  const behind = baseline != null && sold < baseline + UNDER_PACE_ALERT_PTS;
  return (
    <div
      className="relative h-1.5 w-full overflow-hidden rounded-full bg-(--line)"
      role="img"
      aria-label={
        baseline != null
          ? t("{pct}% sold, baseline {baseline}%", { pct: sold.toFixed(1), baseline: baseline.toFixed(1) })
          : t("{pct}% sold", { pct: sold.toFixed(1) })
      }
    >
      <div
        className={`h-full ${behind ? "bg-(--danger)" : "bg-(--ink)/70"}`}
        style={{ width: `${sold}%` }}
      />
      {baseline != null ? (
        <span
          className="absolute inset-y-0 w-0.5 bg-(--warn)"
          style={{ left: `${baseline}%` }}
          title={t("Comparable-events baseline {pct}%", { pct: baseline.toFixed(1) })}
        />
      ) : null}
    </div>
  );
}

export function PaceChip({ pts }: { pts: number | null | undefined }) {
  const t = useT();
  if (pts == null) return null;
  return (
    <Pill tone={pts >= 0 ? "ok" : pts <= UNDER_PACE_ALERT_PTS ? "danger" : "muted"} title={t("Sell-through vs the comparable-events baseline at today's days-to-event")}>
      <span className="at-mono">{formatPacePts(pts, t)}</span>
    </Pill>
  );
}

/** The y axis starts at zero. */
export function WeeklySparkline({ points }: { points: WeeklySoldPoint[] }) {
  const t = useT();
  if (points.length < 2) return null;
  const width = 160;
  const height = 36;
  const max = Math.max(...points.map((point) => point.sold_cum)) || 1;
  const step = width / (points.length - 1);
  const coords = points.map((point, index) => {
    const x = index * step;
    const y = height - 3 - (point.sold_cum / max) * (height - 6);
    return `${x.toFixed(1)},${y.toFixed(1)}`;
  });
  return (
    <svg
      viewBox={`0 0 ${width} ${height}`}
      className="h-9 w-full"
      preserveAspectRatio="none"
      role="img"
      aria-label={t("Weekly cumulative sales, {from} to {to} tickets", {
        from: formatNumber(points[0].sold_cum),
        to: formatNumber(points[points.length - 1].sold_cum),
      })}
    >
      <polyline
        points={`0,${height} ${coords.join(" ")} ${width},${height}`}
        fill="var(--well)"
        stroke="none"
      />
      <polyline
        points={coords.join(" ")}
        fill="none"
        stroke="var(--ink)"
        strokeWidth="1.5"
        strokeLinejoin="round"
        strokeLinecap="round"
      />
    </svg>
  );
}

/** Both series truncate to the shorter when their lengths differ. */
export function PacingCurve({
  points,
  weeklyBaselinePct,
  capacity,
  height = 72,
  underPacing = false,
}: {
  points: WeeklySoldPoint[];
  weeklyBaselinePct?: number[] | null;
  capacity: number | null | undefined;
  height?: number;
  underPacing?: boolean;
}) {
  const t = useT();
  const seats = capacity ?? 0;
  if (seats <= 0 || points.length < 2) return null;
  const rawBaseline = weeklyBaselinePct ?? [];
  const baselineUsable =
    rawBaseline.length >= 2 && rawBaseline.every((value) => Number.isFinite(value));
  const weeks = baselineUsable ? Math.min(points.length, rawBaseline.length) : points.length;
  if (weeks < 2) return null;
  const actual = points
    .slice(0, weeks)
    .map((point) => Math.max(0, Math.min(100, (point.sold_cum / seats) * 100)));
  const baseline = baselineUsable
    ? rawBaseline.slice(0, weeks).map((value) => Math.max(0, Math.min(100, value)))
    : null;
  const width = 300;
  const pad = 3;
  const step = width / (weeks - 1);
  const yFor = (value: number) => pad + (1 - value / 100) * (height - pad * 2);
  const toCoords = (series: number[]) =>
    series
      .map((value, index) => `${(index * step).toFixed(1)},${yFor(value).toFixed(1)}`)
      .join(" ");
  const actualStroke = underPacing ? "var(--danger)" : "var(--ink)";
  return (
    <div>
      <svg
        viewBox={`0 0 ${width} ${height}`}
        style={{ height }}
        className="w-full"
        preserveAspectRatio="none"
        role="img"
        aria-label={
          baseline != null
            ? t("Sell-through pacing: actual {actual}% sold, comparable baseline {baseline}%", {
                actual: actual[actual.length - 1].toFixed(1),
                baseline: baseline[baseline.length - 1].toFixed(1),
              })
            : t("Sell-through pacing: actual {actual}% sold", { actual: actual[actual.length - 1].toFixed(1) })
        }
      >
        {[25, 50, 75, 100].map((gridPct) => (
          <line
            key={gridPct}
            x1={0}
            x2={width}
            y1={yFor(gridPct)}
            y2={yFor(gridPct)}
            stroke="var(--line)"
            strokeWidth="1"
          />
        ))}
        {baseline != null ? (
          <polyline
            points={toCoords(baseline)}
            fill="none"
            stroke="var(--ink-soft)"
            strokeWidth="1.25"
            strokeDasharray="5 4"
            strokeLinejoin="round"
          />
        ) : null}
        <polyline
          points={toCoords(actual)}
          fill="none"
          stroke={actualStroke}
          strokeWidth="1.75"
          strokeLinejoin="round"
          strokeLinecap="round"
        />
      </svg>
      <div className="at-mono mt-1 flex items-center gap-3 text-[11px] text-(--ink-soft)">
        <span className="flex items-center gap-1">
          <span
            className="h-0.5 w-3 rounded-full"
            style={{ background: actualStroke }}
            aria-hidden
          />
          {t("actual")}
        </span>
        {baseline != null ? (
          <span className="flex items-center gap-1">
            <span className="w-3 border-t border-dashed border-(--ink-soft)" aria-hidden />
            {t("baseline")}
          </span>
        ) : null}
      </div>
    </div>
  );
}

/** Comps and kills are not releasable. */
export function releasableTotal(holds: HoldBuckets | null | undefined): number {
  if (!holds) return 0;
  return (holds.promoter_hold ?? 0) + (holds.production_hold ?? 0);
}

/** Zeros included. */
export function holdsSummary(holds: HoldBuckets | null | undefined, t: Translate): string | null {
  if (!holds) return null;
  return [
    t("Promoter {n}", { n: formatNumber(holds.promoter_hold ?? 0) }),
    t("Production {n}", { n: formatNumber(holds.production_hold ?? 0) }),
    t("Comps {n}", { n: formatNumber(holds.comps ?? 0) }),
    t("Kills {n}", { n: formatNumber(holds.kills ?? 0) }),
  ].join(" · ");
}
