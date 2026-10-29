// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useEffect } from "react";
import { ActivityButton } from "../ActivityButton";
import { Composer, type Prefill } from "../Composer";
import { useT } from "../i18n";
import { Icon } from "../icons";
import { useStickToBottom } from "../scroll";
import { AiLabel, LatestPill, Transcript, type TranscriptProps } from "../Transcript";
import type { AgentTurn } from "../turn";
import { IconButton } from "../ui";

/** Under host approval only a card's own buttons can act, so approve/dismiss chips never render. */
const ACTION_CHIP = /\b(approve|apply|dismiss|discard)\b|批准|驳回|丢弃|应用更改|应用此|应用该/i;
const isPlainChip = (text: string) => !ACTION_CHIP.test(text);

export interface AssistantPanelCopy {
  title: string;
  intro: string;
  starters: string[];
  /** aria-label of the message box. */
  label: string;
  placeholder: string;
}

/** The merchant portals' assistant rail. */
export function AssistantPanel({
  chat,
  copy,
  renderBlock,
  prefill,
  newMemoryCount,
  onOpenActivity,
  onClose,
  fullscreen = false,
  onToggleFullscreen,
}: {
  chat: AgentTurn;
  copy: AssistantPanelCopy;
  renderBlock: TranscriptProps["renderBlock"];
  prefill?: Prefill | null;
  newMemoryCount: number;
  onOpenActivity: () => void;
  onClose: () => void;
  fullscreen?: boolean;
  onToggleFullscreen?: () => void;
}) {
  const t = useT();
  const { scrollRef, onScroll, showLatest, jumpToLatest } = useStickToBottom(chat.items, chat.busy, {
    onlyWhileBusy: true,
  });

  // Scrolls a settled reply to its first card. Keyed on turnCount as well as busy so a reply
  // that settles within one render still scrolls.
  useEffect(() => {
    if (chat.busy) return;
    const container = scrollRef.current;
    const replies = container?.querySelectorAll<HTMLElement>("[data-turn]");
    const reply = replies?.[replies.length - 1];
    if (!container || !reply) return;
    const target = reply.querySelector<HTMLElement>("[data-component]") ?? reply;
    const top = target.getBoundingClientRect().top - container.getBoundingClientRect().top + container.scrollTop;
    container.scrollTo({ top: Math.max(0, top - 8), behavior: "smooth" });
  }, [chat.busy, chat.turnCount, scrollRef]);

  const column = fullscreen ? "mx-auto w-full max-w-3xl" : "";

  return (
    <div className="flex h-full w-full flex-col border-l border-(--line) bg-(--card)">
      <div className="flex items-center gap-2.5 border-b border-(--line) py-3 pl-4 pr-2.5">
        <span className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-[10px] bg-(--accent) text-(--on-accent)" aria-hidden>
          <Icon name="spark" size={15} />
        </span>
        <div className="min-w-0 flex-1">
          <div className="flex min-w-0 items-center gap-2">
            <span className="truncate text-[14px] font-semibold leading-tight text-(--ink)">{copy.title}</span>
            <AiLabel />
          </div>
          <div className="truncate text-[11.5px] text-(--ink-soft)">{t("You approve every change")}</div>
        </div>
        <ActivityButton streaming={chat.streaming} newMemoryCount={newMemoryCount} onClick={onOpenActivity} />
        {onToggleFullscreen ? (
          <IconButton
            icon={fullscreen ? "collapse" : "expand"}
            label={fullscreen ? t("Exit full screen") : t("Full screen")}
            onClick={onToggleFullscreen}
            className="hidden lg:grid"
          />
        ) : null}
        <IconButton icon="x" label={t("Hide assistant")} onClick={onClose} />
      </div>

      <div className="relative min-h-0 flex-1">
        <div ref={scrollRef} onScroll={onScroll} className="panel-scroll h-full overflow-y-auto px-4 py-4">
          <div className={`flex flex-col gap-3 text-[14.5px] ${column}`}>
            {chat.items.length === 0 ? (
              <div className="mt-4">
                <p className="text-[16px] leading-relaxed text-(--ink)">{copy.intro}</p>
                <div className="mt-4 flex flex-col gap-2">
                  {copy.starters.map((starter) => (
                    <button
                      key={starter}
                      type="button"
                      onClick={() => void chat.send(starter)}
                      disabled={chat.busy || !chat.ready}
                      className="group flex items-center gap-3 rounded-xl border border-(--line) bg-(--card) px-3.5 py-2.5 text-left text-[13.5px] text-(--ink) shadow-(--shadow-sm) transition hover:border-(--accent) hover:bg-(--accent-soft) disabled:opacity-50"
                    >
                      <Icon name="spark" size={14} className="text-(--accent)" />
                      <span className="min-w-0 flex-1">{starter}</span>
                      <Icon name="arrow-right" size={14} className="text-(--ink-faint) transition group-hover:text-(--accent-ink)" />
                    </button>
                  ))}
                </div>
              </div>
            ) : (
              <Transcript
                items={chat.items}
                busy={chat.busy}
                send={chat.send}
                renderBlock={renderBlock}
                suggestionFilter={isPlainChip}
                gap="gap-2.5"
                onRate={chat.rate}
                onHandoff={(turn) => void chat.handoff(turn)}
                handoffLabel="Escalate to support"
              />
            )}
          </div>
        </div>
        {showLatest ? <LatestPill onClick={jumpToLatest} /> : null}
      </div>

      <div className="border-t border-(--line) p-3">
        <Composer
          send={chat.send}
          ready={chat.ready}
          busy={chat.busy}
          label={copy.label}
          placeholder={copy.placeholder}
          prefill={prefill}
          variant="field"
          className={column}
        />
      </div>
    </div>
  );
}
