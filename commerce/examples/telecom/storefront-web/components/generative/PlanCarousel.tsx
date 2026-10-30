// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** Renders present_products. */

import { useRef, useState } from "react";
import { formatDate, hasOptions, optionSummary, optionValuesLabel, type Translate, useStoreFrame, useT } from "web-shared";
import { formatPrice, formatPriceWithUnit, plateGlyph, plateTint } from "@/lib/format";
import { useOverflow } from "@/lib/overflow";
import type { AccountContext, Product, ProductsPayload } from "@/lib/types";
import { Frame, Rating } from "./shared";

const SPEC_KEYS: [string, (v: string, t: Translate) => string][] = [
  ["data_allowance_gb", (v, t) => (v === "unlimited" ? t("Unlimited data") : t("{value}GB data", { value: v }))],
  ["hotspot_gb", (v, t) => (v === "0" ? "" : t("{value}GB hotspot", { value: v }))],
  ["storage_gb", (v) => (v === "0" ? "" : `${v}GB`)],
  ["battery_hours", (v, t) => t("{value}h battery", { value: v })],
  ["screen_in", (v) => `${v.split(" ")[0]}″`],
  ["speed_tier", (v) => v],
  ["typical_latency_ms", (v, t) => t("{value}ms latency", { value: v })],
  ["contract_term", (v, t) => (v === "none" ? t("No contract") : v)],
  ["price_guarantee", (v) => (v === "none" ? "" : v)],
  ["connectivity", (v) => v],
];

/** A device with options leads with what is still to choose; a variant with what it chose. */
function specChips(product: Product, t: Translate): string[] {
  const attrs = product.attributes ?? {};
  const optionLine = optionValuesLabel(product) || optionSummary(product);
  const chips: string[] = optionLine ? [optionLine] : [];
  for (const [key, render] of SPEC_KEYS) {
    const raw = attrs[key];
    if (!raw) continue;
    const label = render(raw, t);
    if (label) chips.push(label);
    if (chips.length >= 3) break;
  }
  return chips;
}

/** Plan and fiber changes are contractual; only devices and add-ons add directly. */
function isDirectAddable(product: Product): boolean {
  if (product.category) return product.category === "devices" || product.category === "add-ons";
  return /^AM-(DEV|ADD)-/.test(product.product_id);
}

/**
 * An onAdd that resolves `false` means the server rejected the write. A device with options
 * (storage, color) is not added from the card: the button hands the choice to the assistant.
 */
function AddButton({
  product,
  onAdd,
}: {
  product: Product;
  onAdd: (product: Product) => boolean | void | Promise<boolean | void>;
}) {
  const [phase, setPhase] = useState<"idle" | "busy" | "done" | "error">("idle");
  const { ask } = useStoreFrame();
  const t = useT();
  if (hasOptions(product)) {
    return (
      <button
        type="button"
        onClick={(event) => {
          event.stopPropagation();
          ask(t("Add the {title} ({id}) to my order.", { title: product.title, id: product.product_id }));
        }}
        aria-label={t("Choose options for {title}", { title: product.title })}
        className="absolute bottom-2 right-2 flex h-8 w-8 items-center justify-center rounded-full bg-(--ink) text-lg font-semibold leading-none text-(--surface) shadow-sm transition-all hover:scale-105"
      >
        +
      </button>
    );
  }
  return (
    <button
      type="button"
      onClick={async (event) => {
        event.stopPropagation();
        if (phase !== "idle") return;
        setPhase("busy");
        const added = (await onAdd(product)) !== false;
        setPhase(added ? "done" : "error");
        window.setTimeout(() => setPhase("idle"), added ? 1200 : 1600);
      }}
      aria-label={t("Add {title} to order", { title: product.title })}
      className={`absolute bottom-2 right-2 flex h-8 w-8 items-center justify-center rounded-full text-lg font-semibold leading-none text-(--surface) shadow-sm transition-all hover:scale-105 ${
        phase === "done" ? "bg-(--accent)" : phase === "error" ? "bg-(--warn)" : "bg-(--ink)"
      } ${phase === "busy" ? "animate-pulse" : ""}`}
    >
      {phase === "done" ? "✓" : phase === "error" ? "!" : "+"}
    </button>
  );
}

function ContractRail({ account }: { account: AccountContext }) {
  const t = useT();
  const { contract, device } = account;
  const earlyOpen = Boolean(account.upgrade_eligibility?.eligible);
  const paymentsLeft = device.installments_remaining;
  return (
    <div className="border-b border-(--line) bg-(--well)/50 px-4 py-3">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4">
        <p className="am-meta">{t("Device agreement: {name}", { name: device.name })}</p>
        <p className="am-mono text-[11px] font-semibold text-(--ink)">
          {t("month {month} of {total}", { month: contract.month, total: contract.of_months })}
        </p>
      </div>
      <div className="relative mt-2 flex h-[10px] items-stretch gap-[2px]" aria-hidden>
        {Array.from({ length: contract.of_months }).map((_, index) => (
          <span
            key={index}
            className={`flex-1 ${index < contract.month ? "bg-(--ink)" : "bg-(--line)"}`}
          />
        ))}
        <span
          className="absolute -bottom-[3px] -top-[3px] w-[2.5px] bg-(--accent)"
          style={{ left: `${Math.min(contract.month / contract.of_months, 1) * 100}%` }}
        />
      </div>
      <p className="am-mono mt-2 text-[11px] leading-relaxed text-(--ink-soft)">
        {contract.early_upgrade_on ? (
          <span className={earlyOpen ? "font-semibold text-(--accent)" : undefined}>
            {earlyOpen ? t("✓ early upgrade open") : t("early upgrade {date}", { date: formatDate(contract.early_upgrade_on) })}
          </span>
        ) : null}
        {contract.early_upgrade_on ? " · " : null}
        <span className="font-semibold text-(--ink)">
          {t("you are here")}
          {paymentsLeft > 0 && device.installment_usd ? (
            <>
              {" "}
              · {paymentsLeft === 1 ? t("{n} payment left", { n: paymentsLeft }) : t("{n} payments left", { n: paymentsLeft })} ·{" "}
              {formatPrice(device.installment_usd)}
            </>
          ) : null}
        </span>
        {" · "}
        <span>{t("outright unlocks {date}", { date: formatDate(contract.ends) })}</span>
      </p>
    </div>
  );
}

function AppraisalStub({ tradeIn }: { tradeIn: NonNullable<AccountContext["trade_in_estimate"]> }) {
  const t = useT();
  return (
    <div className="flex flex-wrap items-center justify-between gap-x-6 gap-y-2 border-b-2 border-dashed border-(--line) bg-(--well)/50 px-4 py-3">
      <div className="min-w-0">
        <p className="am-meta">{t("Trade-in appraisal")}</p>
        <p className="mt-0.5 text-[14px] font-bold leading-tight text-(--ink)">
          {t("{device} · Tier {tier}", { device: tradeIn.device, tier: tradeIn.tier })}
        </p>
        <p className="mt-0.5 max-w-sm text-[11px] leading-snug text-(--ink-soft)">
          {tradeIn.condition_assumption}
        </p>
      </div>
      <div className="text-right">
        <p className="am-mono text-[26px] font-semibold leading-none tracking-tight text-(--ink)">
          {formatPrice(tradeIn.estimated_credit_usd)}
        </p>
        <p className="am-mono mt-1.5 inline-block border border-(--ink) px-1.5 py-0.5 text-[9.5px] font-semibold uppercase tracking-[0.08em] text-(--ink)">
          {t("Quote valid through {date}", { date: formatDate(tradeIn.quote_valid_through) })}
        </p>
      </div>
    </div>
  );
}

function SkeletonCard() {
  return (
    <div className="am-card-sm flex w-[200px] shrink-0 flex-col overflow-hidden">
      <div className="am-shimmer h-[110px] rounded-none" />
      <div className="flex flex-col gap-2 p-3">
        <div className="am-shimmer h-4 w-3/4" />
        <div className="am-shimmer h-3 w-2/5" />
        <div className="flex gap-1">
          <div className="am-shimmer h-5 w-16" />
          <div className="am-shimmer h-5 w-20" />
        </div>
      </div>
    </div>
  );
}

export default function PlanCarousel({
  payload,
  onAdd,
  partial,
  account,
}: {
  payload: ProductsPayload;
  onAdd?: (product: Product) => boolean | void | Promise<boolean | void>;
  partial?: boolean;
  account?: AccountContext | null;
}) {
  const t = useT();
  const items = payload.items ?? [];
  // Upgrade context applies to device shelves only.
  const showsDevices = items.some(
    ({ product }) => product.category === "devices" || /-DEV-/.test(product.product_id),
  );
  const scrollerRef = useRef<HTMLDivElement>(null);
  const { overflow, sync: syncOverflow } = useOverflow(
    scrollerRef,
    `${items.length}-${partial}`,
  );
  const nudge = (direction: 1 | -1) => {
    const node = scrollerRef.current;
    node?.scrollBy({ left: direction * (node.clientWidth - 80), behavior: "smooth" });
  };
  return (
    <Frame
      component="products"
      label={payload.title ?? t("From the catalog")}
      flush
    >
      {account && showsDevices ? <ContractRail account={account} /> : null}
      {account && showsDevices && account.trade_in_estimate ? (
        <AppraisalStub tradeIn={account.trade_in_estimate} />
      ) : null}
      <div className="relative">
        <div ref={scrollerRef} onScroll={syncOverflow} className="panel-scroll flex gap-3 overflow-x-auto p-4">
        {items.map(({ product, reason }, index) => (
          <article
            key={product.product_id}
            className="am-card-sm am-sharpen am-reveal-item flex w-[200px] shrink-0 flex-col overflow-hidden"
            style={{ animationDelay: `${index * 60}ms` }}
          >
            <div className="am-plate relative h-[110px]">
              <div className="absolute inset-0" style={{ background: plateTint(product) }} aria-hidden />
              <span className="am-plate-glyph" style={{ fontSize: 40 }}>
                {plateGlyph(product)}
              </span>
              <span className="am-plate-id">{product.product_id}</span>
              {product.labels?.[0] ? (
                <span className="am-tag am-tag--ink absolute right-2 top-2">{product.labels[0]}</span>
              ) : null}
              {product.in_stock === false ? (
                <span className="am-tag am-tag--warn absolute left-2 top-2">{t("Out of stock")}</span>
              ) : null}
              {onAdd && isDirectAddable(product) && product.in_stock !== false ? (
                <AddButton product={product} onAdd={onAdd} />
              ) : null}
            </div>
            <div className="flex flex-1 flex-col gap-1.5 p-3">
              <div className="flex items-start justify-between gap-2">
                <h3 className="text-[15px] font-bold leading-tight text-(--ink)">
                  {product.title}
                </h3>
                <span className="am-mono shrink-0 text-[14px] font-semibold text-(--ink)">
                  {hasOptions(product) ? <span className="text-[11px] font-normal text-(--ink-soft)">{t("from")} </span> : null}
                  {formatPriceWithUnit(product)}
                </span>
              </div>
              <Rating rating={product.rating} count={product.review_count} />
              <div className="flex flex-wrap gap-1">
                {specChips(product, t).map((chip) => (
                  <span key={chip} className="am-tag normal-case tracking-normal">
                    {chip}
                  </span>
                ))}
              </div>
              {reason ? (
                <p className="mt-auto pt-1 text-[13px] leading-snug text-(--ink-soft)">
                  {reason}
                </p>
              ) : null}
            </div>
          </article>
        ))}
          {partial ? <SkeletonCard /> : null}
        </div>
        {overflow.left ? (
          <>
            <div
              aria-hidden
              className="pointer-events-none absolute inset-y-0 left-0 w-10 bg-gradient-to-r from-(--surface) to-transparent"
            />
            <button
              type="button"
              onClick={() => nudge(-1)}
              aria-label={t("Scroll to previous products")}
              className="am-mono absolute left-1 top-1/2 -translate-y-1/2 rounded-(--radius) border border-(--line) bg-(--surface) px-2 py-1 text-sm text-(--ink) shadow-md transition hover:border-(--accent)"
            >
              ‹
            </button>
          </>
        ) : null}
        {overflow.right ? (
          <>
            <div
              aria-hidden
              className="pointer-events-none absolute inset-y-0 right-0 w-10 bg-gradient-to-l from-(--surface) to-transparent"
            />
            <button
              type="button"
              onClick={() => nudge(1)}
              aria-label={t("Scroll to more products")}
              className="am-mono absolute right-1 top-1/2 -translate-y-1/2 rounded-(--radius) border border-(--line) bg-(--surface) px-2 py-1 text-sm text-(--ink) shadow-md transition hover:border-(--accent)"
            >
              ›
            </button>
          </>
        ) : null}
      </div>
    </Frame>
  );
}
