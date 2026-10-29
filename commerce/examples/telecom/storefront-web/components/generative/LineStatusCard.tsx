// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** Renders present_order_status. */

import { formatDate, orderStatusLabel, useT } from "web-shared";
import { formatPrice } from "@/lib/format";
import type { OrderStatusPayload } from "@/lib/types";
import { Frame } from "./shared";

const STATUS_STYLE: Record<string, { className: string; pulse?: boolean }> = {
  delivered: { className: "am-tag--accent" },
  shipped: { className: "am-tag--accent", pulse: true },
  processing: { className: "", pulse: true },
  cancelled: { className: "am-tag--warn" },
  refunded: { className: "am-tag--warn" },
};

export default function LineStatusCard({ payload }: { payload: OrderStatusPayload }) {
  const t = useT();
  const order = payload.order;
  const status = (order?.status ?? "processing").toLowerCase();
  const style = STATUS_STYLE[status] ?? {};

  return (
    <Frame component="order_status" label={t("Order {id}", { id: payload.order_id })}>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <span className={`am-tag ${style.className} !px-3 !py-1.5 !text-[12px]`}>
          {style.pulse ? <span className="am-live" aria-hidden /> : <span aria-hidden>■</span>}
          {orderStatusLabel(status)}
        </span>
        {order?.estimated_delivery ? (
          <p className="am-mono text-[13px] text-(--ink-soft)">
            {t("ETA")} <span className="font-semibold text-(--ink)">{formatDate(order.estimated_delivery)}</span>
          </p>
        ) : null}
      </div>

      <p className="mt-3 text-[15px] leading-relaxed text-(--ink)">{payload.summary}</p>

      {order?.items?.length ? (
        <div className="am-rule mt-3 pt-2">
          {order.items.map((item) => (
            <div
              key={item.product_id}
              className="flex items-baseline justify-between gap-3 py-1 text-[14px]"
            >
              <span className="min-w-0 truncate text-(--ink)">
                {item.title}
                {item.quantity > 1 ? (
                  <span className="am-mono text-(--ink-soft)"> × {item.quantity}</span>
                ) : null}
              </span>
              <span className="am-mono shrink-0 text-(--ink)">
                {formatPrice(item.price * item.quantity)}
              </span>
            </div>
          ))}
          <div className="am-rule-bold mt-1 flex items-baseline justify-between pt-1.5">
            <span className="am-meta">{t("Total")}</span>
            <span className="am-mono text-[15px] font-semibold text-(--ink)">
              {formatPrice(order.total, order.currency)}
            </span>
          </div>
        </div>
      ) : null}

      {payload.next_step ? (
        <p className="mt-3 border-l-2 border-(--accent) pl-3 text-[14px] font-medium text-(--ink)">
          {payload.next_step}
        </p>
      ) : null}
    </Frame>
  );
}
