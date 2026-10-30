// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { ChangeChip, formatMoney, formatNumber, formatPeriodLabel, formatRate, GenCard, GenCardHeader, Sparkline, titleCase, type Translate, useT } from "web-shared";
import type { MetricEntry, MetricsPayload } from "@/lib/types";

const CURRENCY_METRICS = new Set(["sales", "revenue", "average_order_value", "average_booking_value", "average_nightly_rate", "spend"]);
const RATE_METRICS = new Set(["conversion_rate", "occupancy", "occupancy_rate", "cancellation_rate", "return_rate", "click_through_rate"]);

function metricLabel(metric: string, t: Translate): string {
  if (metric === "average_order_value") return t("Average booking");
  if (metric === "orders") return t("Bookings");
  return t(titleCase(metric));
}

function metricValue(entry: MetricEntry): string | null {
  if (entry.value == null) return null;
  if (CURRENCY_METRICS.has(entry.metric)) return formatMoney(entry.value, entry.currency ?? "USD", { whole: entry.value >= 1000 });
  if (RATE_METRICS.has(entry.metric)) return formatRate(entry.value);
  return formatNumber(entry.value);
}

export default function MetricsCard({ payload }: { payload: MetricsPayload }) {
  const t = useT();
  const metrics = payload.metrics ?? [];
  return (
    <GenCard>
      <GenCardHeader title={payload.title ?? t("Performance")} aside={payload.period ? formatPeriodLabel(payload.period) : null} />
      <div className="mt-2 grid grid-cols-2 border-t border-(--line) [&>*:nth-child(even)]:border-l [&>*:nth-child(n+3)]:border-t [&>*]:border-(--line)">
        {metrics.map((entry, index) => {
          const value = metricValue(entry);
          const points = entry.series?.points?.map((point) => point.value);
          return (
            <div key={`${entry.metric}-${index}`} className="px-3.5 py-3">
              <div className="text-[12px] font-medium text-(--ink-soft)">{metricLabel(entry.metric, t)}</div>
              <div className="mt-1 flex items-baseline gap-2">
                {value != null ? <span className="text-[20px] font-semibold leading-none tracking-[-0.02em] tabular-nums text-(--ink)">{value}</span> : null}
                <ChangeChip changePct={entry.change_pct} />
              </div>
              {points && points.length > 1 ? <Sparkline points={points} height={34} label={t("{metric} trend", { metric: metricLabel(entry.metric, t) })} className="mt-2" /> : null}
              {entry.note ? <div className="mt-1.5 text-[11.5px] leading-snug text-(--ink-soft)">{entry.note}</div> : null}
            </div>
          );
        })}
      </div>
    </GenCard>
  );
}
