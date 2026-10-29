// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import type { ReactNode } from "react";
import { formatMoney, useT } from "web-shared";
import type { StatusPill } from "@/lib/format";
import { useLive } from "@/lib/live";
import type { Product } from "@/lib/types";

export const RECOMMENDED_LABEL = "Recommended";

const STUB_CODES: Record<string, string> = {
  venue_map: "A1",
  checkout: "A2",
  disclosure: "A3",
  hold: "A4",
  products: "B1",
  comparison: "B2",
  plan: "B3",
  guide: "C1",
  order_status: "C2",
};

function StubCaption({ component, label }: { component: string; label: string }) {
  return (
    <p className="at-stub-caption mb-2 select-none">
      ◉ ADMIT {STUB_CODES[component] ?? "00"} <b>·</b> {label}
    </p>
  );
}

export function Stub({
  component,
  label,
  children,
  flush,
}: {
  component: string;
  label: string;
  children: ReactNode;
  flush?: boolean;
}) {
  return (
    <section className="at-reveal mt-1">
      <StubCaption component={component} label={label} />
      <div className={`at-card overflow-hidden ${flush ? "" : "p-4 sm:p-5"}`}>{children}</div>
    </section>
  );
}

export function Pill({ pill }: { pill: StatusPill }) {
  const t = useT();
  return <span className={`at-pill at-pill--${pill.tone}`}>{t(pill.label)}</span>;
}

export function CountdownArc({
  fraction,
  tone = "var(--warn)",
  size = 20,
  strokeWidth = 3,
  className,
}: {
  fraction: number;
  tone?: string;
  size?: number;
  strokeWidth?: number;
  className?: string;
}) {
  const radius = (24 - strokeWidth) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = Math.max(0, Math.min(1, fraction));
  return (
    <svg
      viewBox="0 0 24 24"
      width={size}
      height={size}
      className={`shrink-0 -rotate-90 ${className ?? ""}`}
      aria-hidden
    >
      <circle cx="12" cy="12" r={radius} fill="none" stroke="var(--line)" strokeWidth={strokeWidth} />
      <circle
        cx="12"
        cy="12"
        r={radius}
        fill="none"
        stroke={tone}
        strokeWidth={strokeWidth}
        strokeLinecap="round"
        strokeDasharray={`${clamped * circumference} ${circumference}`}
        style={{ transition: "stroke-dasharray 500ms linear, stroke 500ms linear" }}
      />
    </svg>
  );
}

export function QueuePosition({
  productId,
  fallback,
}: {
  productId: string;
  fallback: number;
}) {
  const t = useT();
  const { waitlist } = useLive();
  const entry = waitlist.find((row) => row.product_id === productId);
  const position = entry?.position ?? fallback;
  const ahead = Math.max(0, position - 1);
  return (
    <span className="inline-flex items-center gap-2">
      <CountdownArc fraction={1 / Math.max(1, position)} tone="var(--accent)" size={18} strokeWidth={3.5} />
      <span className="at-mono text-[11.5px] font-semibold text-(--ink)">
        {t("#{position} in line", { position })}
        <span className="ml-1.5 font-normal text-(--ink-soft)">
          {ahead ? `· ${t("{ahead} ahead of you", { ahead })}` : `· ${t("you're next")}`} · {t("updates automatically")}
        </span>
      </span>
    </span>
  );
}

export function AllInPrice({
  price,
  currency,
  size = "md",
  suffix = "all-in",
}: {
  price: number;
  currency?: string;
  size?: "sm" | "md" | "lg" | "xl";
  suffix?: string;
}) {
  const t = useT();
  const sizeClass =
    size === "xl"
      ? "text-[30px]"
      : size === "lg"
        ? "text-[26px]"
        : size === "md"
          ? "text-[22px]"
          : "text-[16px]";
  return (
    <span className="inline-flex items-baseline gap-1.5 whitespace-nowrap">
      <span className={`at-mono font-bold leading-none tracking-tight text-(--ink) ${sizeClass}`}>
        {formatMoney(price, currency)}
      </span>
      <span className="at-eyebrow !text-(--ink-soft)">{t(suffix)}</span>
    </span>
  );
}

export function ValueScoreChip({
  score,
  verdict,
}: {
  score: number;
  verdict: "green" | "amber" | "red";
}) {
  const t = useT();
  const toneClass =
    verdict === "green"
      ? "border-(--ok)/45 bg-(--ok-soft) text-(--ok)"
      : verdict === "amber"
        ? "border-(--warn)/45 bg-(--warn-soft) text-(--warn)"
        : "border-(--danger)/45 bg-(--danger-soft) text-(--danger)";
  return (
    <span
      className={`at-mono inline-flex items-center gap-1 rounded-[6px] border px-1.5 py-0.5 text-[12px] font-bold ${toneClass}`}
      title={t("Value score, computed by the box office from live listing and inventory data")}
    >
      {score}/10
    </span>
  );
}

export function DateSquare({ mon, day, dow }: { mon: string; day: string; dow: string }) {
  return (
    <div className="flex w-[52px] shrink-0 flex-col items-center rounded-(--radius) border border-(--line) bg-(--well) py-1.5">
      <span className="at-eyebrow !text-(--accent)">{mon}</span>
      <span className="at-display text-[24px] leading-none text-(--ink)">{day}</span>
      <span className="at-eyebrow mt-0.5">{dow}</span>
    </div>
  );
}

export function VenueLine({ product }: { product: Product }) {
  const attrs = product.attributes ?? {};
  const parts = [attrs.venue, attrs.city].filter(Boolean);
  if (!parts.length) return null;
  return (
    <p className="mt-0.5 truncate text-[13px] text-(--ink-soft)">{parts.join(" · ")}</p>
  );
}
