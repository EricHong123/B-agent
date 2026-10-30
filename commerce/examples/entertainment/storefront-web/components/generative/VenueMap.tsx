// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useMemo, useState } from "react";
import { formatMoney, useT } from "web-shared";
import { formatTime, tierColorMap } from "@/lib/format";
import { useLive } from "@/lib/live";
import type { VenueMapPayload, VenueMapSection } from "@/lib/types";
import { QueuePosition, RECOMMENDED_LABEL, Stub } from "./shared";

const SIGHTLINES: Record<string, string> = {
  floor: "Flat floor, closest to the stage",
  bowl: "Raked seating wrapping the floor, clear elevated sightline",
  terrace: "Highest vantage, full-stage panorama",
  mezzanine: "Elevated side vantage over the floor",
  balcony: "Front-facing elevated view",
};

/** One fill per tier; selection, highlight, and hover change only stroke and opacity. */
function sectionFill(
  section: VenueMapSection,
  color: string | undefined,
  selected: boolean,
  hoveredTier: string | null,
): { fill: string; opacity: number; stroke?: string; strokeWidth?: number } {
  if (section.kind === "stage") return { fill: "var(--ink-soft)", opacity: 0.28 };
  if (!section.product_id || !color) return { fill: "var(--tier-muted)", opacity: 0.3 };
  const hovered = hoveredTier != null && section.product_id === hoveredTier;
  const dimmed = hoveredTier != null && !hovered;
  if (section.status === "sold_out") {
    return { fill: "var(--tier-muted)", opacity: dimmed ? 0.25 : 0.4 };
  }
  const opacity = dimmed ? 0.5 : hovered ? 0.92 : 0.8;
  if (selected) return { fill: color, opacity, stroke: "var(--ink)", strokeWidth: 0.9 };
  if (hovered) return { fill: color, opacity, stroke: "var(--ink)", strokeWidth: 0.5 };
  if (section.highlighted) {
    return { fill: color, opacity, stroke: "var(--accent)", strokeWidth: 0.6 };
  }
  return { fill: color, opacity };
}

const VIGNETTE_BASE: Record<string, { stage: number; horizon: number }> = {
  floor: { stage: 0.86, horizon: 0.62 },
  bowl: { stage: 0.62, horizon: 0.5 },
  mezzanine: { stage: 0.5, horizon: 0.42 },
  balcony: { stage: 0.46, horizon: 0.4 },
  terrace: { stage: 0.34, horizon: 0.34 },
};

function SightlineVignette({
  selected,
  stage,
  viewHeight,
}: {
  selected: VenueMapSection;
  stage: VenueMapSection | undefined;
  viewHeight: number;
}) {
  const t = useT();
  const base = VIGNETTE_BASE[selected.kind] ?? { stage: 0.5, horizon: 0.45 };
  // 0 = touching the stage block, 1 = across the whole room.
  let distance = 0.5;
  if (stage) {
    const dx = selected.x + selected.w / 2 - (stage.x + stage.w / 2);
    const dy = selected.y + selected.h / 2 - (stage.y + stage.h / 2);
    distance = Math.min(1, Math.hypot(dx, dy) / Math.max(1, viewHeight));
  }
  const scale = Math.max(0.24, Math.min(0.95, base.stage * (1.15 - 0.45 * distance)));
  const width = 96 * scale;
  const height = 18 * scale;
  const horizonY = 64 * base.horizon + distance * 6;
  const isTerrace = selected.kind === "terrace";
  const morph = { transition: "all 200ms ease" } as const;

  return (
    <svg
      viewBox="0 0 96 64"
      className="h-[64px] w-[96px] shrink-0 rounded-(--radius) border border-(--line) bg-(--ground)"
      role="img"
      aria-label={t("Stylized view from {section}, not a photo", { section: selected.label })}
    >
      <defs>
        <linearGradient id="at-vign-sky" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={isTerrace ? "#1c2f3f" : "#16141f"} />
          <stop offset="100%" stopColor={isTerrace ? "#3a2f3a" : "#0f0e15"} />
        </linearGradient>
        <linearGradient id="at-vign-glow" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor="rgba(255, 240, 214, 0.35)" />
          <stop offset="100%" stopColor="rgba(255, 240, 214, 0)" />
        </linearGradient>
      </defs>
      <rect x="0" y="0" width="96" height="64" fill="url(#at-vign-sky)" />
      <rect
        x={48 - width / 2 - 6}
        y={Math.max(0, horizonY - height - 14)}
        width={width + 12}
        height={height + 14}
        fill="url(#at-vign-glow)"
        style={morph}
      />
      <rect
        x={48 - width / 2}
        y={horizonY - height}
        width={width}
        height={height}
        rx={1.5}
        fill="var(--ink-soft)"
        opacity={0.75}
        style={morph}
      />
      <line x1="0" y1={horizonY} x2="96" y2={horizonY} stroke="rgba(243,241,250,0.25)" strokeWidth="0.75" style={morph} />
      {/* Silhouette rows; closer sections draw fewer. */}
      {[0, 1, 2].map((row) => {
        const y = horizonY + 5 + row * (16 - distance * 5);
        if (y > 66) return null;
        return (
          <rect
            key={row}
            x={-6 - row * 4}
            y={y}
            width={112 + row * 8}
            height={5 + row * 2.5}
            rx={3}
            fill="#0a0910"
            opacity={0.9}
            style={morph}
          />
        );
      })}
    </svg>
  );
}

function QuantityStepper({
  quantity,
  setQuantity,
  max,
}: {
  quantity: number;
  setQuantity: (next: number) => void;
  max: number;
}) {
  const t = useT();
  return (
    <div className="flex items-center rounded-(--radius) border border-(--line) bg-(--card)">
      <button
        onClick={() => setQuantity(Math.max(1, quantity - 1))}
        aria-label={t("Fewer tickets")}
        className="px-2.5 py-0.5 text-sm text-(--ink-soft) hover:text-(--ink)"
      >
        −
      </button>
      <span className="at-mono min-w-6 text-center text-[13px] font-semibold text-(--ink)">
        {quantity}
      </span>
      <button
        onClick={() => setQuantity(Math.min(max, quantity + 1))}
        aria-label={t("More tickets")}
        className="px-2.5 py-0.5 text-sm text-(--ink-soft) hover:text-(--ink)"
      >
        +
      </button>
    </div>
  );
}

export default function VenueMap({ payload }: { payload: VenueMapPayload }) {
  const t = useT();
  const { hold, join, holdMinutes } = useLive();
  const sections = payload.sections ?? [];
  const viewbox = payload.venue.viewbox;

  // One entry per product, in the order the map, legend, and list all share.
  const tiers = useMemo(() => {
    const byProduct = new Map<string, VenueMapSection>();
    for (const section of sections) {
      if (section.product_id && !byProduct.has(section.product_id)) {
        byProduct.set(section.product_id, section);
      }
    }
    return [...byProduct.values()].sort((a, b) => (b.price_all_in ?? 0) - (a.price_all_in ?? 0));
  }, [sections]);

  const colors = useMemo(
    () =>
      tierColorMap(
        tiers.map((tier) => ({ product_id: tier.product_id!, price: tier.price_all_in ?? 0 })),
      ),
    [tiers],
  );

  const [selectedId, setSelectedId] = useState<string | null>(() => {
    if (payload.recommended_product_id) {
      const match = sections.find(
        (section) => section.product_id === payload.recommended_product_id,
      );
      if (match) return match.section_id;
    }
    return null;
  });
  // Hovering a legend row or a map block highlights the tier in both places.
  const [hoveredTier, setHoveredTier] = useState<string | null>(null);
  const [quantity, setQuantity] = useState(2);
  const [actionState, setActionState] = useState<"idle" | "busy" | "done" | "queued" | "failed">(
    "idle",
  );
  const [queuePosition, setQueuePosition] = useState<number | null>(null);

  const selected = sections.find((section) => section.section_id === selectedId) ?? null;
  const selectedSoldOut = selected?.status === "sold_out";
  const maxQuantity = Math.min(8, Math.max(1, selected?.remaining || 8));
  const boundedQuantity = Math.min(quantity, maxQuantity);

  const selectSection = (section: VenueMapSection) => {
    if (!section.product_id) return;
    setSelectedId((current) => (current === section.section_id ? null : section.section_id));
    setActionState("idle");
    setQueuePosition(null);
  };

  const act = async () => {
    if (!selected?.product_id) return;
    setActionState("busy");
    if (selectedSoldOut) {
      const position = await join(selected.product_id, boundedQuantity);
      if (position != null) {
        setQueuePosition(position);
        setActionState("queued");
      } else {
        setActionState("failed");
      }
    } else {
      const ok = await hold(selected.product_id, boundedQuantity);
      setActionState(ok ? "done" : "failed");
    }
  };

  const eventBits = [
    payload.event.name,
    payload.event.date,
    formatTime(payload.event.time) ?? undefined,
  ].filter(Boolean);

  return (
    <Stub
      component="venue_map"
      label={payload.title ?? t("{venue}: the room", { venue: payload.venue.name })}
    >
      <div className="flex items-baseline justify-between gap-3">
        <div className="min-w-0">
          <h4 className="at-display truncate text-[19px] uppercase leading-tight text-(--ink)">
            {payload.venue.name}
          </h4>
          <p className="mt-0.5 truncate text-[13px] text-(--ink-soft)">
            {payload.venue.city}
            {eventBits.length ? ` · ${eventBits.join(" · ")}` : ""}
          </p>
        </div>
        <span className="at-eyebrow shrink-0">{t("live availability")}</span>
      </div>

      <div className="mt-3 grid gap-4 sm:grid-cols-[1.5fr_1fr]">
        <svg
          viewBox={`0 0 ${viewbox.width} ${viewbox.height}`}
          className="w-full rounded-(--radius) border border-(--line) bg-(--ground)"
          role="img"
          aria-label={t("Stylized schematic of {venue}", { venue: payload.venue.name })}
        >
          <defs>
            <pattern id="at-hatch" width="2.4" height="2.4" patternTransform="rotate(45)" patternUnits="userSpaceOnUse">
              <line x1="0" y1="0" x2="0" y2="2.4" stroke="var(--line-strong)" strokeWidth="0.5" />
            </pattern>
          </defs>
          {sections.map((section) => {
            const isSelected = section.section_id === selectedId;
            const style = sectionFill(
              section,
              colors[section.product_id ?? ""],
              isSelected,
              hoveredTier,
            );
            const clickable = Boolean(section.product_id);
            const vertical = section.h > section.w * 1.6;
            // Fit the label to its block (0.62em average glyph width); fall back to the
            // short label before dropping it.
            const budget = (vertical ? section.h : section.w) - 3;
            const fit = (text: string) => Math.min(2.7, budget / (text.length * 0.62));
            let label = section.label;
            let fitted = fit(label);
            if (fitted < 1.9 && section.short_label) {
              label = section.short_label;
              fitted = fit(label);
            }
            const labelFits = section.kind !== "stage" && fitted >= 1.9 && section.h >= 5;
            return (
              <g
                key={section.section_id}
                onClick={() => selectSection(section)}
                onMouseEnter={() => setHoveredTier(section.product_id ?? null)}
                onMouseLeave={() => setHoveredTier(null)}
                style={{ cursor: clickable ? "pointer" : "default" }}
              >
                <rect
                  x={section.x}
                  y={section.y}
                  width={section.w}
                  height={section.h}
                  rx={1.4}
                  fill={style.fill}
                  opacity={style.opacity}
                  stroke={style.stroke}
                  strokeWidth={style.strokeWidth ?? 0}
                  style={{
                    transition: "opacity 160ms ease-out, stroke-width 160ms ease-out",
                    filter: isSelected
                      ? "drop-shadow(0 0 2.5px rgba(29, 36, 51, 0.35))"
                      : undefined,
                  }}
                />
                {section.status === "sold_out" ? (
                  <rect
                    x={section.x}
                    y={section.y}
                    width={section.w}
                    height={section.h}
                    rx={1.4}
                    fill="url(#at-hatch)"
                  />
                ) : null}
                {section.kind === "stage" ? (
                  <text
                    x={section.x + section.w / 2}
                    y={section.y + section.h / 2}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={3.4}
                    fontWeight={700}
                    letterSpacing={1.2}
                    fill="var(--ink)"
                    style={{ pointerEvents: "none", userSelect: "none" }}
                  >
                    {t("STAGE")}
                  </text>
                ) : labelFits ? (
                  <text
                    x={section.x + section.w / 2}
                    y={section.y + section.h / 2}
                    textAnchor="middle"
                    dominantBaseline="central"
                    fontSize={fitted}
                    fontWeight={500}
                    letterSpacing={0.2}
                    fill={
                      section.status === "sold_out"
                        ? "rgba(29,36,51,0.45)"
                        : "rgba(15,14,21,0.92)"
                    }
                    transform={
                      vertical
                        ? `rotate(90 ${section.x + section.w / 2} ${section.y + section.h / 2})`
                        : undefined
                    }
                    style={{ pointerEvents: "none", userSelect: "none" }}
                  >
                    {label}
                  </text>
                ) : null}
              </g>
            );
          })}
        </svg>

        <div className="flex flex-col gap-1.5">
          {tiers.map((tier) => {
            const color = colors[tier.product_id!];
            const soldOut = tier.status === "sold_out";
            const isSelectedTier = selected?.product_id === tier.product_id;
            const recommended = payload.recommended_product_id === tier.product_id;
            const low = !soldOut && (tier.remaining ?? Infinity) <= 12;
            return (
              <button
                key={tier.product_id}
                onClick={() => selectSection(
                  sections.find(
                    (section) =>
                      section.product_id === tier.product_id &&
                      (isSelectedTier ? section.section_id === selected?.section_id : true),
                  ) ?? tier,
                )}
                onMouseEnter={() => setHoveredTier(tier.product_id ?? null)}
                onMouseLeave={() => setHoveredTier(null)}
                className={`flex items-center gap-2.5 rounded-(--radius) border px-2.5 py-2 text-left transition-colors ${
                  isSelectedTier
                    ? "border-(--ink)/60 bg-(--well)"
                    : hoveredTier === tier.product_id
                      ? "border-(--ink-soft)/60 bg-(--well)/60"
                      : "border-(--line) hover:border-(--ink-soft)/50"
                }`}
              >
                <span
                  className="h-3 w-3 shrink-0 rounded-[3px]"
                  style={{ background: soldOut ? "var(--tier-muted)" : color }}
                  aria-hidden
                />
                <span className="min-w-0 flex-1">
                  {/* The pill wraps under the name rather than truncating it. */}
                  <span className="flex flex-wrap items-center gap-x-1.5 gap-y-0.5">
                    <span className="text-[14px] font-semibold leading-tight text-(--ink)">
                      {tier.tier ?? tier.label}
                    </span>
                    {recommended ? (
                      <span className="at-pill at-pill--accent shrink-0">{t(RECOMMENDED_LABEL)}</span>
                    ) : null}
                  </span>
                  <span
                    className={`at-mono block text-[11px] ${
                      soldOut
                        ? "text-(--danger)"
                        : low
                          ? "text-(--warn)"
                          : "text-(--ink-soft)"
                    }`}
                  >
                    {soldOut ? t("Sold out, waitlist open") : t("{n} left", { n: String(tier.remaining) })}
                  </span>
                </span>
                <span className="at-mono shrink-0 text-[14px] font-semibold text-(--ink)">
                  {tier.price_all_in != null
                    ? formatMoney(tier.price_all_in, tier.currency)
                    : "—"}
                  <span className="ml-1 text-[11px] font-normal text-(--ink-soft)">{t("all-in")}</span>
                </span>
              </button>
            );
          })}
        </div>
      </div>

      {selected?.product_id ? (
        <div className="at-reveal mt-3 rounded-(--radius) border border-(--line) bg-(--well)/60 p-3">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div className="flex min-w-0 items-center gap-3">
              <SightlineVignette
                selected={selected}
                stage={sections.find((section) => section.kind === "stage")}
                viewHeight={viewbox.height}
              />
              <div className="min-w-0">
                <p className="text-[14px] font-semibold text-(--ink)">
                  {selected.label}
                  <span className="at-mono ml-2 text-[13px] font-normal text-(--ink-soft)">
                    {selected.tier}
                  </span>
                </p>
                <p className="mt-0.5 flex items-center gap-1.5 text-[12px] text-(--ink-soft)">
                  <svg viewBox="0 0 16 16" className="h-3 w-3 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5" aria-hidden>
                    <path d="M1.5 8s2.5-4.5 6.5-4.5S14.5 8 14.5 8 12 12.5 8 12.5 1.5 8 1.5 8Z" />
                    <circle cx="8" cy="8" r="2" />
                  </svg>
                  {t(SIGHTLINES[selected.kind] ?? "Stylized schematic, not a seat-accurate plan")}
                </p>
              </div>
            </div>
            <span className="at-mono text-[16px] font-semibold text-(--ink)">
              {selected.price_all_in != null
                ? formatMoney(selected.price_all_in, selected.currency)
                : "—"}
              <span className="ml-1 text-[11px] font-normal text-(--ink-soft)">{t("all-in")}</span>
            </span>
          </div>
          <div className="mt-2.5 flex flex-wrap items-center gap-3">
            {!selectedSoldOut ? (
              <>
                <QuantityStepper
                  quantity={boundedQuantity}
                  setQuantity={setQuantity}
                  max={maxQuantity}
                />
                <span className="text-[12px] text-(--ink-soft)">
                  {selected.kind === "floor"
                    ? t("General admission, no assigned seats")
                    : t("Reserved seats, assigned together at purchase")}
                </span>
              </>
            ) : null}
            <span className="ml-auto">
              {actionState === "done" ? (
                <span className="at-mono text-[11.5px] font-semibold text-(--warn)">
                  ✓ {t("Held for {minutes}:00, not charged", { minutes: holdMinutes })}
                </span>
              ) : actionState === "queued" && queuePosition != null && selected.product_id ? (
                <QueuePosition productId={selected.product_id} fallback={queuePosition} />
              ) : (
                <button
                  onClick={() => void act()}
                  disabled={actionState === "busy"}
                  className={selectedSoldOut ? "at-btn-ghost" : "btn-primary"}
                >
                  {actionState === "busy"
                    ? "…"
                    : actionState === "failed"
                      ? t("Couldn't hold. Try again")
                      : selectedSoldOut
                        ? t("Join waitlist for {n}", { n: boundedQuantity })
                        : t("Hold {n} for 8 min", { n: boundedQuantity })}
                </button>
              )}
            </span>
          </div>
        </div>
      ) : null}

      <p className="at-eyebrow mt-3 !normal-case !tracking-normal">
        {t("Stylized schematic. Counts are live inventory; prices are all-in per ticket.")}
      </p>
    </Stub>
  );
}
