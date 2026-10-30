// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { formatDate, formatMoney, formatNumber, GenCard, GenCardHeader, Pill, useT } from "web-shared";
import { PaceChip, PacingCurve, SellThroughBar, UNDER_PACE_ALERT_PTS, WeeklySparkline, holdsSummary } from "@/components/PacingParts";
import type { EventPacingPayload, PacingEvent, PacingTier } from "@/lib/types";
import { formatDaysToEvent } from "@/lib/format";

/** present_event_pacing (api/event_pacing.py). */

function TierStrip({ tier }: { tier: PacingTier }) {
  const t = useT();
  const history = tier.weekly_sold_cum ?? [];
  // The curve needs three weeks of history and a capacity; otherwise fall back to the sparkline.
  const curveReady = history.length >= 3 && tier.capacity != null && tier.capacity > 0;
  const underPacing = tier.pace_vs_baseline_pts != null && tier.pace_vs_baseline_pts <= UNDER_PACE_ALERT_PTS;
  return (
    <div className="rounded-[10px] bg-(--ground) px-3 py-2.5">
      <div className="flex flex-wrap items-center gap-x-2.5 gap-y-1">
        <span className="text-[13px] font-semibold text-(--ink)">{tier.tier ?? tier.product_id}</span>
        {tier.price != null ? <span className="at-mono text-[11.5px] text-(--ink-soft)">{t("{price} all-in", { price: formatMoney(tier.price) })}</span> : null}
        <span className="ml-auto flex items-center gap-1.5">
          {tier.waitlist_depth != null && tier.waitlist_depth > 0 ? <Pill tone="warn">{t("waitlist {n}", { n: formatNumber(tier.waitlist_depth) })}</Pill> : null}
          <PaceChip pts={tier.pace_vs_baseline_pts} />
        </span>
      </div>
      <div className="mt-2 flex items-center gap-2.5">
        <div className="min-w-0 flex-1">
          <SellThroughBar sellThroughPct={tier.sell_through_pct} baselinePct={tier.baseline_pct} />
        </div>
        <span className="at-mono shrink-0 text-[11.5px] text-(--ink-soft)">
          {tier.sold != null && tier.capacity != null ? t("{sold}/{capacity} sold", { sold: formatNumber(tier.sold), capacity: formatNumber(tier.capacity) }) : ""}
          {tier.remaining != null ? ` · ${t("{n} open", { n: formatNumber(tier.remaining) })}` : ""}
        </span>
      </div>
      {tier.holds ? <div className="at-mono mt-1 text-[11.5px] text-(--ink-soft)">{holdsSummary(tier.holds, t)}</div> : null}
      {curveReady ? (
        <div className="mt-2">
          <PacingCurve points={history} weeklyBaselinePct={tier.weekly_baseline_pct} capacity={tier.capacity} height={56} underPacing={underPacing} />
        </div>
      ) : history.length >= 2 ? (
        <div className="mt-2">
          <WeeklySparkline points={history} />
        </div>
      ) : null}
    </div>
  );
}

function EventPanel({ event }: { event: PacingEvent }) {
  const t = useT();
  return (
    <div className="px-3.5 pt-3">
      <div className="at-display truncate text-[17px] text-(--ink)" title={event.event_name ?? undefined}>
        {event.event_name ?? event.event_id}
      </div>
      <div className="text-[11.5px] text-(--ink-soft)">
        {[[event.venue, event.city].filter(Boolean).join(", "), formatDate(event.event_date), formatDaysToEvent(event.days_to_event, t)].filter(Boolean).join(" · ")}
      </div>
      {event.note ? <p className="mt-1 text-[12.5px] leading-snug text-(--ink-soft)">{event.note}</p> : null}
      <div className="mt-2 space-y-2">
        {event.tiers.map((tier) => (
          <TierStrip key={tier.product_id} tier={tier} />
        ))}
      </div>
    </div>
  );
}

export default function EventPacingCard({ payload }: { payload: EventPacingPayload }) {
  const t = useT();
  const events = payload.events ?? [];
  return (
    <GenCard className="pb-3.5">
      <GenCardHeader title={payload.title ?? t("Sell-through pacing")} aside={t("Tick marks the comparable-events baseline")} />
      {events.length ? (
        <div className="divide-y divide-(--line)">
          {events.map((event, index) => (
            <EventPanel key={event.event_id ?? index} event={event} />
          ))}
        </div>
      ) : (
        <p className="px-3.5 pt-2 text-[13px] text-(--ink-soft)">{t("No pacing rows were returned for those events.")}</p>
      )}
    </GenCard>
  );
}
