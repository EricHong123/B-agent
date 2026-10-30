// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { Fragment } from "react";
import { formatDate, formatMoney, type Locale, useLocale, useT } from "web-shared";
import type { OrderStatusPayload } from "@/lib/types";

/** Rail stages reached; statuses absent here render no rail. */
const RAIL_PROGRESS: Record<string, number> = {
  processing: 1,
  shipped: 3,
  delayed: 3,
  out_for_delivery: 3,
  delivered: 4,
};

const RAIL_STAGES = ["Ordered", "Packed", "Shipped", "Delivered"] as const;

function shortDay(iso: string, locale: Locale): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!match) return iso;
  // Parsed by parts so the local timezone can't shift it a day.
  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]));
  return new Intl.DateTimeFormat(locale === "zh" ? "zh-CN" : "en-US", { month: "short", day: "numeric" }).format(date);
}

function DeliveryRail({ order }: { order: NonNullable<OrderStatusPayload["order"]> }) {
  const { locale, t } = useLocale();
  const reached = RAIL_PROGRESS[order.status];
  if (reached == null) return null;
  const delayed = order.status === "delayed";
  // In the estimate string the first ISO date is the current estimate; a second one is the
  // missed original.
  const estimateDates = [...(order.estimated_delivery ?? "").matchAll(/\d{4}-\d{2}-\d{2}/g)].map(
    (match) => match[0],
  );
  const estimate = estimateDates[0];
  const original = delayed ? estimateDates[1] : undefined;
  const deliveredOn = order.status === "delivered" ? estimate : undefined;

  return (
    <div className="mt-3" data-delivery-rail>
      <div className="flex items-center">
        {RAIL_STAGES.map((stage, index) => {
          const complete = index < reached;
          const isDelaySegment = delayed && index === RAIL_STAGES.length - 1;
          return (
            <Fragment key={stage}>
              {index > 0 ? (
                <div
                  className={`relative h-1 flex-1 rounded-full ${
                    index < reached
                      ? "bg-(--ok)"
                      : isDelaySegment
                        ? "bg-(--warn)/50"
                        : "bg-(--well)"
                  }`}
                >
                  {isDelaySegment ? (
                    <span
                      className="absolute left-1/2 top-1/2 -translate-x-1/2 -translate-y-1/2 whitespace-nowrap rounded-full bg-(--warn-soft) px-2 py-0.5 text-[11px] font-semibold text-(--warn)"
                      title={t("The original delivery estimate was missed")}
                    >
                      {t("delayed")}
                    </span>
                  ) : null}
                </div>
              ) : null}
              <div
                className={`flex h-4 w-4 shrink-0 items-center justify-center rounded-full text-[9px] font-bold ${
                  complete
                    ? "bg-(--ok) text-(--surface)"
                    : index === reached
                      ? "border-2 border-(--ok) bg-(--card)"
                      : "border-2 border-(--line) bg-(--card)"
                }`}
                aria-hidden
              >
                {complete ? "✓" : ""}
              </div>
            </Fragment>
          );
        })}
      </div>
      <div className="mt-1.5 flex justify-between text-[11px] leading-tight">
        {RAIL_STAGES.map((stage, index) => {
          const complete = index < reached;
          const last = index === RAIL_STAGES.length - 1;
          return (
            <div
              key={stage}
              className={`${index === 0 ? "text-left" : last ? "text-right" : "text-center"} ${
                complete ? "font-semibold text-(--ink)" : "text-(--ink-soft)"
              }`}
            >
              <div>{t(stage)}</div>
              {index === 0 && order.placed_at ? (
                <div className="font-normal text-(--ink-soft)">{shortDay(order.placed_at, locale)}</div>
              ) : null}
              {last && deliveredOn ? (
                <div className="font-normal text-(--ink-soft)">{shortDay(deliveredOn, locale)}</div>
              ) : null}
              {last && !deliveredOn && estimate ? (
                <div className="font-normal">
                  {original ? (
                    <s className="text-(--ink-soft)/80">{shortDay(original, locale)}</s>
                  ) : null}{" "}
                  <span className={original ? "font-bold text-(--warn)" : "text-(--ink-soft)"}>
                    {shortDay(estimate, locale)}
                  </span>
                </div>
              ) : null}
            </div>
          );
        })}
      </div>
    </div>
  );
}

const STATUS_STYLES: Record<string, string> = {
  processing: "bg-(--well) text-(--ink)",
  shipped: "bg-(--info-soft) text-(--info)",
  out_for_delivery: "bg-(--accent-soft) text-(--ink)",
  delivered: "bg-(--ok-soft) text-(--ok)",
  delayed: "bg-(--warn-soft) text-(--warn)",
  cancelled: "bg-(--well) text-(--ink-soft)",
  return_initiated: "bg-(--violet-soft) text-(--violet)",
  refunded: "bg-(--ok-soft) text-(--ok)",
};

export default function OrderStatusCard({ payload }: { payload: OrderStatusPayload }) {
  const t = useT();
  const order = payload.order;
  // Adopters swap backends, so only http(s) tracking links render.
  const trackingHref =
    order?.tracking_url && /^https?:\/\//i.test(order.tracking_url) ? order.tracking_url : null;
  const status = order?.status ?? "processing";
  return (
    <section className="rounded-2xl border border-(--line) bg-(--card) p-4 shadow-(--shadow-sm)">
      <div className="flex items-center justify-between gap-2">
        <h3 className="text-[15px] font-semibold text-(--ink)">{t("Order {id}", { id: payload.order_id })}</h3>
        <span className={`rounded-full px-2.5 py-0.5 text-[13px] font-medium ${STATUS_STYLES[status] ?? STATUS_STYLES.processing}`}>
          {t(status.replaceAll("_", " "))}
        </span>
      </div>
      <p className="mt-2 text-[15px] leading-relaxed text-(--ink)">{payload.summary}</p>
      {order ? <DeliveryRail order={order} /> : null}
      {order ? (
        <div className="mt-3 space-y-1 rounded-lg bg-(--well)/60 p-3 text-sm">
          {order.items.map((item) => (
            <div key={item.product_id} className="flex justify-between gap-2">
              <span className="truncate text-(--ink)">
                {item.title} × {item.quantity}
              </span>
              <span className="shrink-0 text-(--ink-soft)">{formatMoney(item.price * item.quantity)}</span>
            </div>
          ))}
          <div className="flex justify-between border-t border-(--line) pt-1 font-medium text-(--ink)">
            <span>{t("Total")}</span>
            <span>{formatMoney(order.total, order.currency)}</span>
          </div>
          {order.estimated_delivery && RAIL_PROGRESS[status] == null ? (
            // The rail shows the estimate for its own statuses; this line covers the rest.
            <div className="text-[13px] text-(--ink-soft)">
              {t("Estimated delivery: {date}", { date: formatDate(order.estimated_delivery) })}
            </div>
          ) : null}
        </div>
      ) : null}
      {trackingHref ? (
        <a
          href={trackingHref}
          target="_blank"
          rel="noreferrer"
          className="mt-3 inline-flex items-center gap-1.5 rounded-lg border border-(--line) px-3 py-1.5 text-[13px] font-semibold text-(--ink) transition hover:border-(--accent) hover:shadow-(--shadow-sm)"
        >
          {t("Track package")}
          <span aria-hidden>↗</span>
        </a>
      ) : null}
      {payload.next_step ? (
        <p className="mt-2 text-[15px] font-medium text-(--ink)">{payload.next_step}</p>
      ) : null}
    </section>
  );
}
