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
  greeting,
  type Translate,
  Notice,
  PageHeader,
  Panel,
  plural,
  QueueOverflow,
  ratioChangePct,
  RecentChanges,
  RecordList,
  Segmented,
  Skeleton,
  StatStrip,
  StatTile,
  useLocale,
  useT,
  ViewLink,
} from "web-shared";
import { INVENTORY_KINDS, inventoryPrompt, ISSUE_KINDS } from "@/lib/kinds";
import type { InventoryAlert, OccupancyOverviewResponse, OrderIssue, OverviewResponse, TodaySnapshot } from "@/lib/types";
import { bookingRows, issuePrompt, runway } from "./BookingsView";

type Filter = "all" | "bookings" | "availability" | "pace";
type QueueRow = { kind: "issue"; issue: OrderIssue } | { kind: "inventory"; alert: InventoryAlert };

const ROW_CAP = 6;

/** One sentence from the overview: the revenue move and what needs the operator. */
function briefing(data: OverviewResponse, t: Translate): string {
  const { snapshot, needs_attention } = data;
  const parts: string[] = [];
  if (snapshot.sales_change_pct != null) {
    const change = formatChangePct(Math.abs(snapshot.sales_change_pct)).replace("+", "");
    parts.push(snapshot.sales_change_pct >= 0 ? t("Revenue is up {change} on the week.", { change }) : t("Revenue is down {change} on the week.", { change }));
  }
  const bookings = needs_attention.order_issues.length;
  const properties = needs_attention.inventory.length;
  const needs = [bookings ? plural(bookings, "booking", "bookings", t) : "", properties ? plural(properties, "property", "properties", t) : ""].filter(Boolean);
  const needing = needs.length === 2 ? t("{a} and {b}", { a: needs[0], b: needs[1] }) : needs[0];
  parts.push(needs.length ? t("{needs} need you today.", { needs: needing }) : t("Nothing needs you today."));
  return parts.join(" ");
}

/** The question a KPI tile prefills: why the figure moved against the comparison window. */
function askWhy(t: Translate, label: string, changePct: number | null | undefined, comparison: string): string {
  const name = label.toLowerCase();
  if (changePct == null) return t("How is {name} trending, and what's behind it?", { name });
  const pct = Math.abs(changePct).toFixed(1);
  const against = comparison || t("prior period");
  return changePct >= 0 ? t("Why is {name} up {pct}% against the {comparison}?", { name, pct, comparison: against }) : t("Why is {name} down {pct}% against the {comparison}?", { name, pct, comparison: against });
}

function queueRows(data: OverviewResponse, filter: Filter): QueueRow[] {
  const { inventory, order_issues } = data.needs_attention;
  const issues = order_issues.map((issue) => ({ kind: "issue" as const, issue }));
  const tight = inventory
    .filter((alert) => alert.kind === "low_stock")
    .sort((a, b) => (a.days_of_cover ?? Infinity) - (b.days_of_cover ?? Infinity))
    .map((alert) => ({ kind: "inventory" as const, alert }));
  const soft = inventory.filter((alert) => alert.kind === "slow_mover").map((alert) => ({ kind: "inventory" as const, alert }));
  if (filter === "bookings") return issues;
  if (filter === "availability") return tight;
  if (filter === "pace") return soft;
  // The softest-pacing stay leads; it is what a supplier acts on.
  return [...soft.slice(0, 1), ...issues, ...soft.slice(1), ...tight];
}

function IssueRow({ issue, onAskAssistant }: { issue: OrderIssue; onAskAssistant: (text: string) => void }) {
  const t = useT();
  const style = ISSUE_KINDS[issue.kind];
  return (
    <AttentionRow
      icon={style.icon}
      tone={style.tone}
      title={issue.summary}
      meta={[t(style.label), t("Booking {id}", { id: issue.order_id }), issue.opened_at ? t("opened {date}", { date: formatDayMonth(issue.opened_at) }) : ""].filter(Boolean).join(" · ")}
      action={{ label: issue.kind === "buyer_message" ? t("Draft reply") : t("Ask"), onClick: () => onAskAssistant(issuePrompt(issue, t)) }}
    />
  );
}

function InventoryRow({ alert, onAskAssistant }: { alert: InventoryAlert; onAskAssistant: (text: string) => void }) {
  const t = useT();
  const style = INVENTORY_KINDS[alert.kind];
  const tight = alert.kind === "low_stock";
  return (
    <AttentionRow
      icon={style.icon}
      tone={style.tone}
      title={alert.title}
      meta={
        <>
          <span className={tight ? "font-semibold text-(--warn)" : ""}>{t("{count} room-nights available", { count: formatNumber(alert.stock) })}</span>
          {["", tight ? runway(alert, t) : null, alert.sales_last_30d != null ? t("{count} booked in 30 days", { count: formatNumber(alert.sales_last_30d) }) : "", alert.listing_id]
            .filter((part, index) => index === 0 || part)
            .join(" · ")}
        </>
      }
      action={{ label: tight ? t("Ask") : t("Plan rates"), onClick: () => onAskAssistant(inventoryPrompt(alert.kind, `${alert.title} (${alert.listing_id})`, t)) }}
    />
  );
}

function TodayPanel({ today }: { today: TodaySnapshot }) {
  const t = useT();
  const rows = [
    { label: t("Arrivals"), ...today.arrivals },
    { label: t("Departures"), ...today.departures },
    { label: t("New bookings"), ...today.new_bookings },
  ];
  return (
    <Panel title={t("Today at your properties")}>
      <ul className="divide-y divide-(--line) px-[18px] pb-2">
        {rows.map((row) => (
          <li key={row.label} className="flex items-baseline gap-3 py-2">
            <span className="al-display w-7 shrink-0 text-[22px] font-semibold leading-none tabular-nums text-(--ink)">{row.count}</span>
            <div className="min-w-0">
              <div className="text-[13px] font-medium text-(--ink)">{row.label}</div>
              {row.properties.length ? <div className="truncate text-[12px] text-(--ink-soft)">{row.properties.join(" · ")}</div> : null}
            </div>
          </li>
        ))}
      </ul>
    </Panel>
  );
}

// Midweek occupancy below this counts as soft, matching the supplier backend's threshold.
const SOFT_PCT = 55;

interface RibbonDay {
  date: Date;
  pct: number | null;
  weekend: boolean;
  overridden: boolean;
  staged: boolean;
}

/** The focus month is the earliest one within this many points of the softest month. */
const FOCUS_TOLERANCE_PTS = 3;

function pickFocusMonth(data: OccupancyOverviewResponse): { year: number; month: number } | null {
  const scores = new Map<string, { sum: number; count: number; year: number; month: number }>();
  for (const listing of data.properties) {
    for (const week of listing.weeks ?? []) {
      if (!week.week_start || week.midweek_occupancy_pct == null) continue;
      const start = new Date(`${week.week_start}T00:00:00`);
      const key = `${start.getFullYear()}-${start.getMonth()}`;
      const entry = scores.get(key) ?? { sum: 0, count: 0, year: start.getFullYear(), month: start.getMonth() };
      entry.sum += week.midweek_occupancy_pct;
      entry.count += 1;
      scores.set(key, entry);
    }
  }
  const months = [...scores.values()]
    .map((entry) => ({ year: entry.year, month: entry.month, average: entry.sum / entry.count }))
    .sort((a, b) => a.year - b.year || a.month - b.month);
  if (months.length === 0) return null;
  const softest = Math.min(...months.map((entry) => entry.average));
  const focus = months.find((entry) => entry.average <= softest + FOCUS_TOLERANCE_PTS);
  return focus ? { year: focus.year, month: focus.month } : null;
}

function isInWindow(day: Date, starts?: string | null, ends?: string | null): boolean {
  if (!starts || !ends) return false;
  return day >= new Date(`${starts}T00:00:00`) && day <= new Date(`${ends}T00:00:00`);
}

/** Weekly grain to days: weekdays take midweek occupancy, Fri/Sat nights weekend occupancy. */
function expandDays(
  listing: OccupancyOverviewResponse["properties"][number],
  year: number,
  month: number,
  stagedWindows: OccupancyOverviewResponse["staged_windows"],
): RibbonDay[] {
  const weeks = (listing.weeks ?? []).filter((week) => week.week_start);
  const staged = stagedWindows.filter((window) => window.listing_ids.includes(listing.listing_id ?? ""));
  const days: RibbonDay[] = [];
  const count = new Date(year, month + 1, 0).getDate();
  for (let dayOfMonth = 1; dayOfMonth <= count; dayOfMonth++) {
    const day = new Date(year, month, dayOfMonth);
    const week = weeks.find((entry) => {
      const start = new Date(`${entry.week_start}T00:00:00`);
      const end = new Date(start);
      end.setDate(end.getDate() + 6);
      return day >= start && day <= end;
    });
    // Friday and Saturday are the hotel weekend (the nights guests stay).
    const weekend = day.getDay() === 5 || day.getDay() === 6;
    const pct =
      week == null
        ? null
        : weekend
          ? (week.weekend_occupancy_pct ?? week.occupancy_pct ?? null)
          : (week.midweek_occupancy_pct ?? week.occupancy_pct ?? null);
    days.push({
      date: day,
      pct,
      weekend,
      overridden: isInWindow(day, week?.override?.starts, week?.override?.ends),
      staged: staged.some((window) => isInWindow(day, window.starts, window.ends)),
    });
  }
  return days;
}

const MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July", "August", "September", "October", "November", "December"];

function OccupancyRibbon({ data, onAskAssistant }: { data: OccupancyOverviewResponse; onAskAssistant: (text: string) => void }) {
  const t = useT();
  const focus = useMemo(() => pickFocusMonth(data), [data]);
  if (!focus || data.properties.length === 0) return null;
  const monthName = t(MONTH_NAMES[focus.month]);
  return (
    <Panel
      title={t("{month} occupancy on the books", { month: monthName })}
      action={<span className="hidden text-[12px] text-(--ink-faint) sm:inline">{t("Paler is softer; outlined days have a staged rate.")}</span>}
    >
      <div className="flex flex-col gap-1.5 px-[18px] pb-4 pt-1">
        {data.properties.map((listing) => {
          const days = expandDays(listing, focus.year, focus.month, data.staged_windows);
          return (
            <div key={listing.listing_id ?? listing.title} className="flex items-center gap-2">
              <div className="w-36 shrink-0 truncate text-[12px] font-medium text-(--ink)" title={listing.title ?? undefined}>
                {listing.title}
              </div>
              <div className="grid min-w-0 flex-1 gap-px" style={{ gridTemplateColumns: `repeat(${days.length}, minmax(0, 1fr))` }}>
                {days.map((day) => {
                  const pct = day.pct;
                  const soft = pct != null && pct < SOFT_PCT;
                  const dayOfMonth = day.date.getDate();
                  const question = soft
                    ? t("Why is {title} pacing soft around {month} {day}?", { title: listing.title ?? "", month: monthName, day: dayOfMonth })
                    : t("How is {title} pacing for {month}?", { title: listing.title ?? "", month: monthName });
                  const details = [
                    pct == null ? t("no data") : t("{pct}% on the books", { pct: Math.round(pct) }),
                    day.staged ? t("staged rate window") : "",
                    day.overridden ? t("promotional rate active") : "",
                  ]
                    .filter(Boolean)
                    .join(t(", "));
                  return (
                    <button
                      key={day.date.toISOString()}
                      type="button"
                      onClick={() => onAskAssistant(question)}
                      className={`relative h-6 min-w-0 rounded-[2px] transition hover:ring-1 hover:ring-(--ink) ${
                        day.staged ? "ring-1 ring-(--violet)" : day.overridden ? "ring-1 ring-(--ok)" : ""
                      }`}
                      style={{
                        backgroundColor: pct == null ? "transparent" : `color-mix(in srgb, var(--accent) ${Math.round(pct)}%, var(--well))`,
                      }}
                      aria-label={t("{title}, {month} {day}: {details}. Ask the assistant.", { title: listing.title ?? "", month: monthName, day: dayOfMonth, details })}
                      title={t("{month} {day} · {value}", { month: monthName, day: dayOfMonth, value: pct == null ? t("no data") : `${Math.round(pct)}%` })}
                    >
                      {day.weekend ? <span className="absolute inset-x-0 top-0 h-0.5 bg-(--ink)/30" /> : null}
                    </button>
                  );
                })}
              </div>
            </div>
          );
        })}
      </div>
    </Panel>
  );
}

export default function HomeView({
  data,
  failed,
  occupancy,
  operator,
  onAskAssistant,
  onNavigate,
}: {
  data: OverviewResponse | null;
  failed: boolean;
  occupancy: OccupancyOverviewResponse | null;
  operator?: string;
  /** Prefills the composer; nothing is sent. */
  onAskAssistant: (text: string) => void;
  onNavigate: (view: "properties" | "bookings") => void;
}) {
  const t = useT();
  const { locale } = useLocale();
  const [filter, setFilter] = useState<Filter>("all");
  const pending = useMemo(() => (data?.needs_attention.pending_changes ?? []).filter((change) => change.status === "staged"), [data]);
  const rows = useMemo(() => (data ? queueRows(data, filter) : []), [data, filter]);
  const now = useMemo(() => new Date(), []);
  const title = operator ? t("{greeting}, {name}", { greeting: greeting(now, t), name: operator }) : greeting(now, t);
  const today = now.toLocaleDateString(locale === "zh" ? "zh-CN" : "en-US", { weekday: "long", month: "long", day: "numeric" });

  if (failed && !data) {
    return (
      <>
        <PageHeader title={title} subtitle={today} />
        <Notice>
          {t("The travel API on port 8001 isn't reachable. Start it with")}{" "}
          <code className="rounded bg-(--well) px-1 font-mono text-[13px]">uvicorn travel.api.main:app --app-dir examples --port 8001</code> {t("and reload.")}
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
    bookings: data.needs_attention.order_issues.length,
    availability: data.needs_attention.inventory.filter((alert) => alert.kind === "low_stock").length,
    pace: data.needs_attention.inventory.filter((alert) => alert.kind === "slow_mover").length,
  };
  const total = counts.bookings + counts.availability + counts.pace;
  const comparison = formatComparisonLabel(snapshot.period, snapshot.compare_to, t);
  // The snapshot carries no average-booking delta, so derive it from the revenue and bookings deltas.
  const averageChangePct = ratioChangePct(snapshot.sales_change_pct, snapshot.orders_change_pct);
  const currency = snapshot.currency ?? "USD";

  return (
    <div className="ac-reveal flex flex-col gap-5">
      <PageHeader title={title} subtitle={`${today} · ${briefing(data, t)}`} />

      <ApprovalsBanner changes={pending} onReview={() => onAskAssistant(t("Walk me through the changes awaiting my approval and what each one would do."))} />

      <Panel title={t("This week")} subtitle={comparison ? t("{period} · against the {comparison}", { period: formatPeriodLabel(snapshot.period), comparison }) : formatPeriodLabel(snapshot.period)} bodyClassName="pb-1">
        <StatStrip>
          <StatTile
            label={t("Revenue")}
            value={formatMoney(snapshot.sales, currency, { whole: snapshot.sales >= 1000 })}
            changePct={snapshot.sales_change_pct}
            onClick={() => onAskAssistant(askWhy(t, t("Revenue"), snapshot.sales_change_pct, comparison))}
            ariaLabel={t("{label}: ask the assistant why", { label: t("Revenue") })}
          />
          <StatTile
            label={t("Bookings")}
            value={formatNumber(snapshot.orders)}
            changePct={snapshot.orders_change_pct}
            onClick={() => onAskAssistant(askWhy(t, t("Bookings"), snapshot.orders_change_pct, comparison))}
            ariaLabel={t("{label}: ask the assistant why", { label: t("Bookings") })}
          />
          <StatTile
            label={t("Conversion")}
            value={snapshot.conversion_rate != null ? formatRate(snapshot.conversion_rate) : "—"}
            changePct={snapshot.conversion_change_pct}
            onClick={() => onAskAssistant(askWhy(t, t("Conversion"), snapshot.conversion_change_pct, comparison))}
            ariaLabel={t("{label}: ask the assistant why", { label: t("Conversion") })}
          />
          <StatTile
            label={t("Average booking")}
            value={snapshot.average_order_value != null ? formatMoney(snapshot.average_order_value, currency) : "—"}
            changePct={averageChangePct}
            onClick={() => onAskAssistant(askWhy(t, t("Average booking value"), averageChangePct, comparison))}
            ariaLabel={t("{label}: ask the assistant why", { label: t("Average booking") })}
          />
        </StatStrip>
      </Panel>

      {occupancy ? <OccupancyRibbon data={occupancy} onAskAssistant={onAskAssistant} /> : null}

      <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_300px]">
        <Panel
          title={t("Needs you today")}
          action={
            <Segmented<Filter>
              label={t("Filter attention items")}
              value={filter}
              onChange={setFilter}
              options={[
                { id: "all", label: t("All"), count: total },
                { id: "bookings", label: t("Bookings"), count: counts.bookings },
                { id: "availability", label: t("Availability"), count: counts.availability },
                { id: "pace", label: t("Soft pacing"), count: counts.pace },
              ]}
            />
          }
        >
          {rows.length === 0 ? (
            <p className="px-[18px] pb-4 pt-1 text-[13.5px] text-(--ink-soft)">{t("Nothing needs you today.")}</p>
          ) : (
            <>
              <AttentionList>
                {rows.slice(0, ROW_CAP).map((row) =>
                  row.kind === "issue" ? (
                    <IssueRow key={row.issue.issue_id} issue={row.issue} onAskAssistant={onAskAssistant} />
                  ) : (
                    <InventoryRow key={`${row.alert.kind}-${row.alert.listing_id}`} alert={row.alert} onAskAssistant={onAskAssistant} />
                  ),
                )}
              </AttentionList>
              <QueueOverflow hidden={rows.length - ROW_CAP} link={{ label: t("See all"), onClick: () => onNavigate("bookings") }} />
            </>
          )}
        </Panel>

        <div className="flex flex-col gap-4">
          {data.today ? <TodayPanel today={data.today} /> : null}
          <Panel title={t("Recent bookings")} action={<ViewLink label={t("All bookings")} onClick={() => onNavigate("bookings")} />}>
            {data.recent_orders.length === 0 ? (
              <p className="px-[18px] pb-4 text-[13px] text-(--ink-soft)">{t("No bookings yet.")}</p>
            ) : (
              <RecordList rows={bookingRows(data.recent_orders.slice(0, 4), t)} />
            )}
          </Panel>
          <RecentChanges changes={data.recent_changes} />
        </div>
      </div>
    </div>
  );
}
