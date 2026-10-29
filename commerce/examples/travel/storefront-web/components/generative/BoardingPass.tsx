// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import type { CSSProperties } from "react";
import { formatPrice, quantityLabel } from "@/lib/format";
import type { CheckoutPayload } from "@/lib/types";
import { PostcardWindow } from "../PostcardWindow";
import { BODY, CARD, DISPLAY, META, display } from "./shared";
import { safeHandoffs, useT } from "web-shared";

/** Keyed by the checkout tool's fulfillment enum. */
const FULFILLMENT_LABELS: Record<string, string> = {
  delivery: "E-ticket",
  shipping: "E-ticket",
  pickup: "Confirmation",
};

function fulfillmentLabel(method?: string): string {
  if (!method) return "E-ticket";
  return FULFILLMENT_LABELS[method] ?? "Confirmation";
}

const NOTCH: CSSProperties = {
  background: "var(--well)",
  boxShadow: "inset 0 1px 2px rgba(31,61,51,0.18)",
};

const BARCODE: CSSProperties = {
  backgroundImage:
    "repeating-linear-gradient(90deg, var(--surface) 0px, var(--surface) 2px, transparent 2px, transparent 5px)," +
    "repeating-linear-gradient(90deg, var(--surface) 0px, var(--surface) 1px, transparent 1px, transparent 7px)",
};

export default function BoardingPass({ payload }: { payload: CheckoutPayload }) {
  const t = useT();
  const cart = payload.cart;
  const handoffs = safeHandoffs(payload.handoffs);
  const items = cart?.items ?? [];
  return (
    <section className="al-reveal" data-checkout-card>
      <div className="flex overflow-hidden" style={CARD}>
        <div className="min-w-0 flex-1 p-6">
          <div style={META}>{t("Boarding pass · not charged")}</div>
          <h3 className="mt-1" style={display(20, 600)}>
            {t("Your trip, ready to book")}
          </h3>
          {payload.note ? (
            <p
              className="mt-1"
              style={{
                fontFamily: BODY,
                fontSize: 13,
                lineHeight: 1.5,
                color: "var(--ink-soft)",
              }}
            >
              {payload.note}
            </p>
          ) : null}

          <div className="mt-4 space-y-2">
            {items.map((item, i) => (
              <div
                key={item.product_id}
                className="al-reveal-item flex items-center justify-between gap-3"
                style={{
                  animationDelay: `${i * 70}ms`,
                  fontFamily: BODY,
                  fontSize: 15,
                  color: "var(--ink)",
                }}
              >
                <PostcardWindow
                  title={item.title}
                  className="h-10 w-10 shrink-0 !rounded-lg"
                />
                <span className="min-w-0 flex-1 truncate" title={item.title}>
                  {item.title}
                  {item.quantity > 1 ? ` ${quantityLabel(item.product_id, item.quantity, t)}` : ""}
                </span>
                <span className="shrink-0">{formatPrice(item.line_total)}</span>
              </div>
            ))}
            {!items.length ? (
              <p style={{ fontFamily: BODY, fontSize: 13, color: "var(--ink-soft)" }}>
                {t("Your trip basket is empty.")}
              </p>
            ) : null}
          </div>

          <div
            className="mt-3 flex items-baseline justify-between border-t pt-3"
            style={{ borderColor: "var(--line)" }}
          >
            <span style={META}>
              {t("Total")}
              <span style={{ display: "block", fontSize: 11, opacity: 0.8, textTransform: "none", letterSpacing: 0 }}>
                {t("all-in, fees included; final total confirmed at checkout")}
              </span>
            </span>
            <span style={{ fontFamily: DISPLAY, fontWeight: 700, fontSize: 26, color: "var(--accent)" }}>
              {formatPrice(cart?.subtotal ?? 0)}
            </span>
          </div>

          {handoffs.length ? (
            // The backend named where payment happens (a hosted checkout URL, or one per seller).
            <div className="mt-4 flex flex-col gap-2">
              {handoffs.map((h) => (
                <a
                  key={h.url}
                  href={h.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  aria-describedby="al-boarding-pass-demo-note"
                  className="w-full rounded-full py-2.5 text-center"
                  style={{
                    background: "var(--accent)",
                    color: "var(--surface)",
                    fontFamily: BODY,
                    fontWeight: 600,
                    fontSize: 15,
                  }}
                >
                  {h.label ?? (h.seller ? t("Continue to checkout with {seller}", { seller: h.seller }) : t("Continue to checkout"))}
                </a>
              ))}
            </div>
          ) : (
            // Disabled so assistive tech skips it.
            <button
              type="button"
              disabled
              aria-describedby="al-boarding-pass-demo-note"
              className="mt-4 w-full cursor-not-allowed rounded-full py-2.5"
              style={{
                background: "var(--accent)",
                color: "var(--surface)",
                fontFamily: BODY,
                fontWeight: 600,
                fontSize: 15,
                opacity: 0.92,
              }}
            >
              {t("Continue to checkout")}
            </button>
          )}
          <p
            id="al-boarding-pass-demo-note"
            className="mt-2 text-center"
            style={{ fontFamily: BODY, fontSize: 12, color: "var(--ink-soft)" }}
          >
            {t("Nothing is charged here. Payment happens when you check out.")}
          </p>
        </div>

        <div
          aria-hidden
          className="relative w-0 self-stretch"
          style={{ borderLeft: "2px dashed rgba(31,61,51,0.28)" }}
        >
          <span className="absolute -left-[9px] -top-[9px] h-[18px] w-[18px] rounded-full" style={NOTCH} />
          <span className="absolute -bottom-[9px] -left-[9px] h-[18px] w-[18px] rounded-full" style={NOTCH} />
        </div>

        <div
          className="al-stub-snap relative flex w-[120px] shrink-0 flex-col items-center justify-between gap-4 p-4"
          style={{ background: "var(--ink)", color: "var(--surface)" }}
        >
          <span
            style={{
              writingMode: "vertical-rl",
              transform: "rotate(180deg)",
              fontFamily: DISPLAY,
              fontStyle: "italic",
              fontWeight: 650,
              fontSize: 18,
              letterSpacing: "0.18em",
            }}
          >
            ACME TRAVEL
          </span>
          {/* In normal flow, so it overlaps neither neighbor at any pass height. */}
          <span
            aria-hidden
            className="al-passport-stamp al-stamp-thump -mr-2 self-end"
            style={{ color: "rgba(247,243,236,0.88)", fontSize: 10, letterSpacing: "0.13em" }}
          >
            <span>{t("Not")}</span>
            <span>{t("charged")}</span>
          </span>
          <div className="flex w-full flex-col items-center gap-3">
            <span
              style={{
                fontFamily: BODY,
                fontSize: 11,
                fontWeight: 600,
                textTransform: "uppercase",
                letterSpacing: "0.12em",
                color: "rgba(247,243,236,0.75)",
              }}
            >
              {t(fulfillmentLabel(payload.fulfillment_method))}
            </span>
            <div aria-hidden className="h-10 w-full" style={BARCODE} />
          </div>
        </div>
      </div>
    </section>
  );
}
