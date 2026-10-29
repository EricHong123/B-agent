// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { AttentionList, AttentionRow, formatDayMonth, Notice, PageHeader, Panel, QuotedAsData, RecordList, Skeleton, useResource, useT } from "web-shared";
import { fetchAlerts } from "@/lib/api";
import { orderRows } from "@/lib/format";
import { ISSUE_KINDS } from "@/lib/kinds";
import { pluralT } from "@/lib/labels";
import type { OrderIssue, RecentOrder } from "@/lib/types";

function IssueRow({ issue, onAskAssistant }: { issue: OrderIssue; onAskAssistant: (text: string) => void }) {
  const t = useT();
  const style = ISSUE_KINDS[issue.kind];
  return (
    <AttentionRow
      icon={style.icon}
      tone={style.tone}
      title={issue.summary}
      meta={[t(style.label), t("Order {id}", { id: issue.order_id }), issue.listing_id ?? "", issue.opened_at ? t("opened {date}", { date: formatDayMonth(issue.opened_at) }) : ""].filter(Boolean).join(" · ")}
      note={
        issue.buyer_message_excerpt ? (
          <div className="mt-1 rounded-[10px] bg-(--ground) px-3 py-2">
            <blockquote className="text-[13px] leading-snug text-(--ink-2)">&ldquo;{issue.buyer_message_excerpt}&rdquo;</blockquote>
            {/* Some fixture excerpts are injection attempts, so the note sits beside the quote. */}
            <QuotedAsData subject={t("Buyer message")} className="mt-1.5" />
          </div>
        ) : null
      }
      action={{
        label: issue.kind === "buyer_message" ? t("Draft reply") : t("Ask"),
        onClick: () => onAskAssistant(t("What are my options for order {id}? {summary}.", { id: issue.order_id, summary: issue.summary })),
      }}
    />
  );
}

export default function OrdersView({
  refreshKey,
  recentOrders,
  onAskAssistant,
}: {
  refreshKey: number;
  recentOrders: RecentOrder[] | null;
  onAskAssistant: (text: string) => void;
}) {
  const t = useT();
  const { data, failed } = useResource(fetchAlerts, [refreshKey]);
  const issues = data?.order_issues ?? [];

  return (
    <div className="ac-reveal flex flex-col gap-4">
      <PageHeader
        title={t("Orders")}
        subtitle={data ? (issues.length ? pluralT(t, issues.length, "{count} open issue", "{count} open issues") : t("No open issues")) : undefined}
      />
      {failed && !data ? (
        <Notice>{t("The merchant API isn't reachable, so order issues can't load.")}</Notice>
      ) : !data ? (
        <div className="grid gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
          <Skeleton className="h-96" />
          <Skeleton className="h-64" />
        </div>
      ) : (
        <div className="grid items-start gap-4 xl:grid-cols-[minmax(0,1fr)_320px]">
          <Panel title={t("Open issues")} subtitle={issues.length ? String(issues.length) : undefined}>
            {issues.length === 0 ? (
              <p className="px-[18px] pb-4 text-[13.5px] text-(--ink-soft)">{t("No open order issues.")}</p>
            ) : (
              <AttentionList>
                {issues.map((issue) => (
                  <IssueRow key={issue.issue_id} issue={issue} onAskAssistant={onAskAssistant} />
                ))}
              </AttentionList>
            )}
          </Panel>
          <Panel title={t("Recent orders")}>
            {!recentOrders ? (
              <Skeleton className="mx-[18px] mb-4 h-40" />
            ) : recentOrders.length === 0 ? (
              <p className="px-[18px] pb-4 text-[13px] text-(--ink-soft)">{t("No recent orders to show.")}</p>
            ) : (
              <RecordList rows={orderRows(recentOrders, t)} />
            )}
          </Panel>
        </div>
      )}
    </div>
  );
}
