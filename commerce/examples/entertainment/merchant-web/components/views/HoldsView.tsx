// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { AskButton, formatDate, formatDayMonth, formatNumber, KindIcon, Notice, PageHeader, Panel, Skeleton, useResource, useT } from "web-shared";
import { releasableTotal } from "@/components/PacingParts";
import { fetchPacing } from "@/lib/api";
import type { PacingEvent, PacingTier, StagedWindow, VenueRecord } from "@/lib/types";
import { countLabel, formatDaysToEvent } from "@/lib/format";

function sectionState(tier: PacingTier | undefined): {
  fill: string;
  fillOpacity: number;
  stroke: string;
  strokeDasharray?: string;
} {
  if (!tier) {
    // A ticketed section with no live tier row: not on sale.
    return { fill: "none", fillOpacity: 1, stroke: "var(--ink-faint)", strokeDasharray: "3 2.5" };
  }
  if (tier.remaining === 0) {
    return { fill: "var(--ink-faint)", fillOpacity: 0.35, stroke: "var(--line-strong)" };
  }
  // Fill opacity follows the open share.
  let openFrac = 0;
  if (tier.capacity != null && tier.capacity > 0 && tier.remaining != null) {
    openFrac = Math.max(0, Math.min(1, tier.remaining / tier.capacity));
  } else if (tier.sell_through_pct != null) {
    openFrac = Math.max(0, Math.min(1, 1 - tier.sell_through_pct / 100));
  }
  return {
    fill: "var(--accent)",
    fillOpacity: 0.12 + 0.55 * openFrac,
    stroke: "var(--accent)",
  };
}

function LegendKey({ swatch, label }: { swatch: string; label: string }) {
  return (
    <span className="flex items-center gap-1">
      <span className={`h-2.5 w-2.5 rounded-[3px] ${swatch}`} aria-hidden />
      {label}
    </span>
  );
}

function SchematicLegend() {
  const t = useT();
  return (
    <div className="at-mono mt-2 flex flex-wrap items-center gap-x-3 gap-y-1 text-[11px] text-(--ink-soft)">
      <LegendKey swatch="border border-(--accent) bg-(--accent)/60" label={t("open")} />
      <LegendKey swatch="border border-(--accent)/50 bg-(--accent)/20" label={t("selling")} />
      <LegendKey swatch="border border-(--line-strong) bg-(--ink-faint)/35" label={t("sold out")} />
      <LegendKey swatch="border border-dashed border-(--ink-faint)" label={t("not on sale")} />
    </div>
  );
}

function VenueSchematic({ venue, tiers }: { venue: VenueRecord; tiers: PacingTier[] }) {
  const t = useT();
  const byCode = new Map<string, PacingTier>();
  for (const tier of tiers) {
    const code = tier.tier_code;
    if (code != null && !byCode.has(code)) byCode.set(code, tier);
  }
  // The tier-level open count renders once, in the tier's largest section.
  const countHost = new Map<string, string>();
  for (const section of venue.sections) {
    if (section.tier_code == null) continue;
    const current = countHost.get(section.tier_code);
    const currentSection = venue.sections.find((s) => s.section_id === current);
    if (!currentSection || section.w * section.h > currentSection.w * currentSection.h) {
      countHost.set(section.tier_code, section.section_id);
    }
  }
  return (
    <div>
      <svg
        viewBox={`0 0 ${venue.viewbox.width} ${venue.viewbox.height}`}
        className="w-full max-w-md"
        role="img"
        aria-label={t("{venue} seat map, sections shaded by live sell-through", { venue: venue.name })}
      >
        {venue.sections.map((section) => {
          const tier = section.tier_code != null ? byCode.get(section.tier_code) : undefined;
          const isStage = section.tier_code == null;
          const state = isStage
            ? { fill: "none", fillOpacity: 1, stroke: "var(--line-strong)" }
            : sectionState(tier);
          const soldOut = tier?.remaining === 0;
          const showCount =
            tier != null &&
            tier.remaining != null &&
            tier.remaining > 0 &&
            countHost.get(section.tier_code ?? "") === section.section_id &&
            section.w >= 16 &&
            section.h >= 8;
          const tierVars = {
            section: section.label,
            tier: tier ? (tier.tier ?? tier.product_id) : "",
            n: tier?.remaining != null ? formatNumber(tier.remaining) : "",
            capacity: tier?.capacity != null ? formatNumber(tier.capacity) : "",
          };
          const title = isStage
            ? section.label
            : tier
              ? tier.remaining != null
                ? tier.capacity != null
                  ? t("{section}, {tier}: {n} open of {capacity}", tierVars)
                  : t("{section}, {tier}: {n} open", tierVars)
                : tier.capacity != null
                  ? t("{section}, {tier}: open unknown of {capacity}", tierVars)
                  : t("{section}, {tier}: open unknown", tierVars)
              : t("{section}, not on sale", tierVars);
          return (
            <g key={section.section_id}>
              <rect
                x={section.x}
                y={section.y}
                width={section.w}
                height={section.h}
                rx={1.5}
                fill={state.fill}
                fillOpacity={state.fillOpacity}
                stroke={state.stroke}
                strokeDasharray={"strokeDasharray" in state ? state.strokeDasharray : undefined}
                strokeWidth={0.4}
              >
                <title>{title}</title>
              </rect>
              <text
                x={section.x + section.w / 2}
                y={section.y + section.h / 2 + (showCount ? -0.6 : 1.1)}
                textAnchor="middle"
                fontSize={3}
                fill={soldOut || isStage || !tier ? "var(--ink-soft)" : "var(--ink)"}
                className="pointer-events-none"
              >
                {section.short_label ?? section.label}
              </text>
              {showCount ? (
                <text
                  x={section.x + section.w / 2}
                  y={section.y + section.h / 2 + 3.4}
                  textAnchor="middle"
                  fontSize={2.5}
                  fill="var(--ink-soft)"
                  className="pointer-events-none"
                >
                  {t("{n} open", { n: formatNumber(tier.remaining ?? 0) })}
                </text>
              ) : null}
            </g>
          );
        })}
      </svg>
      <SchematicLegend />
    </div>
  );
}

function AllocationRow({
  event,
  tier,
  onAskAssistant,
}: {
  event: PacingEvent;
  tier: PacingTier;
  onAskAssistant: (text: string) => void;
}) {
  const t = useT();
  const holds = tier.holds ?? {};
  const releasable = releasableTotal(holds);
  const releasePrompt = t(
    "Release {n} held seats on {event} {tier} ({id}): {promoter} promoter and {production} production hold. What would that do to pacing?",
    {
      n: formatNumber(releasable),
      event: event.event_name ?? event.event_id,
      tier: tier.tier ?? tier.product_id,
      id: tier.product_id,
      promoter: formatNumber(holds.promoter_hold ?? 0),
      production: formatNumber(holds.production_hold ?? 0),
    },
  );
  return (
    <tr className="border-t border-(--line)">
      <td className="py-2.5 pl-[18px] pr-3">
        <div className="text-[13.5px] font-medium leading-snug text-(--ink)">{tier.tier ?? tier.product_id}</div>
        <div className="at-mono text-[11.5px] text-(--ink-soft)">{tier.product_id}</div>
      </td>
      <td className="at-mono px-3 py-2.5 text-right text-(--ink)">{formatNumber(holds.promoter_hold ?? 0)}</td>
      <td className="at-mono px-3 py-2.5 text-right text-(--ink)">{formatNumber(holds.production_hold ?? 0)}</td>
      <td className="at-mono px-3 py-2.5 text-right text-(--ink-soft)">{formatNumber(holds.comps ?? 0)}</td>
      <td className="at-mono px-3 py-2.5 text-right text-(--ink-soft)">{formatNumber(holds.kills ?? 0)}</td>
      <td className="at-mono px-3 py-2.5 text-right font-semibold text-(--ink)">{formatNumber(releasable)}</td>
      <td className="at-mono px-3 py-2.5 text-right text-(--ink)">{tier.remaining != null ? formatNumber(tier.remaining) : "—"}</td>
      <td className="py-2.5 pl-3 pr-[18px] text-right">
        {releasable > 0 ? <AskButton label={t("Release holds")} onClick={() => onAskAssistant(releasePrompt)} /> : null}
      </td>
    </tr>
  );
}

function EventAllocations({
  event,
  venue,
  onAskAssistant,
}: {
  event: PacingEvent;
  venue?: VenueRecord;
  onAskAssistant: (text: string) => void;
}) {
  const t = useT();
  const releasable = event.tiers.reduce((sum, tier) => sum + releasableTotal(tier.holds), 0);
  return (
    <Panel
      title={<span className="at-display text-[19px]">{event.event_name ?? event.event_id}</span>}
      subtitle={[event.venue, formatDate(event.event_date), formatDaysToEvent(event.days_to_event, t)].filter(Boolean).join(" · ")}
      action={<span className="at-mono text-[12px] text-(--ink-soft)">{t("{n} releasable", { n: formatNumber(releasable) })}</span>}
    >
      <div className="grid gap-4 pt-1 @4xl:grid-cols-[minmax(0,340px)_minmax(0,1fr)]">
        {venue ? (
          <div className="px-[18px] pb-2">
            <VenueSchematic venue={venue} tiers={event.tiers} />
          </div>
        ) : null}
        <div className={`panel-scroll overflow-x-auto pb-1 ${venue ? "" : "@4xl:col-span-2"}`}>
          <table className="w-full border-collapse text-[13px]">
            <thead>
              <tr className="text-left text-[12px] text-(--ink-soft)">
                <th className="py-2 pl-[18px] pr-3 font-semibold">{t("Tier")}</th>
                <th className="px-3 py-2 text-right font-semibold">{t("Promoter")}</th>
                <th className="px-3 py-2 text-right font-semibold">{t("Production")}</th>
                <th className="px-3 py-2 text-right font-semibold">{t("Comps")}</th>
                <th className="px-3 py-2 text-right font-semibold">{t("Kills")}</th>
                <th className="px-3 py-2 text-right font-semibold">{t("Releasable")}</th>
                <th className="px-3 py-2 text-right font-semibold">{t("Open")}</th>
                <th className="py-2 pl-3 pr-[18px]" />
              </tr>
            </thead>
            <tbody>
              {event.tiers.map((tier) => (
                <AllocationRow key={tier.product_id} event={event} tier={tier} onAskAssistant={onAskAssistant} />
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </Panel>
  );
}

function StagedWindows({ windows }: { windows: StagedWindow[] }) {
  const t = useT();
  if (!windows.length) return null;
  return (
    <section className="flex flex-wrap items-start gap-x-4 gap-y-2 rounded-2xl border border-(--violet)/25 bg-(--violet-soft) px-[18px] py-3">
      <KindIcon icon="calendar" tone="violet" size={32} />
      <div className="min-w-0 flex-1">
        <div className="text-[14px] font-semibold text-(--ink)">
          {countLabel(t, windows.length, "{n} staged promotion window awaiting approval", "{n} staged promotion windows awaiting approval")}
        </div>
        <ul className="mt-1 space-y-0.5 text-[12.5px] text-(--ink-soft)">
          {windows.map((window) => (
            <li key={window.change_id}>
              <span className="font-semibold text-(--ink)">{window.name ?? window.change_id}</span>
              <span className="at-mono">
                {window.starts && window.ends ? ` · ${formatDayMonth(window.starts)} – ${formatDayMonth(window.ends)}` : ""} · {window.listing_ids.join(", ")}
              </span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}

export default function HoldsView({
  refreshKey,
  onAskAssistant,
}: {
  refreshKey: number;
  onAskAssistant: (text: string) => void;
}) {
  const t = useT();
  const { data, failed } = useResource(fetchPacing, [refreshKey]);
  const releasable = data?.events.reduce((sum, event) => sum + event.tiers.reduce((inner, tier) => inner + releasableTotal(tier.holds), 0), 0);

  return (
    <div className="ac-reveal @container flex flex-col gap-4">
      <PageHeader
        title={t("Holds")}
        subtitle={
          data
            ? t("{seats} releasable seats across {events} · promoter and production holds release; comps and kills never do", {
                seats: formatNumber(releasable ?? 0),
                events: countLabel(t, data.events.length, "{n} event", "{n} events"),
              })
            : undefined
        }
      />
      {failed && !data ? (
        <Notice>{t("The entertainment API isn't reachable, so the allocation book can't load.")}</Notice>
      ) : !data ? (
        <>
          <Skeleton className="h-56" />
          <Skeleton className="h-56" />
        </>
      ) : (
        <>
          <StagedWindows windows={data.staged_windows} />
          {data.events.length === 0 ? (
            <Notice>{t("No events in the allocation book.")}</Notice>
          ) : (
            data.events.map((event) => (
              <EventAllocations
                key={event.event_id}
                event={event}
                venue={event.venue_id ? (data.venues ?? {})[event.venue_id] : undefined}
                onAskAssistant={onAskAssistant}
              />
            ))
          )}
        </>
      )}
    </div>
  );
}
