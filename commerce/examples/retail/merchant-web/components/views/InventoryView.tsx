// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { AskButton, formatNumber, KindIcon, MiniBar, Notice, optionValuesLabel, PageHeader, Panel, Pill, Skeleton, useResource, useT } from "web-shared";
import { fetchAlerts } from "@/lib/api";
import { INVENTORY_KINDS } from "@/lib/kinds";
import { coverText, pluralT } from "@/lib/labels";
import type { InventoryAlert } from "@/lib/types";

function AlertRow({ alert, onAskAssistant }: { alert: InventoryAlert; onAskAssistant: (text: string) => void }) {
  const t = useT();
  const style = INVENTORY_KINDS[alert.kind];
  const soldOut = alert.stock === 0;
  const low = alert.kind === "low_stock";
  const chosen = optionValuesLabel(alert);
  const name = chosen ? t("{title} in {options}", { title: alert.title, options: chosen }) : alert.title;
  const ref = `${name} (${alert.listing_id})`;
  const prompt = low ? t("Draft a restock plan for {ref}.", { ref }) : t("Plan a markdown for {ref}.", { ref });
  return (
    <li className="flex items-center gap-3 px-[18px] py-3">
      <KindIcon icon={style.icon} tone={soldOut ? "danger" : style.tone} />
      <div className="min-w-0 flex-1">
        <div className="text-[13.5px] font-medium leading-snug text-(--ink)">
          {alert.title}
          {chosen ? <span className="font-normal text-(--ink-soft)"> · {chosen}</span> : null}
        </div>
        <div className="mt-0.5 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[12.5px] tabular-nums text-(--ink-soft)">
          <span>{alert.listing_id}</span>
          {alert.sales_last_30d != null ? <span>· {t("{count} sold in 30 days", { count: formatNumber(alert.sales_last_30d) })}</span> : null}
          {low && alert.threshold != null ? <span>· {t("reorder at {count}", { count: formatNumber(alert.threshold) })}</span> : null}
          {low && alert.stock > 0 && alert.storefront_visible ? (
            <Pill tone="warn" dot>
              {t("Storefront shows “Only {count} left”", { count: formatNumber(alert.stock) })}
            </Pill>
          ) : null}
          {soldOut && alert.storefront_visible === false ? <span>· {t("hidden from the storefront")}</span> : null}
        </div>
      </div>
      <div className="w-32 shrink-0 whitespace-nowrap text-right tabular-nums">
        <div className={`text-[15px] font-semibold ${soldOut ? "text-(--danger)" : low ? "text-(--warn)" : "text-(--ink)"}`}>
          {soldOut ? "0" : formatNumber(alert.stock)}
          <span className="ml-1 text-[11.5px] font-medium text-(--ink-soft)">{t("in stock")}</span>
        </div>
        <div className="mt-0.5 flex items-center justify-end gap-1.5 text-[11.5px] text-(--ink-soft)">
          {/* Stock against the reorder threshold: empty at zero, full at twice the threshold. */}
          {low && alert.threshold ? <MiniBar value={alert.stock / (alert.threshold * 2)} tone={soldOut ? "danger" : "warn"} /> : null}
          {alert.days_of_cover != null && !soldOut ? <span>{coverText(t, alert.days_of_cover)}</span> : soldOut ? <span>{t("sold out")}</span> : null}
        </div>
      </div>
      <AskButton label={low ? t("Draft restock") : t("Plan markdown")} onClick={() => onAskAssistant(prompt)} />
    </li>
  );
}

export default function InventoryView({ refreshKey, onAskAssistant }: { refreshKey: number; onAskAssistant: (text: string) => void }) {
  const t = useT();
  const { data, failed } = useResource(fetchAlerts, [refreshKey]);

  const lowStock = (data?.inventory ?? [])
    .filter((alert) => alert.kind === "low_stock")
    .sort((a, b) => (a.days_of_cover ?? Infinity) - (b.days_of_cover ?? Infinity));
  const slowMovers = (data?.inventory ?? []).filter((alert) => alert.kind === "slow_mover");
  const tiedUp = slowMovers.reduce((sum, alert) => sum + alert.stock, 0);

  return (
    <div className="ac-reveal @container flex flex-col gap-4">
      <PageHeader
        title={t("Inventory")}
        subtitle={
          data
            ? t(tiedUp ? "{low} low or out of stock · {slow} with {units} units tied up" : "{low} low or out of stock · {slow}", {
                low: lowStock.length,
                slow: pluralT(t, slowMovers.length, "{count} slow mover", "{count} slow movers"),
                units: formatNumber(tiedUp),
              })
            : undefined
        }
      />
      {failed && !data ? (
        <Notice>{t("The merchant API isn't reachable, so inventory alerts can't load.")}</Notice>
      ) : !data ? (
        <div className="grid gap-4 @4xl:grid-cols-2">
          <Skeleton className="h-72" />
          <Skeleton className="h-72" />
        </div>
      ) : (
        <div className="grid items-start gap-4 @4xl:grid-cols-2">
          <Panel title={t("Low stock")} subtitle={t("soonest to run out first")}>
            {lowStock.length === 0 ? (
              <p className="px-[18px] pb-4 text-[13.5px] text-(--ink-soft)">{t("No low-stock listings.")}</p>
            ) : (
              <ul className="divide-y divide-(--line)">
                {lowStock.map((alert) => (
                  <AlertRow key={alert.listing_id} alert={alert} onAskAssistant={onAskAssistant} />
                ))}
              </ul>
            )}
          </Panel>
          <Panel title={t("Slow movers")} subtitle={t("stock well above the last 30 days of sales")}>
            {slowMovers.length === 0 ? (
              <p className="px-[18px] pb-4 text-[13.5px] text-(--ink-soft)">{t("No slow movers.")}</p>
            ) : (
              <ul className="divide-y divide-(--line)">
                {slowMovers.map((alert) => (
                  <AlertRow key={alert.listing_id} alert={alert} onAskAssistant={onAskAssistant} />
                ))}
              </ul>
            )}
          </Panel>
        </div>
      )}
    </div>
  );
}
