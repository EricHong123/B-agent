// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useState } from "react";
import { formatMoney, useT } from "web-shared";
import {
  dateBlock,
  formatTime,
  scarcityLine,
  soldTogetherCount,
  statusPill,
  valueScore,
  valueScoreBasis,
} from "@/lib/format";
import { useLive } from "@/lib/live";
import type { Product, ProductsPayload } from "@/lib/types";
import { AllInPrice, DateSquare, Pill, QueuePosition, Stub, ValueScoreChip, VenueLine } from "./shared";

function HoldOrWaitlistButton({ product }: { product: Product }) {
  const t = useT();
  const { hold, join, holdMinutes } = useLive();
  const [state, setState] = useState<"idle" | "busy" | "held" | "queued" | "failed">("idle");
  const [position, setPosition] = useState<number | null>(null);
  const soldOut = product.in_stock === false;
  // Sold-together listings hold or queue as one unit.
  const unit = soldTogetherCount(product);

  const act = async () => {
    setState("busy");
    if (soldOut) {
      const queuedAt = await join(product.product_id, unit);
      if (queuedAt != null) {
        setPosition(queuedAt);
        setState("queued");
      } else {
        setState("failed");
        window.setTimeout(() => setState("idle"), 2000);
      }
    } else {
      const ok = await hold(product.product_id, unit);
      setState(ok ? "held" : "failed");
      if (!ok) window.setTimeout(() => setState("idle"), 2000);
    }
  };

  if (state === "held") {
    return (
      <span className="at-mono text-[11px] font-semibold text-(--warn)">
        ✓ {t("Held for {minutes}:00", { minutes: holdMinutes })}
      </span>
    );
  }
  if (state === "queued" && position != null) {
    return <QueuePosition productId={product.product_id} fallback={position} />;
  }
  const holdLabel = unit > 1 ? t("Hold pair ({n})", { n: unit }) : t("Hold 1");
  return (
    <button
      onClick={() => void act()}
      disabled={state === "busy"}
      className={soldOut ? "at-btn-ghost !py-1.5 !text-[11px]" : "btn-primary !py-1.5 !text-[11px]"}
      title={
        soldOut
          ? t("Join the waitlist; you get a claim window if seats come back")
          : unit > 1
            ? t("This pair sells together: a {minutes}-minute hold on both, not charged", { minutes: holdMinutes })
            : t("A {minutes}-minute hold, not charged; the seats release if the timer runs out", { minutes: holdMinutes })
      }
    >
      {state === "busy" ? "…" : state === "failed" ? t("Couldn't") : soldOut ? t("Join waitlist") : holdLabel}
    </button>
  );
}

function EventCard({
  product,
  reason,
}: {
  product: Product;
  reason?: string | null;
}) {
  const t = useT();
  const attrs = product.attributes ?? {};
  const date = dateBlock(attrs.event_date);
  const pill = statusPill(product);
  const scarce = scarcityLine(product, t);
  const time = formatTime(attrs.event_time);

  return (
    <div className="at-reveal-item flex gap-3 rounded-(--radius) border border-(--line) bg-(--well)/50 p-3">
      {date ? <DateSquare {...date} /> : null}
      <div className="min-w-0 flex-1">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">
            {product.brand ? <p className="at-eyebrow truncate">{product.brand}</p> : null}
            <h4 className="at-display truncate text-[18px] uppercase leading-tight text-(--ink)">
              {attrs.event_name ?? product.title}
            </h4>
            <VenueLine product={product} />
          </div>
          <div className="shrink-0 text-right">
            <AllInPrice price={product.price} currency={product.currency} />
            <p className="at-eyebrow mt-0.5 !normal-case !tracking-normal">{t("per ticket")}</p>
          </div>
        </div>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <Pill pill={pill} />
          {attrs.tier ? (
            <span className="at-mono text-[11px] text-(--ink-soft)">
              {attrs.tier}
              {time ? ` · ${time}` : ""}
            </span>
          ) : null}
          {scarce ? (
            <span className="at-mono text-[11px] font-semibold text-(--warn)">{scarce}</span>
          ) : null}
          <span className="ml-auto">
            <HoldOrWaitlistButton product={product} />
          </span>
        </div>
        {reason ? (
          <p className="mt-1.5 text-[13px] leading-snug text-(--ink-soft)">{reason}</p>
        ) : null}
      </div>
    </div>
  );
}

function ResaleTable({ items }: { items: { product: Product; reason?: string | null }[] }) {
  const t = useT();
  const scored = items.map(({ product }) => ({ product, value: valueScore(product) }));
  const explained = scored.find((row) => row.value != null);

  return (
    <div className="mt-3">
      <p className="at-eyebrow mb-1.5">{t("Fan resale · capped listings, prices all-in")}</p>
      <div className="overflow-x-auto rounded-(--radius) border border-(--line)">
        <table className="w-full min-w-[480px] border-collapse text-left">
          <thead>
            <tr className="border-b border-(--line) bg-(--well)/70">
              <th className="at-eyebrow px-3 py-1.5 font-semibold">{t("Section")}</th>
              <th className="at-eyebrow px-3 py-1.5 font-semibold">{t("Event")}</th>
              <th className="at-eyebrow px-3 py-1.5 text-right font-semibold">{t("Qty")}</th>
              <th className="at-eyebrow px-3 py-1.5 text-right font-semibold">{t("Value")}</th>
              <th className="at-eyebrow px-3 py-1.5 text-right font-semibold">{t("All-in")}</th>
              <th className="px-2 py-1.5" aria-label={t("actions")} />
            </tr>
          </thead>
          <tbody>
            {scored.map(({ product, value }) => {
              const attrs = product.attributes ?? {};
              return (
                <tr key={product.product_id} className="border-b border-(--line) last:border-b-0">
                  <td className="at-mono px-3 py-2 text-[13px] text-(--ink)">
                    {attrs.tier ?? "—"}
                  </td>
                  <td className="max-w-[130px] truncate px-3 py-2 text-[13px] text-(--ink-soft)">
                    {attrs.event_name ?? product.title}
                  </td>
                  <td className="at-mono px-3 py-2 text-right text-[13px] text-(--ink)">
                    {soldTogetherCount(product)}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {value ? <ValueScoreChip score={value.score} verdict={value.verdict} /> : "—"}
                  </td>
                  <td className="at-mono px-3 py-2 text-right text-[14px] font-semibold text-(--ink)">
                    {formatMoney(product.price, product.currency)}
                    {value?.vsFace ? (
                      <span className="ml-1 text-[11px] font-normal text-(--ink-soft)">
                        {value.vsFace}
                      </span>
                    ) : null}
                  </td>
                  <td className="px-2 py-2 text-right">
                    <HoldOrWaitlistButton product={product} />
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      </div>
      {explained?.value ? (
        <p className="mt-1.5 text-[12px] leading-snug text-(--ink-soft)">
          {t("Value scores are computed by the box office: this {tier} ask is {basis}.", {
            tier: (explained.product.attributes ?? {}).tier ?? t("listing"),
            basis: valueScoreBasis(explained.value, t),
          })}
        </p>
      ) : null}
    </div>
  );
}

export default function EventCards({
  payload,
  partial,
}: {
  payload: ProductsPayload;
  partial?: boolean;
}) {
  const t = useT();
  const items = payload.items ?? [];
  const primary = items.filter(({ product }) => product.category !== "resale");
  const resale = items.filter(({ product }) => product.category === "resale");

  return (
    <Stub component="products" label={payload.title ?? t("What's on")}>
      <div className="flex flex-col gap-2.5">
        {primary.map(({ product, reason }) => (
          <EventCard key={product.product_id} product={product} reason={reason} />
        ))}
        {partial ? (
          // Skeleton at event-card size.
          <div className="flex gap-3 rounded-(--radius) border border-(--line) p-3">
            <div className="at-skeleton h-[64px] w-[52px] shrink-0" />
            <div className="flex min-w-0 flex-1 flex-col gap-2 py-1">
              <div className="at-skeleton h-4 w-3/5" />
              <div className="at-skeleton h-3 w-2/5" />
              <div className="at-skeleton h-3 w-1/3" />
            </div>
          </div>
        ) : null}
      </div>
      {resale.length ? <ResaleTable items={resale} /> : null}
    </Stub>
  );
}
