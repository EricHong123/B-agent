// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** The countdown follows the soonest server hold deadline. */

import { useMemo } from "react";
import { formatMoney, safeHandoffs, useCatalogIndex, useT } from "web-shared";
import { fetchProducts } from "@/lib/api";
import { countdownTone, dateBlock, feeParts, formatCountdown } from "@/lib/format";
import { useCountdown, useLive } from "@/lib/live";
import type { CartItem, CheckoutPayload, Product } from "@/lib/types";
import { CountdownArc, DateSquare, Stub } from "./shared";

function FeeRow({
  label,
  amount,
  note,
}: {
  label: string;
  amount: number;
  note?: string;
}) {
  return (
    <div className="flex items-baseline justify-between gap-4 py-1">
      <span className="text-[13px] text-(--ink-soft)">
        {label}
        {note ? <span className="ml-1.5 text-[11px] opacity-80">{note}</span> : null}
      </span>
      <span className="at-mono shrink-0 text-[13px] text-(--ink)">
        {formatMoney(amount)}
      </span>
    </div>
  );
}

function LineTile({ item, product }: { item: CartItem; product?: Product }) {
  const date = product ? dateBlock(product.attributes?.event_date) : null;
  if (date) return <DateSquare {...date} />;
  let hash = 0;
  for (const char of item.title) hash = (hash * 31 + char.charCodeAt(0)) % 360;
  return (
    <div
      aria-hidden
      className="flex w-[52px] shrink-0 items-center justify-center self-stretch rounded-(--radius) border border-(--line)"
      style={{
        background: `linear-gradient(140deg, hsl(${hash} 45% 26%), hsl(${(hash + 40) % 360} 45% 16%))`,
      }}
    >
      <span className="at-display text-[18px] text-(--ink)/80">{item.title.slice(0, 1)}</span>
    </div>
  );
}

export default function CheckoutHold({
  payload,
  variant = "checkout",
}: {
  /** The hold variant's payload (present_hold) has the same cart and note. */
  payload: CheckoutPayload;
  variant?: "checkout" | "hold";
}) {
  const t = useT();
  const { holds, holdsLoaded, holdMinutes } = useLive();
  const catalog = useCatalogIndex(fetchProducts);
  const cart = payload.cart;
  const handoffs = safeHandoffs(payload.handoffs);
  const items = cart.items ?? [];

  const soonest = holds.length ? Math.min(...holds.map((hold) => hold.deadline)) : null;
  const seconds = useCountdown(soonest);
  // Not expired until the first holds read has landed.
  const expired = holdsLoaded && (holds.length === 0 || (seconds != null && seconds <= 0));

  // Fee rows summed across lines; rendered only when every line carries fee attributes.
  const fees = useMemo(() => {
    let base = 0;
    let service = 0;
    let facility = 0;
    let processing = 0;
    const baseLabels = new Set<string>();
    for (const item of items) {
      const product = catalog[item.product_id];
      const parts = product ? feeParts(product) : null;
      if (!parts) return null;
      base += parts.base * item.quantity;
      service += parts.service * item.quantity;
      facility += parts.facility * item.quantity;
      processing += parts.processing * item.quantity;
      baseLabels.add(parts.baseLabel);
    }
    if (!items.length) return null;
    const baseLabel = baseLabels.size === 1 ? [...baseLabels][0] : "Face / seller value";
    return { base, baseLabel, service, facility, processing };
  }, [items, catalog]);

  // Arc is full at the hold TTL and empty at expiry.
  const tone = countdownTone(seconds);
  const fraction = expired ? 0 : (seconds ?? 0) / (holdMinutes * 60);

  return (
    <Stub
      component={variant}
      label={
        variant === "hold"
          ? t("Held for you, timer running, not charged")
          : t("Order summary: held, not charged")
      }
    >
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className={`at-pill ${expired ? "at-pill--out" : "at-pill--scarce"}`}>
          {expired ? t("Released, back on sale") : t("Held, not charged")}
        </span>
        <div className="flex items-center gap-2.5">
          <CountdownArc
            fraction={fraction}
            tone={expired ? "var(--ink-soft)" : tone}
            size={44}
            strokeWidth={2.5}
          />
          <div className="text-right">
            <p className="at-eyebrow">{expired ? t("Hold ended") : t("Hold expires")}</p>
            <p
              className={`at-mono text-[40px] font-semibold leading-none tracking-tight ${
                expired ? "text-(--ink-soft)" : seconds != null && seconds <= 30 ? "at-urgent" : ""
              }`}
              style={expired ? undefined : { color: tone }}
            >
              {holdsLoaded || seconds != null ? formatCountdown(seconds ?? 0) : "--:--"}
            </p>
          </div>
        </div>
      </div>
      <p className="mt-1 text-right text-[11px] text-(--ink-soft)">
        {expired
          ? t("These seats went back on sale. Ask ACME Assistant to hold them again.")
          : t("At 0:00 these seats release to other buyers.")}
      </p>

      {payload.note ? (
        <p className="mt-2 text-[13px] leading-snug text-(--ink-soft)">{payload.note}</p>
      ) : null}

      <div className="at-perf mt-3 pt-3">
        <div className="space-y-2">
          {items.map((item) => {
            const product = catalog[item.product_id];
            const attrs = product?.attributes ?? {};
            return (
              <div key={item.product_id} className="flex items-center gap-3">
                <LineTile item={item} product={product} />
                <div className="min-w-0 flex-1">
                  <p
                    className={`line-clamp-1 text-[14px] font-medium text-(--ink) ${
                      expired ? "line-through decoration-(--danger)/60 opacity-60" : ""
                    }`}
                    title={item.title}
                  >
                    {attrs.event_name ?? item.title}
                  </p>
                  <p
                    className={`mt-0.5 text-[12px] text-(--ink-soft) ${
                      expired ? "line-through decoration-(--danger)/50 opacity-60" : ""
                    }`}
                  >
                    {attrs.tier ? `${attrs.tier} · ` : ""}
                    <span className="at-mono">× {item.quantity}</span>
                  </p>
                </div>
                <span className="at-mono shrink-0 text-[14px] font-semibold text-(--ink)">
                  {formatMoney(item.line_total)}
                </span>
              </div>
            );
          })}
        </div>

        {fees ? (
          <div className="mt-3 rounded-(--radius) bg-(--well)/60 px-3 py-2">
            <p className="at-eyebrow mb-1">{t("Inside the total")}</p>
            <FeeRow label={t(fees.baseLabel)} amount={fees.base} />
            <FeeRow label={t("Service fee")} amount={fees.service} />
            <FeeRow label={t("Facility fee")} amount={fees.facility} />
            <FeeRow label={t("Order processing")} amount={fees.processing} />
          </div>
        ) : null}

        <div className="mt-3 flex items-baseline justify-between border-t-2 border-(--rule) pt-2">
          <span className="text-[15px] font-bold text-(--ink)">{t("Total, all-in")}</span>
          <span className="at-mono text-[30px] font-bold tracking-tight text-(--ink)">
            {formatMoney(cart.subtotal, cart.currency)}
          </span>
        </div>

        <div className="mt-3 flex items-center gap-2 rounded-(--radius) border border-(--line) px-3 py-2">
          <svg viewBox="0 0 16 16" className="h-3.5 w-3.5 shrink-0 text-(--ok)" fill="none" stroke="currentColor" strokeWidth="1.6" aria-hidden>
            <path d="M8 1.5 13.5 4v4c0 3.4-2.4 5.7-5.5 6.5C4.9 13.7 2.5 11.4 2.5 8V4L8 1.5Z" />
            <path d="m5.7 8 1.6 1.6 3-3.2" strokeLinecap="round" strokeLinejoin="round" />
          </svg>
          <span className="text-[12px] leading-snug text-(--ink-soft)">
            {t("Guaranteed valid for entry or your money back, and the all-in price you see is the full price you pay.")}
          </span>
        </div>

        {variant === "checkout" ? (
          <>
            {handoffs.length ? (
              // The backend named where payment happens (a hosted checkout URL, or one per seller).
              <div className="mt-3 flex flex-col gap-2">
                {handoffs.map((h) => (
                  <a
                    key={h.url}
                    href={h.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    aria-describedby="at-checkout-demo-note"
                    className="btn-primary w-full text-center"
                  >
                    {h.label ?? (h.seller ? t("Continue to checkout with {seller}", { seller: h.seller }) : t("Continue to checkout"))}
                  </a>
                ))}
              </div>
            ) : (
              // Disabled so assistive tech is not offered a focusable no-op.
              <button
                type="button"
                disabled
                aria-describedby="at-checkout-demo-note"
                className="btn-primary mt-3 w-full !opacity-70"
                title={t("Nothing is charged here. Payment happens when you check out.")}
              >
                {t("Continue to checkout")}
              </button>
            )}
            <p
              id="at-checkout-demo-note"
              className="mt-2 text-center text-[11px] text-(--ink-soft)/80"
            >
              {t("Nothing is charged here. Payment happens when you check out.")}
            </p>
            <p className="mt-1 text-center text-[11px] text-(--ink-soft)/80">
              {payload.fulfillment_method === "pickup"
                ? t("Will-call pickup at the venue box office.")
                : t("Mobile tickets are added to your wallet at purchase.")}
            </p>
          </>
        ) : (
          <p className="mt-3 text-center text-[11px] text-(--ink-soft)/80">
            {t("Ask ACME Assistant to check out before the timer ends, or let the hold lapse and the seats go back on sale. Nothing is charged here.")}
          </p>
        )}
      </div>
    </Stub>
  );
}
