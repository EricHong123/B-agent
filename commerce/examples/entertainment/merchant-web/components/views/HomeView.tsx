// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useMemo, useState } from "react";
import {
  ApprovalsBanner,
  AttentionList,
  AttentionRow,
  formatComparisonLabel,
  formatDayMonth,
  formatMoney,
  formatNumber,
  formatPeriodLabel,
  formatRate,
  MiniBar,
  Notice,
  PageHeader,
  Panel,
  QueueOverflow,
  ratioChangePct,
  RecentChanges,
  RecordList,
  Segmented,
  Skeleton,
  StatStrip,
  StatTile,
  type Translate,
  useT,
  ViewLink,
} from "web-shared";
import { INVENTORY_KINDS, ISSUE_KINDS, ORDER_STATUS } from "@/lib/kinds";
import type { InventoryAlert, OrderIssue, OverviewResponse, TodaySnapshot } from "@/lib/types";
import { askWhy, countLabel, formatDaysToEvent, greetingFor, runwayLabel, unsignedChangePct } from "@/lib/format";

type Filter = "all" | "orders" | "scarce" | "pacing";
type Row = { kind: "issue"; issue: OrderIssue } | { kind: "tier"; alert: InventoryAlert };

const ROW_CAP = 6;

/** One sentence from the overview: the gross move and what needs the operator. */
function briefing(data: OverviewResponse, t: Translate): string {
  const { snapshot, needs_attention } = data;
  const parts: string[] = [];
  if (snapshot.sales_change_pct != null) {
    parts.push(
      t(snapshot.sales_change_pct >= 0 ? "Gross sales are up {pct} on the week." : "Gross sales are down {pct} on the week.", {
        pct: unsignedChangePct(snapshot.sales_change_pct),
      }),
    );
  }
  const orders = needs_attention.order_issues.length;
  const tiers = needs_attention.inventory.length;
  const needs = [orders ? countLabel(t, orders, "{n} order", "{n} orders") : "", tiers ? countLabel(t, tiers, "{n} tier", "{n} tiers") : ""].filter(Boolean);
  parts.push(
    needs.length === 2
      ? t("{a} and {b} need you today.", { a: needs[0], b: needs[1] })
      : needs.length === 1
        ? t("{a} need you today.", { a: needs[0] })
        : t("Nothing needs you today."),
  );
  return parts.join(" ");
}

function rowsFor(data: OverviewResponse, filter: Filter): Row[] {
  const { inventory, order_issues } = data.needs_attention;
  const issues = order_issues.map((issue) => ({ kind: "issue" as const, issue }));
  const scarce = inventory
    .filter((alert) => alert.kind === "low_stock")
    .sort((a, b) => a.stock - b.stock)
    .map((alert) => ({ kind: "tier" as const, alert }));
  const pacing = inventory.filter((alert) => alert.kind === "slow_mover").map((alert) => ({ kind: "tier" as const, alert }));
  if (filter === "orders") return issues;
  if (filter === "scarce") return scarce;
  if (filter === "pacing") return pacing;
  // The tier furthest behind pace leads; it is what the box office acts on first.
  return [...pacing.slice(0, 1), ...issues, ...scarce, ...pacing.slice(1)];
}

function IssueRow({ issue, onAskAssistant }: { issue: OrderIssue; onAskAssistant: (text: string) => void }) {
  const t = useT();
  const style = ISSUE_KINDS[issue.kind];
  return (
    <AttentionRow
      icon={style.icon}
      tone={style.tone}
      title={issue.summary}
      meta={[
        t(style.label),
        t("Order {id}", { id: issue.order_id }),
        issue.opened_at ? t("opened {date}", { date: formatDayMonth(issue.opened_at) }) : "",
      ]
        .filter(Boolean)
        .join(" · ")}
      action={{
        label: issue.kind === "buyer_message" ? t("Draft reply") : t("Ask"),
        onClick: () => onAskAssistant(t("What are my options for order {id}? {summary}.", { id: issue.order_id, summary: issue.summary })),
      }}
    />
  );
}

function TierRow({ alert, onAskAssistant }: { alert: InventoryAlert; onAskAssistant: (text: string) => void }) {
  const t = useT();
  const style = INVENTORY_KINDS[alert.kind];
  const scarce = alert.kind === "low_stock";
  const ref = `${alert.title} (${alert.listing_id})`;
  return (
    <AttentionRow
      icon={style.icon}
      tone={style.tone}
      title={alert.title}
      meta={
        <>
          <span className={`font-semibold ${scarce ? "text-(--warn)" : "text-(--danger)"}`}>{scarce ? t("{n} open seats", { n: formatNumber(alert.stock) }) : t(style.label)}</span>
          {[
            "",
            scarce ? "" : t("{n} open", { n: formatNumber(alert.stock) }),
            alert.days_of_cover != null ? runwayLabel(alert.days_of_cover, t) : "",
            alert.sales_last_30d != null ? t("{n} sold in 30 days", { n: formatNumber(alert.sales_last_30d) }) : "",
            alert.listing_id,
          ]
            .filter((part, index) => index === 0 || part)
            .join(" · ")}
        </>
      }
      action={
        scarce
          ? { label: t("Release holds"), onClick: () => onAskAssistant(t("{ref} is nearly sold out. Should we release any held seats?", { ref })) }
          : { label: t("Ask"), onClick: () => onAskAssistant(t("{ref} is behind its comparable-events pace. What would you propose?", { ref })) }
      }
    />
  );
}

function NextUp({ today, onNavigate }: { today: TodaySnapshot; onNavigate: () => void }) {
  const t = useT();
  if (!today.upcoming.length) return null;
  return (
    <Panel title={t("Next up")} action={<ViewLink label={t("All events")} onClick={onNavigate} />}>
      <div className="grid gap-2.5 px-[18px] pb-4 pt-1 @2xl:grid-cols-3">
        {today.upcoming.map((show) => (
          <button
            key={show.event_id}
            type="button"
            onClick={onNavigate}
            className="rounded-[10px] border border-(--line) bg-(--well)/60 px-3 py-2.5 text-left transition-colors hover:border-(--accent)"
            aria-label={t("{event}, {date}, {sold} of {capacity} sold. Open the Events view.", {
              event: show.event_name,
              date: formatDayMonth(show.event_date),
              sold: formatNumber(show.sold),
              capacity: formatNumber(show.capacity),
            })}
          >
            <div className="at-display truncate text-[16px] text-(--ink)" title={show.event_name}>
              {show.event_name}
            </div>
            <div className="mt-0.5 truncate text-[11.5px] text-(--ink-soft)">
              {[show.venue, formatDayMonth(show.event_date), formatDaysToEvent(show.days_to_event, t)].filter(Boolean).join(" · ")}
            </div>
            <MiniBar value={show.capacity > 0 ? show.sold / show.capacity : 0} tone="accent" className="mt-2 w-full" />
            <div className="at-mono mt-1 text-[11.5px] text-(--ink-soft)">
              {t("{sold}/{capacity} sold", { sold: formatNumber(show.sold), capacity: formatNumber(show.capacity) })} · {t("{n} open", { n: formatNumber(show.remaining) })}
              {show.waitlist_depth > 0 ? ` · ${t("waitlist {n}", { n: formatNumber(show.waitlist_depth) })}` : ""}
            </div>
          </button>
        ))}
      </div>
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
  onNavigate: (view: "events" | "holds") => void;
}) {
  const t = useT();
  const [filter, setFilter] = useState<Filter>("all");
  const pending = useMemo(() => (data?.needs_attention.pending_changes ?? []).filter((change) => change.status === "staged"), [data]);
  const rows = useMemo(() => (data ? rowsFor(data, filter) : []), [data, filter]);
  const now = useMemo(() => new Date(), []);
  const title = `${greetingFor(now, t)}${operator ? `, ${operator}` : ""}`;
  const today = now.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric" });

  if (failed && !data) {
    return (
      <>
        <PageHeader title={title} subtitle={today} />
        <Notice>
          {t("The entertainment API on port 8003 isn't reachable. Start it with")}{" "}
          <code className="at-mono rounded bg-(--well) px-1 text-[13px]">uvicorn entertainment.api.main:app --app-dir examples --port 8003</code> {t("and reload.")}
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
    scarce: data.needs_attention.inventory.filter((alert) => alert.kind === "low_stock").length,
    pacing: data.needs_attention.inventory.filter((alert) => alert.kind === "slow_mover").length,
  };
  const currency = snapshot.currency ?? "USD";
  const aovChangePct = ratioChangePct(snapshot.sales_change_pct, snapshot.orders_change_pct);
  const comparison = formatComparisonLabel(snapshot.period, snapshot.compare_to);

  return (
    <div className="ac-reveal @container flex flex-col gap-5">
      <PageHeader title={title} subtitle={`${today} · ${briefing(data, t)}`} />

      <ApprovalsBanner changes={pending} onReview={() => onAskAssistant(t("Walk me through the changes awaiting my approval and what each one would do."))} />

      <Panel
        title={t("This week")}
        subtitle={
          comparison
            ? t("{period} · against the {comparison}", { period: formatPeriodLabel(snapshot.period), comparison: t(comparison) })
            : formatPeriodLabel(snapshot.period)
        }
        bodyClassName="pb-1"
      >
        <StatStrip>
          <StatTile
            label={t("Gross sales")}
            value={formatMoney(snapshot.sales, currency, { whole: snapshot.sales >= 1000 })}
            changePct={snapshot.sales_change_pct}
            onClick={() => onAskAssistant(askWhy(t, "Gross sales", snapshot.sales_change_pct, comparison))}
            ariaLabel={t("{label}: ask the assistant why", { label: t("Gross sales") })}
          />
          <StatTile
            label={t("Orders")}
            value={formatNumber(snapshot.orders)}
            changePct={snapshot.orders_change_pct}
            onClick={() => onAskAssistant(askWhy(t, "Orders", snapshot.orders_change_pct, comparison))}
            ariaLabel={t("{label}: ask the assistant why", { label: t("Orders") })}
          />
          <StatTile
            label={t("Conversion")}
            value={snapshot.conversion_rate != null ? formatRate(snapshot.conversion_rate) : "—"}
            changePct={snapshot.conversion_change_pct}
            onClick={() => onAskAssistant(askWhy(t, "Conversion", snapshot.conversion_change_pct, comparison))}
            ariaLabel={t("{label}: ask the assistant why", { label: t("Conversion") })}
          />
          <StatTile
            label={t("Average order")}
            value={snapshot.average_order_value != null ? formatMoney(snapshot.average_order_value, currency) : "—"}
            changePct={aovChangePct}
            onClick={() => onAskAssistant(askWhy(t, "Average order value", aovChangePct, comparison))}
            ariaLabel={t("{label}: ask the assistant why", { label: t("Average order value") })}
          />
        </StatStrip>
      </Panel>

      {data.today ? <NextUp today={data.today} onNavigate={() => onNavigate("events")} /> : null}

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
        <Panel
          title={t("Needs you today")}
          action={
            <Segmented<Filter>
              label={t("Filter attention items")}
              value={filter}
              onChange={setFilter}
              options={[
                { id: "all", label: t("All"), count: counts.orders + counts.scarce + counts.pacing },
                { id: "orders", label: t("Orders"), count: counts.orders },
                { id: "scarce", label: t("Scarce"), count: counts.scarce },
                { id: "pacing", label: t("Pacing"), count: counts.pacing },
              ]}
            />
          }
        >
          {rows.length === 0 ? (
            <p className="px-[18px] pb-4 pt-1 text-[13.5px] text-(--ink-soft)">{t("Nothing is waiting on you.")}</p>
          ) : (
            <>
              <AttentionList>
                {rows.slice(0, ROW_CAP).map((row) =>
                  row.kind === "issue" ? (
                    <IssueRow key={row.issue.issue_id} issue={row.issue} onAskAssistant={onAskAssistant} />
                  ) : (
                    <TierRow key={`${row.alert.kind}-${row.alert.listing_id}`} alert={row.alert} onAskAssistant={onAskAssistant} />
                  ),
                )}
              </AttentionList>
              <QueueOverflow hidden={rows.length - ROW_CAP} />
            </>
          )}
        </Panel>

        <div className="flex flex-col gap-4">
          <Panel title={t("Recent orders")}>
            {data.recent_orders.length === 0 ? (
              <p className="px-[18px] pb-4 text-[13px] text-(--ink-soft)">{t("No orders yet.")}</p>
            ) : (
              <RecordList
                mono
                rows={data.recent_orders.slice(0, 5).map((order) => ({
                  id: order.order_id,
                  detail: countLabel(t, order.items, "{n} ticket", "{n} tickets"),
                  sub: `${formatDayMonth(order.placed_at)} · ${formatMoney(order.total)}`,
                  status: ORDER_STATUS[order.status]
                    ? { ...ORDER_STATUS[order.status], label: t(ORDER_STATUS[order.status].label) }
                    : { label: t(order.status.replaceAll("_", " ")), tone: "muted" },
                }))}
              />
            )}
          </Panel>
          <RecentChanges changes={data.recent_changes} />
        </div>
      </div>
    </div>
  );
}
