// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import type { ReactNode } from "react";
import { evidenceLabel } from "./format";
import { type Translate, useT } from "./i18n";
import { Icon } from "./icons";
import { AssistantText, ErrorBubble, UserBubble } from "./MessageBubble";
import type { AssistantChatItem, ChatItem, HandoffBrief, UISegment } from "./protocol";
import { Suggestions } from "./Suggestions";
import { describeToolCall } from "./tool-copy";
import { Pill } from "./ui";

export interface TranscriptProps {
  items: ChatItem[];
  busy: boolean;
  send: (text: string) => void;
  renderBlock: (segment: UISegment, item: AssistantChatItem) => ReactNode;
  /** Defaults to `ActivityLine`. */
  renderPending?: (item: AssistantChatItem) => ReactNode;
  suggestionFilter?: (text: string) => boolean;
  /** Components that may extend past the text measure when the page has room. */
  wide?: ReadonlySet<string>;
  gap?: string;
  /** Votes on a finished reply; without it no vote buttons show. */
  onRate?: (turn: number, helpful: boolean) => void;
  /** Asks for a person from the latest reply; without it no handoff button shows. */
  onHandoff?: (turn: number) => void;
  /** The handoff button's label ("Talk to a person"); translated here. */
  handoffLabel?: string;
}

/** A handoff brief as the customer reads it: one line per step the assistant took (loading a
 * skill is not one), then the terms it read. */
function checkedSteps(brief: HandoffBrief, t: Translate): string[] {
  const steps = brief.tried.tools
    .filter(({ name }) => name !== "load_skill")
    .map(({ name, status }) => {
      const step = describeToolCall(name, {}, t).replace(/…$/, "");
      if (status === "blocked") return t("{step} (held by a store rule)", { step });
      if (status === "error") return t("{step} (did not go through)", { step });
      return step;
    });
  const terms = brief.evidence_versions
    .filter((entry) => entry.status !== "superseded")
    .map((entry) => {
      const label = t("{source} v{version}", { source: entry.source_id, version: entry.version });
      return entry.status === "current" ? label : t("{terms} (not applied)", { terms: label });
    });
  if (terms.length) steps.push(t("Store terms: {terms}", { terms: terms.join(" · ") }));
  if (brief.tried.fallbacks.includes("no_terms_match")) steps.push(t("The store terms had no answer"));
  return [...new Set(steps)];
}

/** Under a finished reply: the vote, a person to hand off to, or the ticket a handoff opened. */
function ReplyFooter({
  item,
  latest,
  onRate,
  onHandoff,
  handoffLabel = "Talk to a person",
}: {
  item: AssistantChatItem;
  latest: boolean;
  onRate?: TranscriptProps["onRate"];
  onHandoff?: TranscriptProps["onHandoff"];
  handoffLabel?: string;
}) {
  const t = useT();
  if (item.ticket) {
    const steps = item.handoff ? checkedSteps(item.handoff, t) : [];
    return (
      <div role="status" className="flex flex-col gap-1.5 text-[13px] text-(--ink-soft)">
        <p className="flex items-center gap-2">
          <Icon name="headset" size={15} />
          {t("A person will pick this up from here. Ticket {ticket}.", { ticket: item.ticket })}
        </p>
        {steps.length ? (
          <div className="pl-[23px] text-[12.5px] leading-snug">
            <p className="text-(--ink-faint)">{t("What the assistant already checked")}</p>
            <ul className="mt-0.5 list-disc pl-4">
              {steps.map((step) => (
                <li key={step} className="break-words">
                  {step}
                </li>
              ))}
            </ul>
          </div>
        ) : null}
        {item.handoff?.request ? (
          <p className="pl-[23px] text-[12px] text-(--ink-faint)">{t("Your last message goes with the ticket too.")}</p>
        ) : null}
      </div>
    );
  }
  const canRate = Boolean(onRate && item.turnId);
  const canHandOff = Boolean(onHandoff && latest);
  if (!canRate && !canHandOff) return null;
  const vote = (helpful: boolean, icon: "thumb-up" | "thumb-down", label: string) => {
    const chosen = item.rating === (helpful ? "up" : "down");
    return (
      <button
        type="button"
        onClick={() => onRate?.(item.turn, helpful)}
        aria-label={t(label)}
        aria-pressed={chosen}
        title={t(label)}
        className={`grid h-7 w-7 place-items-center rounded-md transition-colors hover:bg-(--well) ${
          chosen ? "text-(--ink)" : "text-(--ink-faint)"
        }`}
      >
        <Icon name={icon} size={15} />
      </button>
    );
  };
  return (
    <div className="-mt-1 flex items-center gap-1 text-[12.5px]">
      {canRate ? (
        <>
          {vote(true, "thumb-up", "Helpful")}
          {vote(false, "thumb-down", "Not helpful")}
        </>
      ) : null}
      {canHandOff ? (
        <button
          type="button"
          onClick={() => onHandoff?.(item.turn)}
          className={`ml-1 inline-flex h-7 items-center gap-1.5 rounded-md px-2 transition-colors hover:bg-(--well) ${
            item.rating === "down" || item.segments.some((s) => s.type === "error")
              ? "text-(--ink)"
              : "text-(--ink-faint)"
          }`}
        >
          <Icon name="headset" size={15} />
          {t(handoffLabel)}
        </button>
      ) : null}
    </div>
  );
}

/** Under a finished reply that read store terms: each current version it rested on. A card that
 * cites terms shows them itself, so the line is left out when one did. */
function SourcesLine({ item }: { item: AssistantChatItem }) {
  const t = useT();
  if (!item.sources?.length) return null;
  const cardCites = item.segments.some((s) => {
    const payload = s.type === "ui" ? (s.block.payload as { evidence?: unknown[] } | null) : null;
    return Boolean(payload?.evidence?.length);
  });
  if (cardCites) return null;
  return (
    <p className="-mt-1 break-words text-[11.5px] leading-snug text-(--ink-faint)">
      {t("Terms in force")}: {item.sources.map((source) => evidenceLabel(source, t)).join(" · ")}
    </p>
  );
}

/** The label that says the assistant is an AI, shown in each chat surface's header for as long as
 * it is on screen. `compact` shortens the visible text to "AI" below `sm`; the accessible name
 * stays whole. */
export function AiLabel({ compact = false }: { compact?: boolean }) {
  const t = useT();
  const label = t("AI assistant");
  return (
    <span role="note" aria-label={label} className="inline-flex shrink-0">
      <Pill tone="muted" title={label}>
        <Icon name="spark" size={12} />
        {compact ? (
          <>
            <span aria-hidden className="sm:hidden">AI</span>
            <span aria-hidden className="hidden sm:inline">{label}</span>
          </>
        ) : (
          <span aria-hidden>{label}</span>
        )}
      </Pill>
    </span>
  );
}

/** At the start of every conversation: the replies that follow are generated by AI. */
function AiNotice() {
  const t = useT();
  return (
    <p role="note" className="flex items-center justify-center gap-1.5 text-[12px] text-(--ink-soft)">
      <Icon name="spark" size={13} />
      {t("The replies below are generated by AI")}
    </p>
  );
}

/** What shows under a reply while it is being made: the current step, or a shimmer before the first word. */
export function ActivityLine({ item }: { item: AssistantChatItem }) {
  const t = useT();
  if (item.activity) {
    return (
      <div role="status" className="flex items-center gap-2 text-[13px] text-(--ink-soft)">
        <span className="inline-block h-1.5 w-1.5 animate-pulse rounded-full bg-(--accent)" />
        <span className="min-w-0 truncate">{item.activity}</span>
      </div>
    );
  }
  if (item.segments.length) return null;
  return (
    <div role="status" aria-label={t("Working")} className="flex flex-col gap-2">
      <div className="ac-skeleton h-4 w-3/5 rounded" />
      <div className="ac-skeleton h-4 w-2/5 rounded" />
    </div>
  );
}

export function Transcript({
  items,
  busy,
  send,
  renderBlock,
  renderPending = (item) => <ActivityLine item={item} />,
  suggestionFilter,
  wide,
  gap = "gap-3",
  onRate,
  onHandoff,
  handoffLabel,
}: TranscriptProps) {
  if (!items.length) return null;
  const replies = items.map((item, index) =>
    item.kind === "user" ? (
      <UserBubble key={index} text={item.text} />
    ) : (
      <div key={index} data-turn={item.turn} className={`flex flex-col ${gap}`}>
        {item.segments.map((segment, i) => {
          if (segment.type === "text") {
            const last = item.pending && i === item.segments.length - 1;
            return <AssistantText key={i} text={segment.text} streaming={last} />;
          }
          if (segment.type === "error") return <ErrorBubble key={i} text={segment.text} />;
          return (
            <div
              key={segment.slotKey}
              data-component={segment.block.component}
              className={`transition-opacity duration-300 ${segment.status === "retrying" ? "opacity-60" : ""} ${
                wide?.has(segment.block.component) ? "min-[1500px]:-mx-14" : ""
              }`}
            >
              {renderBlock(segment, item)}
            </div>
          );
        })}
        {item.pending ? renderPending(item) : null}
        {!item.pending ? <SourcesLine item={item} /> : null}
        {!item.pending ? (
          <ReplyFooter
            item={item}
            latest={index === items.length - 1}
            onRate={onRate}
            onHandoff={onHandoff}
            handoffLabel={handoffLabel}
          />
        ) : null}
        {!item.pending && index === items.length - 1 ? (
          <Suggestions
            suggestions={suggestionFilter ? item.suggestions.filter(suggestionFilter) : item.suggestions}
            onPick={send}
            disabled={busy || item.suggestionsStale}
          />
        ) : null}
      </div>
    ),
  );
  return (
    <>
      <AiNotice />
      {replies}
    </>
  );
}

export function LatestPill({ onClick }: { onClick: () => void }) {
  const t = useT();
  return (
    <div className="pointer-events-none absolute inset-x-0 bottom-3 flex justify-center">
      <button
        type="button"
        onClick={onClick}
        className="pointer-events-auto rounded-full border border-(--line) bg-(--card) px-3.5 py-1.5 text-[13px] font-semibold text-(--ink) shadow-md transition hover:border-(--accent)"
      >
        ↓ {t("Latest")}
      </button>
    </div>
  );
}
