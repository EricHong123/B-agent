// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** Renders checkout as an activation ticket. */

import { safeHandoffs, useCatalogIndex, useT } from "web-shared";
import PlanTile from "@/components/PlanTile";
import { fetchProducts } from "@/lib/api";
import { billAfterOrder, formatPrice, priceUnitOf, splitCart } from "@/lib/format";
import { useCountUp } from "@/lib/motion";
import type { AccountContext, CheckoutPayload } from "@/lib/types";
import { Frame } from "./shared";

/** The stamp lands after the QR assembly and count-up finish. */
const QR_ASSEMBLY_MS = 500;
const COUNT_MS = 400;

/** Decorative; scans nothing. */
function QrPlate({ seed }: { seed: string }) {
  let value = 7;
  for (let i = 0; i < seed.length; i++) value = (value * 31 + seed.charCodeAt(i)) >>> 0;
  const cells: { on: boolean; delayMs: number }[] = [];
  for (let i = 0; i < 81; i++) {
    value = (value * 1103515245 + 12345) >>> 0;
    cells.push({
      on: ((value >> 16) & 3) !== 0 ? (value & 1) === 1 : true,
      // Unsigned shift; a signed one can go negative and yield negative delays.
      delayMs: ((value >>> 8) % 81) * (QR_ASSEMBLY_MS / 81),
    });
  }
  return (
    <div
      className="grid aspect-square w-[88px] gap-[2px] border border-(--line) bg-(--surface) p-[6px]"
      style={{ gridTemplateColumns: "repeat(9, 1fr)" }}
      aria-hidden
    >
      {cells.map((cell, index) =>
        cell.on ? (
          <span key={index} className="am-dot bg-(--ink)" style={{ animationDelay: `${cell.delayMs}ms` }} />
        ) : (
          <span key={index} className="bg-transparent" />
        ),
      )}
    </div>
  );
}

function CountUpPrice({ value, suffix }: { value: number; suffix?: string }) {
  const animated = useCountUp(value, COUNT_MS);
  return (
    <p className="am-mono text-[24px] font-semibold leading-tight tracking-tight text-(--ink)">
      {formatPrice(Math.round(animated * 100) / 100)}
      {suffix ? <span className="text-[12px] text-(--ink-soft)">{suffix}</span> : null}
    </p>
  );
}

function BillDeltaStrip({
  bill,
}: {
  bill: { before: number; after: number; replacesPlan: boolean };
}) {
  const t = useT();
  const delta = Math.round((bill.after - bill.before) * 100) / 100;
  // The "after" figure counts from today's bill to its new value.
  const animatedDelta = useCountUp(delta, COUNT_MS);
  const after = Math.round((bill.before + animatedDelta) * 100) / 100;
  return (
    <div className="am-rule mt-3 pt-2.5">
      <div className="flex flex-wrap items-baseline justify-between gap-x-4 gap-y-1">
        <p className="am-meta">{t("Your bill")}</p>
        <p className="am-mono text-[13.5px] font-semibold text-(--ink)">
          {t("{before}/mo → {after}/mo", { before: formatPrice(bill.before), after: formatPrice(after) })}{" "}
          <span className={delta < 0 ? "text-(--accent)" : "text-(--ink-soft)"}>
            (
            {delta === 0
              ? t("no change")
              : t("{sign}{amount}/mo", { sign: delta > 0 ? "+" : "−", amount: formatPrice(Math.abs(delta)) })}
            )
          </span>
        </p>
      </div>
      <p className="mt-0.5 text-[11px] leading-snug text-(--ink-soft)">
        {bill.replacesPlan
          ? t("your current plan is replaced at activation; existing device installments continue unchanged")
          : t("added to your current bill; existing device installments continue unchanged")}
      </p>
    </div>
  );
}

export default function ActivationTicket({
  payload,
  account,
}: {
  payload: CheckoutPayload;
  account?: AccountContext | null;
}) {
  const t = useT();
  const handoffs = safeHandoffs(payload.handoffs);
  const catalog = useCatalogIndex(fetchProducts);
  const items = payload.cart?.items ?? [];
  const { monthly, today } = splitCart(items, catalog);
  const bill = billAfterOrder(account, items, catalog);

  return (
    <Frame
      component="checkout"
      label={t("Activation order for your confirmation")}
      flush
    >
      <div className="flex flex-col sm:flex-row">
        {/* Order body */}
        <div className="flex-1 p-4 sm:p-5">
          <div className="flex items-baseline justify-between">
            <h3 className="text-[16px] font-extrabold uppercase tracking-[0.04em] text-(--ink)">
              {t("Activation order")}
            </h3>
            <span
              className="am-stamp am-mono text-[11px] text-(--ink-soft)"
              style={{ animationDelay: `${QR_ASSEMBLY_MS + COUNT_MS - 200}ms` }}
            >
              {t("NOT CHARGED")}
            </span>
          </div>

          <div className="am-rule-bold mt-3">
            {items.map((item) => (
              <div key={item.product_id} className="am-rule py-2 first:border-t-0">
                <PlanTile
                  product={{ product_id: item.product_id, title: item.title, price: item.price }}
                  note={
                    item.quantity > 1 ? `${item.product_id} · × ${item.quantity}` : item.product_id
                  }
                  trailing={
                    <span className="am-mono shrink-0 text-[14px] font-semibold text-(--ink)">
                      {formatPrice(item.line_total)}
                      {priceUnitOf(item.product_id, catalog) === "per_month" ? (
                        <span className="text-[11px] font-normal text-(--ink-soft)">{t("/mo")}</span>
                      ) : null}
                    </span>
                  }
                />
              </div>
            ))}
          </div>

          <div className="am-rule-heavy mt-2 grid grid-cols-2 gap-3 pt-3">
            <div>
              <p className="am-meta">{t("Monthly")}</p>
              <CountUpPrice value={monthly} suffix={t("/mo")} />
            </div>
            <div>
              <p className="am-meta">{t("Due today")}</p>
              <CountUpPrice value={today} />
            </div>
          </div>

          {bill ? <BillDeltaStrip bill={bill} /> : null}

          {payload.note ? (
            <p className="mt-3 text-[13px] leading-snug text-(--ink-soft)">{payload.note}</p>
          ) : null}
        </div>

        {/* eSIM stub */}
        <div className="flex shrink-0 items-center justify-between gap-4 border-t-2 border-dashed border-(--line) bg-(--well)/60 p-4 sm:w-[180px] sm:flex-col sm:items-start sm:justify-center sm:border-l-2 sm:border-t-0 sm:p-5">
          <div>
            <p className="am-meta">{t("eSIM ready")}</p>
            <p className="mt-0.5 text-[11.5px] leading-snug text-(--ink-soft)">
              {t("Activates in minutes after you check out.")}
            </p>
          </div>
          <QrPlate seed={items.map((i) => i.product_id).join("|") || "acme-mobile"} />
        </div>
      </div>

      {handoffs.length ? (
        // The backend named where payment happens (a hosted checkout URL, or one per seller).
        <div className="flex flex-col gap-2 border-t border-(--line) px-4 py-3">
          {handoffs.map((h) => (
            <a
              key={h.url}
              href={h.url}
              target="_blank"
              rel="noopener noreferrer"
              aria-describedby="am-activation-demo-note"
              className="w-full rounded-(--radius) bg-(--ink) py-2.5 text-center text-[14px] font-semibold text-(--surface)"
            >
              {h.label ?? (h.seller ? t("Continue to checkout with {seller}", { seller: h.seller }) : t("Continue to checkout"))}
            </a>
          ))}
        </div>
      ) : null}

      <p
        id="am-activation-demo-note"
        className="border-t border-(--line) px-4 py-2 text-center text-[11px] font-medium text-(--ink-soft)"
      >
        {t("Nothing is charged here. Payment happens when you check out.")}
      </p>
    </Frame>
  );
}
