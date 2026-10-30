// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** The frame the merchant presentation cards share; each vertical fills in its own rows. */

import { type ReactNode, useEffect, useState } from "react";
import { describeApply, type FieldKinds, formatDate, formatFieldValue, formatMoney, humanizeField } from "../format";
import { type Translate, useT } from "../i18n";
import { Icon, type IconName } from "../icons";
import { AskButton, Button, KindIcon, Pill, type Tone } from "../ui";
import type { ChangeAction, ChangeActionHandler } from "./merchant";

export function GenCard({ children, className = "" }: { children: ReactNode; className?: string }) {
  return (
    <section className={`ac-reveal overflow-hidden rounded-[14px] border border-(--line) bg-(--card) shadow-(--shadow) ${className}`}>
      {children}
    </section>
  );
}

export function GenCardHeader({ title, aside, meta }: { title: ReactNode; aside?: ReactNode; meta?: ReactNode }) {
  return (
    <div className="px-3.5 pt-3">
      <div className="flex items-start gap-2">
        <h3 className="min-w-0 flex-1 text-[14px] font-semibold leading-snug text-(--ink)">{title}</h3>
        {aside ? <div className="shrink-0 text-[12px] text-(--ink-soft)">{aside}</div> : null}
      </div>
      {meta ? <div className="mt-1 flex flex-wrap items-center gap-x-1.5 gap-y-1 text-[12.5px] text-(--ink-soft)">{meta}</div> : null}
    </div>
  );
}

// --- Digest rows ---

export function DigestRow({
  icon,
  tone,
  headline,
  why,
  context,
  action,
}: {
  icon: IconName;
  tone: Tone;
  headline: ReactNode;
  why?: ReactNode;
  context?: ReactNode;
  action?: { label: string; onClick: () => void } | null;
}) {
  return (
    <li className="flex gap-2.5 px-2 py-2">
      <KindIcon icon={icon} tone={tone} size={30} />
      <div className="min-w-0 flex-1">
        <div className="text-[13px] font-medium leading-snug text-(--ink)">{headline}</div>
        {why ? <div className="mt-0.5 text-[12px] leading-snug text-(--ink-soft)">{why}</div> : null}
        {context || action ? (
          <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-[12px] tabular-nums text-(--ink-soft)">
            {context}
            {action ? <AskButton label={action.label} onClick={action.onClick} /> : null}
          </div>
        ) : null}
      </div>
    </li>
  );
}

export function DigestList({ children }: { children: ReactNode }) {
  return <ul className="divide-y divide-(--line) px-1.5 pb-1.5 pt-1">{children}</ul>;
}

// --- Change preview ---

interface ChangeLike {
  change_id: string;
  kind: string;
  items: DiffItem[];
  status: "staged" | "applied" | "discarded" | "expired";
  applied_at?: string | null;
  applied_by?: string | null;
  discarded_by?: string | null;
  discarded_by_kind?: "operator" | "agent" | null;
  expired_at?: string | null;
}

export const CHANGE_STATUS: Record<ChangeLike["status"], { tone: Tone; label: string }> = {
  staged: { tone: "violet", label: "Awaiting approval" },
  applied: { tone: "ok", label: "Approved" },
  discarded: { tone: "muted", label: "Dismissed" },
  expired: { tone: "warn", label: "Expired" },
};

export function ChangeStatusPill({ status }: { status: ChangeLike["status"] }) {
  const t = useT();
  const { tone, label } = CHANGE_STATUS[status];
  return (
    <Pill tone={tone} dot>
      {t(label)}
    </Pill>
  );
}

/**
 * Tracks the change a card shows: starts from the streamed payload, is replaced by the API
 * response when the operator acts, and re-syncs when a later turn rewrites the payload.
 */
export function useChangeActions<T extends ChangeLike>(streamed: T, onAct?: ChangeActionHandler<T>) {
  const t = useT();
  const [change, setChange] = useState<T>(streamed);
  useEffect(() => {
    setChange(streamed);
  }, [streamed]);
  const [busy, setBusy] = useState<ChangeAction | null>(null);
  const [error, setError] = useState<string | null>(null);

  const act = async (action: ChangeAction) => {
    if (!onAct || busy) return;
    setBusy(action);
    setError(null);
    const result = await onAct(change.change_id, action);
    if (result?.change) setChange(result.change);
    // A change that came back (expired) says so in its own status line.
    else if (result?.reason)
      setError(action === "apply" ? t("Not applied: {reason}", { reason: result.reason }) : t("Not dismissed: {reason}", { reason: result.reason }));
    else setError(t("That action did not go through. Check the API and try again."));
    setBusy(null);
  };

  return { change, busy, error, act, canAct: Boolean(onAct) };
}

/** Approve and Dismiss go through the same change gate the assistant uses. */
export function ApproveBar({
  change,
  busy,
  error,
  canAct,
  onAct,
}: {
  change: ChangeLike;
  busy: ChangeAction | null;
  error: string | null;
  canAct: boolean;
  onAct: (action: ChangeAction) => void;
}) {
  const t = useT();
  return (
    <div className="px-3.5 pb-3.5 pt-3">
      {change.status === "staged" ? <p className="mb-2.5 text-[13px] leading-snug text-(--ink)">{describeApply(change, t)}</p> : null}
      {change.status === "staged" ? (
        <div className="flex flex-wrap items-center gap-2">
          <Button variant="accent" size="sm" icon="check" onClick={() => onAct("apply")} disabled={busy !== null || !canAct}>
            {busy === "apply" ? t("Applying…") : t("Approve")}
          </Button>
          <Button variant="secondary" size="sm" onClick={() => onAct("discard")} disabled={busy !== null || !canAct}>
            {busy === "discard" ? t("Dismissing…") : t("Dismiss")}
          </Button>
          <span className="text-[11.5px] leading-tight text-(--ink-soft)">{t("Nothing applies until you approve.")}</span>
        </div>
      ) : (
        <div className="flex items-center gap-2 text-[13px] text-(--ink-soft)">
          <Icon
            name={change.status === "applied" ? "check" : change.status === "expired" ? "clock" : "x"}
            size={15}
            className={change.status === "applied" ? "text-(--ok)" : change.status === "expired" ? "text-(--warn)" : "text-(--ink-faint)"}
          />
          {change.status === "applied" ? approvedLine(change, t) : change.status === "expired" ? expiredLine(change, t) : dismissedLine(change, t)}
        </div>
      )}
      {error ? <div className="mt-2 text-[13px] text-(--danger)">{error}</div> : null}
    </div>
  );
}

/** "Approved by Dana on Jun 24, 2026." with either part left out when unknown. */
function approvedLine(change: ChangeLike, t: Translate): string {
  const name = change.applied_by;
  const date = change.applied_at ? formatDate(change.applied_at) : null;
  if (name && date) return t("Approved by {name} on {date}.", { name, date });
  if (name) return t("Approved by {name}.", { name });
  if (date) return t("Approved on {date}.", { date });
  return t("Approved.");
}

function expiredLine(change: ChangeLike, t: Translate): string {
  return change.expired_at
    ? t("Expired unapproved on {date}. Nothing was changed.", { date: formatDate(change.expired_at) })
    : t("Expired unapproved. Nothing was changed.");
}

function dismissedLine(change: ChangeLike, t: Translate): string {
  const name = change.discarded_by;
  if (!name) return t("Dismissed. Nothing was changed.");
  return change.discarded_by_kind === "agent"
    ? t("Dismissed by {name}'s assistant. Nothing was changed.", { name })
    : t("Dismissed by {name}. Nothing was changed.", { name });
}

export interface DiffItem {
  target: string;
  field: string;
  before?: unknown;
  after?: unknown;
}

/** Characters; longer values render as stacked before/after blocks. */
const LONG_TEXT_THRESHOLD = 48;

export function isLongTextDiff(item: DiffItem): boolean {
  return [item.before, item.after].some(
    (value) => typeof value === "string" && (value.length > LONG_TEXT_THRESHOLD || value.includes("\n")),
  );
}

/** One row per short field change: target, field, before struck through, after bold. */
export function DiffRows({
  items,
  fields,
  targetLabel,
}: {
  items: DiffItem[];
  /** The vertical's own currency or percent field names, beyond the shared ones. */
  fields?: FieldKinds;
  /** Names a target id, e.g. the record's title; the id shows beside it. */
  targetLabel?: (target: string) => string | null | undefined;
}) {
  const t = useT();
  if (!items.length) return null;
  const formatValue = (field: string, value: unknown) => formatFieldValue(field, value, fields);
  return (
    <div className="mx-3.5 mt-2.5 divide-y divide-(--line) rounded-[11px] bg-(--ground)">
      {items.map((item, index) => {
        const name = targetLabel?.(item.target);
        return (
          <div key={`${item.target}-${item.field}-${index}`} className="flex flex-wrap items-baseline justify-between gap-x-3 gap-y-1 px-3 py-2">
            <div className="min-w-0 text-[12.5px] text-(--ink-soft)">
              {name ? <span className="font-semibold text-(--ink)">{name} </span> : null}
              <span className="tabular-nums">{item.target}</span>
              <span> · {t(humanizeField(item.field))}</span>
            </div>
            <div className="flex min-w-0 flex-wrap items-baseline gap-x-1.5 text-[14px] tabular-nums break-words">
              <s className="min-w-0 text-(--ink-soft) decoration-(--ink-faint)">{formatValue(item.field, item.before)}</s>
              <Icon name="arrow-right" size={13} className="self-center text-(--ink-faint)" />
              <b className="min-w-0 text-[15px] font-bold text-(--ink)">{formatValue(item.field, item.after)}</b>
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function LongTextDiff({ item }: { item: DiffItem }) {
  const t = useT();
  const formatValue = (field: string, value: unknown) => formatFieldValue(field, value);
  return (
    <div className="mx-3.5 mt-2.5 overflow-hidden rounded-[11px] border border-(--line)">
      <div className="flex items-baseline gap-2 border-b border-(--line) bg-(--ground) px-3 py-1.5 text-[12px]">
        <span className="font-semibold text-(--ink)">{t(humanizeField(item.field))}</span>
        <span className="tabular-nums text-(--ink-soft)">{item.target}</span>
      </div>
      <div className="grid gap-2 px-3 py-2.5 text-[13px] leading-snug">
        <div>
          <div className="text-[11.5px] font-semibold text-(--ink-soft)">{t("Before")}</div>
          <p className="mt-0.5 whitespace-pre-line break-words text-(--ink-soft)">{formatValue(item.field, item.before)}</p>
        </div>
        <div>
          <div className="text-[11.5px] font-semibold text-(--ink)">{t("After")}</div>
          <p className="mt-0.5 whitespace-pre-line break-words font-medium text-(--ink)">{formatValue(item.field, item.after)}</p>
        </div>
      </div>
    </div>
  );
}

/** For a single price move with margins: the new price against cost and the old price. */
export function MarginHeadroom({
  change,
  costLabel,
}: {
  change: ChangeLike & { items: DiffItem[]; margin_before_pct?: number | null; margin_after_pct?: number | null };
  /** "Unit cost", "Nightly cost", "Per-ticket cost". */
  costLabel: string;
}) {
  const t = useT();
  const item = change.items.length === 1 ? change.items[0] : null;
  if (!item || typeof item.before !== "number" || typeof item.after !== "number" || change.margin_before_pct == null || change.margin_after_pct == null) {
    return null;
  }
  // cost = price × (1 − margin%); the bar turns red when the new price is at or below cost.
  const cost = item.after * (1 - change.margin_after_pct / 100);
  const top = Math.max(item.before, item.after);
  const at = (value: number) => `${Math.max(0, Math.min(100, (value / top) * 100))}%`;
  const headroom = item.after - cost;
  const deltaPts = change.margin_after_pct - change.margin_before_pct;
  return (
    <div className="mx-3.5 mt-2.5">
      <div
        className="relative h-2 rounded-full bg-(--well)"
        role="img"
        aria-label={t("New price {price}, previous {previous}, {cost} {amount}", {
          price: formatMoney(item.after),
          previous: formatMoney(item.before),
          cost: costLabel.toLowerCase(),
          amount: formatMoney(cost),
        })}
      >
        <div className={`absolute inset-y-0 left-0 rounded-full ${headroom > 0 ? "bg-(--accent)" : "bg-(--danger)"}`} style={{ width: at(item.after) }} />
        <div className="absolute -inset-y-0.5 w-0.5 rounded bg-(--danger)" style={{ left: at(cost) }} />
        <div className="absolute -inset-y-0.5 w-0.5 rounded bg-(--ink-soft)/70" style={{ left: at(item.before) }} />
      </div>
      <p className="mt-1.5 text-[12.5px] tabular-nums text-(--ink-soft)">
        {costLabel} {formatMoney(cost)} · <b className="font-semibold text-(--ink)">{t("{amount} headroom", { amount: formatMoney(headroom) })}</b> ·{" "}
        {t("{delta} margin pts", { delta: `${deltaPts >= 0 ? "+" : ""}${deltaPts.toFixed(1)}` })}
      </p>
    </div>
  );
}

/** Floor, current price, and ceiling on one track. */
export function PriceBand({ current, floor, ceiling }: { current: number; floor: number; ceiling: number }) {
  const t = useT();
  // Pad the track so the floor and ceiling labels never sit on its ends.
  const low = Math.min(floor, current) * 0.8;
  const high = Math.max(ceiling, current) * 1.12;
  const at = (value: number) => `${((value - low) / (high - low)) * 100}%`;
  return (
    <div className="relative mt-1 h-[54px]" role="img" aria-label={t("{price} now, floor {floor}, ceiling {ceiling}", { price: formatMoney(current), floor: formatMoney(floor), ceiling: formatMoney(ceiling) })}>
      <div className="absolute inset-x-0 top-[22px] h-2 rounded-full bg-(--well)" />
      <div className="absolute top-[22px] h-2 rounded-full bg-(--accent)/70" style={{ left: at(floor), right: `calc(100% - ${at(ceiling)})` }} />
      <div className="absolute top-[15px] h-[22px] w-[3px] -translate-x-1/2 rounded bg-(--ink)" style={{ left: at(current) }} />
      <span className="absolute top-0 -translate-x-1/2 whitespace-nowrap text-[11.5px] font-semibold tabular-nums text-(--ink)" style={{ left: at(current) }}>
        {t("{price} now", { price: formatMoney(current) })}
      </span>
      <span className="absolute top-[36px] -translate-x-1/2 whitespace-nowrap text-[11.5px] tabular-nums text-(--ink-soft)" style={{ left: at(floor) }}>
        {t("floor {price}", { price: formatMoney(floor) })}
      </span>
      <span className="absolute top-[36px] -translate-x-1/2 whitespace-nowrap text-[11.5px] tabular-nums text-(--ink-soft)" style={{ left: at(ceiling) }}>
        {t("ceiling {price}", { price: formatMoney(ceiling) })}
      </span>
    </div>
  );
}

export function GuardrailNotes({ notes }: { notes?: string[] | null }) {
  if (!notes?.length) return null;
  return (
    <ul className="mx-3.5 mt-2.5 space-y-1 rounded-[11px] bg-(--warn-soft) px-3 py-2 text-[12.5px] leading-snug text-(--ink)">
      {notes.map((note) => (
        <li key={note} className="flex gap-2">
          <Icon name="alert" size={14} className="mt-[2px] text-(--warn)" />
          <span>{note}</span>
        </li>
      ))}
    </ul>
  );
}
