// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { formatMoney, orderStatusLabel, useT } from "web-shared";
import type { OrderStatusPayload } from "@/lib/types";
import { Stub } from "./shared";

export default function OrderCard({ payload }: { payload: OrderStatusPayload }) {
  const t = useT();
  const order = payload.order;
  return (
    <Stub component="order_status" label={t("Order {id}", { id: payload.order_id })}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="text-[15px] leading-snug text-(--ink)">{payload.summary}</p>
        {order ? <span className="at-pill at-pill--calm">{orderStatusLabel(order.status)}</span> : null}
      </div>
      {order ? (
        <div className="at-perf mt-3 pt-3">
          <div className="space-y-1">
            {order.items.map((item) => (
              <div key={item.product_id} className="flex items-baseline justify-between gap-3">
                <span className="min-w-0 truncate text-[14px] text-(--ink)">
                  {item.title}
                  <span className="at-mono ml-1.5 text-[11px] text-(--ink-soft)">
                    × {item.quantity}
                  </span>
                </span>
                <span className="at-mono shrink-0 text-[14px] text-(--ink)">
                  {formatMoney(item.price * item.quantity)}
                </span>
              </div>
            ))}
          </div>
          <div className="mt-2 flex items-baseline justify-between border-t border-(--line) pt-2">
            <span className="text-[14px] font-bold text-(--ink)">{t("Total, all-in")}</span>
            <span className="at-mono text-[17px] font-bold text-(--ink)">
              {formatMoney(order.total, order.currency)}
            </span>
          </div>
          {order.estimated_delivery ? (
            <p className="mt-2 text-[12px] text-(--ink-soft)">{order.estimated_delivery}</p>
          ) : null}
        </div>
      ) : null}
      {payload.next_step ? (
        <p className="mt-2 text-[13px] font-medium text-(--ink)">{payload.next_step}</p>
      ) : null}
    </Stub>
  );
}
