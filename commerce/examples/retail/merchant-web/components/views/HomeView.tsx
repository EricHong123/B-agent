// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useMemo, useState } from "react";
import {
  ApprovalsBanner,
  AttentionList,
  AttentionRow,
  formatChangePct,
  formatComparisonLabel,
  formatDayMonth,
  formatMoney,
  formatNumber,
  formatPeriodLabel,
  formatRate,
  Icon,
  KindIcon,
  Notice,
  optionValuesLabel,
  PageHeader,
  Panel,
  Pill,
  QueueOverflow,
  ratioChangePct,
  RecentChanges,
  RecordList,
  Segmented,
  Skeleton,
  StatStrip,
  StatTile,
  type Translate,
  useLocale,
  useT,
  ViewLink,
} from "web-shared";
import { orderRows } from "@/lib/format";
import { INVENTORY_KINDS, ISSUE_KINDS } from "@/lib/kinds";
import { askWhyText, coverText, greetingText, pluralT } from "@/lib/labels";
import type { HomeInsight, InventoryAlert, MetricPoint, OrderIssue, OverviewResponse } from "@/lib/types";

type Filter = "all" | "orders" | "stock" | "slow";
type Row = { kind: "issue"; issue: OrderIssue } | { kind: "inventory"; alert: InventoryAlert };

const ROW_CAP = 6;

/** One sentence from the overview: the sales move and what needs the operator. */
function briefing(data: OverviewResponse, t: Translate): string {
  const { snapshot, needs_attention } = data;
  const parts: string[] = [];
  if (snapshot.sales_change_pct != null) {
    const pct = formatChangePct(Math.abs(snapshot.sales_change_pct)).replace("+", "");
    parts.push(snapshot.sales_change_pct >= 0 ? t("Sales are up {pct} on the week.", { pct }) : t("Sales are down {pct} on the week.", { pct }));
  }
  const orders = needs_attention.order_issues.length;
  const listings = needs_attention.inventory.length;
  const needs = [orders ? pluralT(t, orders, "{count} order", "{count} orders") : "", listings ? pluralT(t, listings, "{count} listing", "{count} listings") : ""].filter(Boolean);
  parts.push(
    needs.length === 2
      ? t("{a} and {b} need you today.", { a: needs[0], b: needs[1] })
      : needs.length === 1
        ? t("{a} need you today.", { a: needs[0] })
        : t("Nothing needs you today."),
  );
  return parts.join(" ");
}

function values(points?: MetricPoint[]): number[] | undefined {
  return points?.map((point) => point.value);
}

function rows(data: OverviewResponse, filter: Filter): Row[] {
  const { inventory, order_issues } = data.needs_attention;
  const issues = order_issues.map((issue) => ({ kind: "issue" as const, issue }));
  const lowStock = inventory
    .filter((alert) => alert.kind === "low_stock")
    .sort((a, b) => (a.days_of_cover ?? Infinity) - (b.days_of_cover ?? Infinity))
    .map((alert) => ({ kind: "inventory" as const, alert }));
  const slow = inventory.filter((alert) => alert.kind === "slow_mover").map((alert) => ({ kind: "inventory" as const, alert }));
  if (filter === "orders") return issues;
  if (filter === "stock") return lowStock;
  if (filter === "slow") return slow;
  // The most urgent stock alert leads; it is the one a seller acts on first.
  return [...lowStock.slice(0, 1), ...issues, ...lowStock.slice(1), ...slow];
}

function IssueRow({ issue, onAskAssistant }: { issue: OrderIssue; onAskAssistant: (text: string) => void }) {
  const t = useT();
  const style = ISSUE_KINDS[issue.kind];
  return (
    <AttentionRow
      icon={style.icon}
      tone={style.tone}
      title={issue.summary}
      meta={[t(style.label), t("Order {id}", { id: issue.order_id }), issue.opened_at ? t("opened {date}", { date: formatDayMonth(issue.opened_at) }) : ""].filter(Boolean).join(" · ")}
      action={{
        label: issue.kind === "buyer_message" ? t("Draft reply") : t("Ask"),
        onClick: () => onAskAssistant(t("What are my options for order {id}? {summary}.", { id: issue.order_id, summary: issue.summary })),
      }}
    />
  );
}

function InventoryRow({ alert, onAskAssistant }: { alert: InventoryAlert; onAskAssistant: (text: string) => void }) {
  const t = useT();
  const style = INVENTORY_KINDS[alert.kind];
  const soldOut = alert.kind === "low_stock" && alert.stock === 0;
  const low = alert.kind === "low_stock";
  const chosen = optionValuesLabel(alert);
  const name = chosen ? `${alert.title} · ${chosen}` : alert.title;
  const ref = `${name} (${alert.listing_id})`;
  return (
    <AttentionRow
      icon={style.icon}
      tone={soldOut ? "danger" : style.tone}
      title={name}
      meta={
        <>
          <span className={soldOut ? "font-semibold text-(--danger)" : low ? "font-semibold text-(--warn)" : ""}>
            {soldOut ? t("Sold out") : t("{count} in stock", { count: formatNumber(alert.stock) })}
          </span>
          {[
            "",
            alert.days_of_cover != null && !soldOut ? coverText(t, alert.days_of_cover) : "",
            alert.sales_last_30d != null ? t("{count} sold in 30 days", { count: formatNumber(alert.sales_last_30d) }) : "",
            alert.listing_id,
            soldOut && alert.storefront_visible === false ? t("hidden from the storefront") : "",
          ]
            .filter((part, index) => index === 0 || part)
            .join(" · ")}
        </>
      }
      note={
        // A paused listing still alerts here but shows no chip to shoppers.
        low && alert.stock > 0 && alert.storefront_visible ? (
          <Pill tone="warn" dot>
            {t("Storefront shows “Only {count} left”", { count: formatNumber(alert.stock) })}
          </Pill>
        ) : null
      }
      action={{
        label: low ? t("Draft restock") : t("Plan markdown"),
        onClick: () => onAskAssistant(low ? t("Draft a restock plan for {ref}.", { ref }) : t("Plan a markdown for {ref}.", { ref })),
      }}
    />
  );
}

function Insights({ insights, onAskAssistant }: { insights: HomeInsight[]; onAskAssistant: (text: string) => void }) {
  const t = useT();
  if (insights.length === 0) return null;
  return (
    <Panel title={t("From the assistant")} icon={<KindIcon icon="spark" tone="accent" size={24} />}>
      <ul className="divide-y divide-(--line)">
        {insights.map((insight) => (
          <li key={insight.insight_id} className="px-[18px] py-2.5">
            <div className="text-[13px] font-medium leading-snug text-(--ink)">{insight.headline}</div>
            {insight.detail ? <div className="mt-0.5 line-clamp-2 text-[12px] leading-snug text-(--ink-soft)">{insight.detail}</div> : null}
            <button
              type="button"
              onClick={() => onAskAssistant(insight.prompt)}
              className="mt-1.5 inline-flex items-center gap-1 text-[12.5px] font-semibold text-(--accent-ink) hover:underline"
            >
              {t("Ask")} <Icon name="arrow-right" size={13} />
            </button>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

export default function HomeView({
  data,
  failed,
  operator,
  onAskAssistant,
  onNavigate,
}: {
  data: OverviewResponse | null;
  failed: boolean;
  operator?: string;
  /** Prefills the composer; nothing is sent. */
  onAskAssistant: (text: string) => void;
  onNavigate: (view: "orders" | "inventory") => void;
}) {
  const t = useT();
  const { locale } = useLocale();
  const [filter, setFilter] = useState<Filter>("all");
  const pending = useMemo(() => (data?.needs_attention.pending_changes ?? []).filter((change) => change.status === "staged"), [data]);
  const queue = useMemo(() => (data ? rows(data, filter) : []), [data, filter]);
  const now = useMemo(() => new Date(), []);
  const greeting = greetingText(t, now);
  const title = operator ? t("{greeting}, {name}", { greeting, name: operator }) : greeting;
  const today = now.toLocaleDateString(locale === "zh" ? "zh-CN" : "en-US", { weekday: "long", month: "long", day: "numeric" });

  if (failed && !data) {
    return (
      <>
        <PageHeader title={title} subtitle={today} />
        <Notice>
          {t("The merchant API on port 8000 isn't reachable. Start it with")}{" "}
          <code className="rounded bg-(--well) px-1 font-mono text-[13px]">uvicorn retail.api.main:app --app-dir examples --port 8000</code> {t("and reload.")}
        </Notice>
      </>
    );
  }
  if (!data) {
    return (
      <>
        <PageHeader title={title} subtitle={today} />
        <Skeleton className="h-36" />
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
          <Skeleton className="h-96" />
          <Skeleton className="h-72" />
        </div>
      </>
    );
  }

  const { snapshot } = data;
  const counts = {
    orders: data.needs_attention.order_issues.length,
    stock: data.needs_attention.inventory.filter((alert) => alert.kind === "low_stock").length,
    slow: data.needs_attention.inventory.filter((alert) => alert.kind === "slow_mover").length,
  };
  const comparison = formatComparisonLabel(snapshot.period, snapshot.compare_to);
  // The snapshot carries no average-order delta, so derive it from the sales and orders deltas.
  const aovChangePct = ratioChangePct(snapshot.sales_change_pct, snapshot.orders_change_pct);
  const currency = snapshot.currency ?? "USD";

  return (
    <div className="ac-reveal flex flex-col gap-5">
      <PageHeader title={title} subtitle={`${today} · ${briefing(data, t)}`} />

      <ApprovalsBanner changes={pending} onReview={() => onAskAssistant(t("Walk me through the changes awaiting my approval and what each one would do."))} />

      <Panel
        title={t("This week")}
        subtitle={comparison ? t("{period} · against the {comparison}", { period: formatPeriodLabel(snapshot.period), comparison: t(comparison) }) : formatPeriodLabel(snapshot.period)}
        bodyClassName="pb-1"
      >
        <StatStrip>
          <StatTile
            label={t("Sales")}
            value={formatMoney(snapshot.sales, currency, { whole: snapshot.sales >= 1000 })}
            changePct={snapshot.sales_change_pct}
            points={values(data.trends?.sales)}
            prior={values(data.trends_prior?.sales)}
            onClick={() => onAskAssistant(askWhyText(t, "Sales", snapshot.sales_change_pct, comparison))}
            ariaLabel={t("{label}: ask the assistant why", { label: t("Sales") })}
          />
          <StatTile
            label={t("Orders")}
            value={formatNumber(snapshot.orders)}
            changePct={snapshot.orders_change_pct}
            points={values(data.trends?.orders)}
            prior={values(data.trends_prior?.orders)}
            onClick={() => onAskAssistant(askWhyText(t, "Orders", snapshot.orders_change_pct, comparison))}
            ariaLabel={t("{label}: ask the assistant why", { label: t("Orders") })}
          />
          <StatTile
            label={t("Conversion")}
            value={snapshot.conversion_rate != null ? formatRate(snapshot.conversion_rate) : "—"}
            changePct={snapshot.conversion_change_pct}
            points={values(data.trends?.conversion)}
            prior={values(data.trends_prior?.conversion)}
            onClick={() => onAskAssistant(askWhyText(t, "Conversion", snapshot.conversion_change_pct, comparison))}
            ariaLabel={t("{label}: ask the assistant why", { label: t("Conversion") })}
          />
          <StatTile
            label={t("Average order")}
            value={snapshot.average_order_value != null ? formatMoney(snapshot.average_order_value, currency) : "—"}
            changePct={aovChangePct}
            points={values(data.trends?.average_order_value)}
            prior={values(data.trends_prior?.average_order_value)}
            onClick={() => onAskAssistant(askWhyText(t, "Average order value", aovChangePct, comparison))}
            ariaLabel={t("{label}: ask the assistant why", { label: t("Average order value") })}
          />
        </StatStrip>
      </Panel>

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
        <Panel
          title={t("Needs you today")}
          action={
            <Segmented<Filter>
              label={t("Filter attention items")}
              value={filter}
              onChange={setFilter}
              options={[
                { id: "all", label: t("All"), count: counts.orders + counts.stock + counts.slow },
                { id: "orders", label: t("Orders"), count: counts.orders },
                { id: "stock", label: t("Low stock"), count: counts.stock },
                { id: "slow", label: t("Slow"), count: counts.slow },
              ]}
            />
          }
        >
          {queue.length === 0 ? (
            <p className="px-[18px] pb-4 pt-1 text-[13.5px] text-(--ink-soft)">{t("Nothing needs you today.")}</p>
          ) : (
            <>
              <AttentionList>
                {queue.slice(0, ROW_CAP).map((row) =>
                  row.kind === "issue" ? (
                    <IssueRow key={row.issue.issue_id} issue={row.issue} onAskAssistant={onAskAssistant} />
                  ) : (
                    <InventoryRow key={`${row.alert.kind}-${row.alert.listing_id}`} alert={row.alert} onAskAssistant={onAskAssistant} />
                  ),
                )}
              </AttentionList>
              <QueueOverflow
                hidden={queue.length - ROW_CAP}
                link={{
                  label: t("See all"),
                  // The hidden rows are order issues first, so open Orders when any of them is one.
                  onClick: () => onNavigate(queue.slice(ROW_CAP).some((row) => row.kind === "issue") ? "orders" : "inventory"),
                }}
              />
            </>
          )}
        </Panel>

        <div className="flex flex-col gap-4">
          <Insights insights={data.insights ?? []} onAskAssistant={onAskAssistant} />
          <Panel title={t("Recent orders")} action={<ViewLink label={t("All orders")} onClick={() => onNavigate("orders")} />}>
            {data.recent_orders.length === 0 ? (
              <p className="px-[18px] pb-4 text-[13px] text-(--ink-soft)">{t("No orders yet.")}</p>
            ) : (
              <RecordList rows={orderRows(data.recent_orders.slice(0, 4), t)} />
            )}
          </Panel>
          <RecentChanges changes={data.recent_changes} />
        </div>
      </div>
    </div>
  );
}
