// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useT } from "web-shared";
import { formatPrice } from "@/lib/format";
import type { OrderStatusPayload } from "@/lib/types";
import { BODY, CARD, DISPLAY, META, display } from "./shared";

const ALERT_STATUSES = new Set(["delayed", "cancelled"]);

// The shared order pipeline's parcel statuses, translated into booking language.
const BOOKING_STATUS_LABELS: Record<string, string> = {
  shipped: "confirmed",
  out_for_delivery: "confirmed",
  delivered: "completed",
  return_initiated: "refund requested",
};

/** Date-only input gets a local noon so the day is stable across timezones. */
function formatEta(raw: string): string {
  const timestamp = Date.parse(/^\d{4}-\d{2}-\d{2}$/.test(raw) ? `${raw}T12:00:00` : raw);
  if (Number.isNaN(timestamp)) return raw;
  const date = new Date(timestamp);
  const weekday = date.toLocaleDateString("en-US", { weekday: "short" });
  const month = date.toLocaleDateString("en-US", { month: "short" });
  return `${weekday} ${date.getDate()} ${month}`;
}

function StatusStamp({ status }: { status: string }) {
  const t = useT();
  const alert = ALERT_STATUSES.has(status);
  const color = alert ? "var(--accent)" : "var(--ink)";
  return (
    <span
      className="al-passport-stamp shrink-0"
      style={{
        transform: "rotate(-3deg)",
        color,
        fontFamily: BODY,
        fontSize: 12,
        letterSpacing: "0.14em",
      }}
    >
      {t((BOOKING_STATUS_LABELS[status] ?? status).replaceAll("_", " "))}
    </span>
  );
}

export default function BookingStatusCard({ payload }: { payload: OrderStatusPayload }) {
  const t = useT();
  const order = payload.order;
  return (
    <section className="al-reveal" style={{ ...CARD, padding: 24 }}>
      <div className="flex items-start justify-between gap-3">
        <div>
          <div style={META}>{t("Booking")}</div>
          <h3 className="mt-0.5" style={display(20, 600)}>
            {payload.order_id}
          </h3>
        </div>
        <StatusStamp status={order?.status ?? "processing"} />
      </div>

      <p
        className="al-reveal-item mt-3"
        style={{ fontFamily: BODY, fontSize: 15, lineHeight: 1.6, color: "var(--ink)" }}
      >
        {payload.summary}
      </p>

      {order ? (
        <div
          className="al-reveal-item mt-3"
          style={{
            animationDelay: "70ms",
            background: "var(--well)",
            borderRadius: "var(--radius)",
            padding: 14,
          }}
        >
          {order.items.map((item) => (
            <div
              key={item.product_id}
              className="flex items-baseline justify-between gap-3 py-0.5"
              style={{ fontFamily: BODY, fontSize: 15, color: "var(--ink)" }}
            >
              <span className="truncate">
                {item.title}
                {item.quantity > 1 ? ` × ${item.quantity}` : ""}
              </span>
              <span className="shrink-0" style={{ color: "var(--ink-soft)" }}>
                {formatPrice(item.price * item.quantity)}
              </span>
            </div>
          ))}
          <div
            className="mt-1.5 flex items-baseline justify-between border-t pt-1.5"
            style={{ borderColor: "var(--line)" }}
          >
            <span style={META}>{t("Total")}</span>
            <span style={{ fontFamily: DISPLAY, fontWeight: 700, fontSize: 17, color: "var(--ink)" }}>
              {formatPrice(order.total)}
            </span>
          </div>
          {order.estimated_delivery ? (
            <div className="mt-1.5" style={{ ...META, fontSize: 11 }}>
              {t("ETA · {date}", { date: formatEta(order.estimated_delivery) })}
            </div>
          ) : null}
        </div>
      ) : null}

      {payload.next_step ? (
        <p
          className="al-reveal-item mt-3"
          style={{
            animationDelay: "140ms",
            fontFamily: BODY,
            fontSize: 15,
            fontWeight: 600,
            color: "var(--ink)",
          }}
        >
          <span aria-hidden style={{ color: "var(--accent)" }}>
            →{" "}
          </span>
          {payload.next_step}
        </p>
      ) : null}
    </section>
  );
}
