// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** The blocks every portal's home page shares; a vertical supplies its nouns and rows. */

import type { ReactNode } from "react";
import { describeProposer, describeResolver, formatDayMonth } from "../format";
import { english } from "../english";
import { type Translate, useT } from "../i18n";
import { Icon, type IconName } from "../icons";
import { AskButton, Button, KindIcon, Panel, Pill, type Tone } from "../ui";
import { CHANGE_STATUS } from "./cards";

/** The question a KPI tile prefills: why the figure moved against the comparison window. */
export function askWhy(label: string, changePct: number | null | undefined, comparison: string, t: Translate = english): string {
  const name = t(label).toLowerCase();
  if (changePct == null) return t("How is {name} trending, and what's behind it?", { name });
  const vars = { name, pct: Math.abs(changePct).toFixed(1), comparison: comparison || t("prior period") };
  return changePct >= 0
    ? t("Why is {name} up {pct}% against the {comparison}?", vars)
    : t("Why is {name} down {pct}% against the {comparison}?", vars);
}

/** A ratio's change from its parts' changes, e.g. average order value from sales and orders. */
export function ratioChangePct(numeratorPct: number | null | undefined, denominatorPct: number | null | undefined): number | null {
  if (numeratorPct == null || denominatorPct == null) return null;
  return ((1 + numeratorPct / 100) / (1 + denominatorPct / 100) - 1) * 100;
}

/** Approval itself happens on the change card; this banner hands off to the assistant. */
export function ApprovalsBanner({ changes, onReview }: { changes: { change_id: string; summary: string }[]; onReview: () => void }) {
  const t = useT();
  if (changes.length === 0) return null;
  return (
    <section className="flex flex-wrap items-center gap-x-4 gap-y-2 rounded-2xl border border-(--violet)/20 bg-(--violet-soft) px-[18px] py-3">
      <KindIcon icon="edit" tone="violet" size={32} />
      <div className="min-w-0 flex-1">
        <div className="text-[14px] font-semibold text-(--ink)">{changes.length === 1 ? t("{n} change awaiting approval", { n: changes.length }) : t("{n} changes awaiting approval", { n: changes.length })}</div>
        <div className="mt-0.5 truncate text-[12.5px] text-(--ink-soft)">{changes.map((change) => change.summary).join(" · ")}</div>
      </div>
      <Button variant="primary" size="sm" onClick={onReview}>
        {t("Review")}
      </Button>
    </section>
  );
}

/** One row of the home queue or an issue list: kind icon, title, one metadata line, one hand-off. */
export function AttentionRow({
  icon,
  tone,
  title,
  meta,
  note,
  action,
}: {
  icon: IconName;
  tone: Tone;
  title: ReactNode;
  meta: ReactNode;
  /** A pill or quote under the metadata line. */
  note?: ReactNode;
  action: { label: string; onClick: () => void };
}) {
  return (
    <li className={`flex gap-3 px-2.5 py-2.5 ${note ? "items-start" : "items-center"}`}>
      <KindIcon icon={icon} tone={tone} />
      <div className="min-w-0 flex-1">
        <div className="text-[13.5px] font-medium leading-snug text-(--ink)">{title}</div>
        <div className="mt-0.5 text-[12.5px] leading-snug tabular-nums text-(--ink-soft)">{meta}</div>
        {note ? <div className="mt-1.5">{note}</div> : null}
      </div>
      <AskButton label={action.label} onClick={action.onClick} />
    </li>
  );
}

export function AttentionList({ children }: { children: ReactNode }) {
  return <ul className="divide-y divide-(--line) px-2 pb-1">{children}</ul>;
}

/** The footer under a capped queue; the link goes to the view that lists the hidden rows, if one does. */
export function QueueOverflow({ hidden, link }: { hidden: number; link?: { label: string; onClick: () => void } }) {
  const t = useT();
  if (hidden <= 0) return null;
  return (
    <div className="flex items-center gap-2 border-t border-(--line) px-[18px] py-2.5 text-[12.5px] text-(--ink-soft)">
      <span>{hidden === 1 ? t("{n} more item in the queue", { n: hidden }) : t("{n} more items in the queue", { n: hidden })}</span>
      {link ? <ViewLink label={link.label} onClick={link.onClick} className="ml-auto" /> : null}
    </div>
  );
}

/** "All orders →" style link to another view. */
export function ViewLink({ label, onClick, className = "" }: { label: string; onClick: () => void; className?: string }) {
  return (
    <button type="button" onClick={onClick} className={`inline-flex items-center gap-1 text-[12.5px] font-semibold text-(--ink) hover:underline ${className}`}>
      {label} <Icon name="arrow-right" size={13} />
    </button>
  );
}

export interface RecordRowData {
  id: string;
  /** Beside the id: "2 items", "3 nights". */
  detail?: string;
  /** Under the id: date and amount. */
  sub: string;
  status: { label: string; tone: Tone };
}

/** Recent orders or bookings: id, a detail, a second line, and a status pill. */
export function RecordList({ rows, mono = false }: { rows: RecordRowData[]; mono?: boolean }) {
  return (
    <ul className="divide-y divide-(--line) px-[18px] pb-2">
      {rows.map((row) => (
        <li key={row.id} className="flex items-center gap-3 py-2.5">
          <div className="min-w-0 flex-1 tabular-nums">
            <div className="text-[13px] font-semibold text-(--ink)">
              <span className={mono ? "font-mono" : ""}>{row.id}</span>
              {row.detail ? <span className="ml-1.5 text-[12.5px] font-normal text-(--ink-soft)">· {row.detail}</span> : null}
            </div>
            <div className="text-[12px] text-(--ink-soft)">{row.sub}</div>
          </div>
          <Pill tone={row.status.tone} dot>
            {row.status.label}
          </Pill>
        </li>
      ))}
    </ul>
  );
}

interface ChangeSummary {
  change_id: string;
  status: "staged" | "applied" | "discarded" | "expired";
  summary: string;
  created_by: string;
  created_by_kind?: "operator" | "agent";
  applied_at?: string | null;
  applied_by?: string | null;
  discarded_at?: string | null;
  discarded_by?: string | null;
  discarded_by_kind?: "operator" | "agent" | null;
  expired_at?: string | null;
}

/** The last few resolved changes, newest first. */
export function RecentChanges({ changes, limit = 4 }: { changes: ChangeSummary[]; limit?: number }) {
  const t = useT();
  if (changes.length === 0) return null;
  return (
    <Panel title={t("Recent changes")}>
      <ul className="divide-y divide-(--line) px-[18px] pb-2">
        {changes.slice(0, limit).map((change) => {
          const status = CHANGE_STATUS[change.status];
          const actedAt =
            change.status === "applied" ? change.applied_at : change.status === "expired" ? change.expired_at : change.discarded_at;
          return (
            <li key={change.change_id} className="py-2.5">
              <div className="flex items-start gap-2">
                <div className="line-clamp-2 min-w-0 flex-1 text-[13px] font-medium leading-snug text-(--ink)" title={change.summary}>
                  {change.summary}
                </div>
                <Pill tone={status.tone} dot>
                  {t(status.label)}
                </Pill>
              </div>
              <div className="mt-0.5 text-[12px] text-(--ink-soft)">
                {describeResolver(change, t) ?? describeProposer(change, t)}
                {actedAt ? ` · ${formatDayMonth(actedAt)}` : ""}
              </div>
            </li>
          );
        })}
      </ul>
    </Panel>
  );
}
