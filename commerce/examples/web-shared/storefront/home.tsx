// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** The blocks a storefront's home is built from, and the shopper's sheet. */

import { type ReactNode, useState } from "react";
import type { AgentApi } from "../api";
import { formatDayMonth } from "../format";
import { useT } from "../i18n";
import { Icon, type IconName } from "../icons";
import type { MemoryFact } from "../protocol";
import { Button, Pill, Sheet } from "../ui";
import { useStoreFrame } from "./frame";

/** The home's opening: the vertical's headline, then one brief line of what is going on. */
export function Greeting({ eyebrow, title, children }: { eyebrow?: ReactNode; title: ReactNode; children?: ReactNode }) {
  return (
    <div className="ac-reveal pt-2">
      {eyebrow ? <div className="mb-1.5 text-[12px] font-semibold tracking-[0.02em] text-(--ink-soft)">{eyebrow}</div> : null}
      {title}
      {children ? <p className="mt-2 max-w-[62ch] text-[15px] leading-relaxed text-(--ink-2)">{children}</p> : null}
    </div>
  );
}

export interface Starter {
  icon: IconName;
  prompt: string;
}

/** The ways to begin; each sends its prompt as the first message. */
export function Starters({ items }: { items: Starter[] }) {
  const { ask, chat } = useStoreFrame();
  const disabled = !chat || chat.busy || !chat.ready;
  return (
    <div className="grid gap-2.5 sm:grid-cols-2">
      {items.map((item, index) => (
        <button
          key={item.prompt}
          type="button"
          onClick={() => ask(item.prompt)}
          disabled={disabled}
          className="ac-reveal group flex items-center gap-3 rounded-(--radius) border border-(--line) bg-(--card) px-3.5 py-3 text-left shadow-(--shadow-sm) transition hover:border-(--accent) disabled:opacity-50"
          style={{ animationDelay: `${60 + index * 50}ms` }}
        >
          <span className="grid h-[30px] w-[30px] shrink-0 place-items-center rounded-lg bg-(--accent-soft) text-(--accent)">
            <Icon name={item.icon} size={16} />
          </span>
          <span className="min-w-0 flex-1 text-[14px] leading-snug text-(--ink)">{item.prompt}</span>
          <Icon name="arrow-right" size={15} className="shrink-0 text-(--ink-faint) transition-colors group-hover:text-(--accent)" />
        </button>
      ))}
    </div>
  );
}

/** A titled block on the home that is not a card (a product strip). */
export function HomeSection({ title, subtitle, children }: { title: string; subtitle?: ReactNode; children: ReactNode }) {
  return (
    <section className="ac-reveal" style={{ animationDelay: "160ms" }}>
      <div className="mb-2.5 flex flex-wrap items-baseline gap-x-3 gap-y-1">
        <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-(--ink)">{title}</h2>
        {subtitle ? <span className="text-[12.5px] text-(--ink-soft)">{subtitle}</span> : null}
      </div>
      {children}
    </section>
  );
}

/** "All orders" style link for a card header. */
export function MoreLink({ label, onClick }: { label: string; onClick: () => void }) {
  return (
    <button
      type="button"
      onClick={onClick}
      className="inline-flex items-center gap-1 text-[12.5px] font-semibold text-(--accent-ink) transition-colors hover:text-(--accent)"
    >
      {label}
      <Icon name="arrow-right" size={13} />
    </button>
  );
}

/** How a fact's category reads to the shopper. */
const CATEGORY_LABELS: Record<string, string> = { preference: "Preference", constraint: "Rule", context: "About you" };

function FactRow({
  fact,
  isNew,
  onEdit,
  onForget,
}: {
  fact: MemoryFact;
  isNew: boolean;
  onEdit: (key: string, value: string) => Promise<boolean>;
  onForget: (key: string) => Promise<void>;
}) {
  const t = useT();
  const [draft, setDraft] = useState<string | null>(null);
  const [failed, setFailed] = useState(false);
  const [busy, setBusy] = useState(false);
  const save = async () => {
    if (draft === null || !draft.trim() || busy) return;
    setBusy(true);
    const saved = await onEdit(fact.key, draft.trim());
    setBusy(false);
    setFailed(!saved);
    if (saved) setDraft(null);
  };
  return (
    <li className="border-t border-(--line) py-3 first:border-t-0">
      {draft === null ? (
        <div className="flex items-start gap-3">
          <p className="min-w-0 flex-1 text-[14px] leading-snug text-(--ink)">{fact.value}</p>
          <div className="flex shrink-0 gap-3 pt-px text-[12.5px] font-semibold">
            <button type="button" onClick={() => setDraft(fact.value)} className="text-(--ink-2) hover:text-(--ink)">
              {t("Edit")}
            </button>
            <button
              type="button"
              disabled={busy}
              onClick={async () => {
                setBusy(true);
                await onForget(fact.key);
                setBusy(false);
              }}
              className="font-medium text-(--danger) hover:underline disabled:opacity-50"
            >
              {t("Forget")}
            </button>
          </div>
        </div>
      ) : (
        <div>
          <textarea
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter" && !event.shiftKey && !event.nativeEvent.isComposing) {
                event.preventDefault();
                void save();
              }
              if (event.key === "Escape") {
                event.stopPropagation();
                setDraft(null);
              }
            }}
            rows={2}
            maxLength={200}
            aria-label={t("Correct this")}
            autoFocus
            className="w-full resize-none rounded-[10px] border border-(--accent) bg-(--card) px-3 py-2 text-[14px] leading-snug text-(--ink) shadow-[0_0_0_3px_var(--accent-soft)] outline-none"
          />
          {failed ? <p className="mt-1 text-[12px] text-(--danger)">{t("That could not be saved. Keep it to a preference or a standing rule.")}</p> : null}
          <div className="mt-2 flex gap-2">
            <Button variant="primary" size="sm" onClick={() => void save()} disabled={busy || !draft.trim()}>
              {t("Save")}
            </Button>
            <Button size="sm" onClick={() => setDraft(null)}>
              {t("Cancel")}
            </Button>
          </div>
        </div>
      )}
      <div className="mt-1.5 flex items-center gap-2 text-[11.5px] text-(--ink-soft)">
        {isNew ? <Pill tone="accent">{t("New this session")}</Pill> : <Pill>{t(CATEGORY_LABELS[fact.category] ?? fact.category)}</Pill>}
        {fact.updated_at ? <span>{t("Saved {date}", { date: formatDayMonth(fact.updated_at) })}</span> : null}
      </div>
    </li>
  );
}

export interface Profile {
  id: string;
  name: string;
}

/**
 * The signed-in shopper's sheet: who they are, the profile switch when the vertical has more
 * than one, and every fact the assistant has saved, each with Edit and Forget.
 */
export function AccountSheet({
  name,
  detail,
  api,
  profiles = [],
  profileId,
  onSwitchProfile,
  onClose,
}: {
  name: string;
  detail?: string;
  api: AgentApi;
  profiles?: Profile[];
  profileId?: string;
  onSwitchProfile?: (id: string) => void;
  onClose: () => void;
}) {
  const t = useT();
  const { chat, assistantName } = useStoreFrame();
  const facts = chat?.memory ?? [];
  const others = profiles.filter((profile) => profile.id !== profileId);
  const onEdit = async (key: string, value: string) => {
    const fact = await api.editMemoryFact(key, value);
    if (fact) chat?.reloadMemory(key);
    return fact !== null;
  };
  const onForget = async (key: string) => {
    if (await api.forgetMemoryFact(key)) chat?.reloadMemory(key);
  };
  return (
    <Sheet title={name} detail={detail} onClose={onClose}>
      {others.length && onSwitchProfile ? (
        <div className="flex flex-wrap items-center gap-2 text-[13px] text-(--ink-2)">
          <span>{t("Signed in as {name}.", { name })}</span>
          {others.map((profile) => (
            <Button key={profile.id} size="sm" icon="user" onClick={() => onSwitchProfile(profile.id)}>
              {t("Switch to {name}", { name: profile.name })}
            </Button>
          ))}
        </div>
      ) : null}
      <section>
        <h3 className="flex items-baseline gap-2 text-[15px] font-semibold text-(--ink)">
          {t("What {name} knows", { name: assistantName })}
          <span className="ml-auto text-[12px] font-normal tabular-nums text-(--ink-soft)">{t("{n} saved", { n: facts.length })}</span>
        </h3>
        <p className="mt-1 text-[13px] leading-snug text-(--ink-soft)">
          {t("{name} uses these when it recommends something. Edit or forget any line; a forgotten line is deleted.", { name: assistantName })}
        </p>
        {facts.length ? (
          <ul className="mt-2">
            {facts.map((fact) => (
              <FactRow key={fact.key} fact={fact} isNew={chat?.newMemoryKeys.has(fact.key) ?? false} onEdit={onEdit} onForget={onForget} />
            ))}
          </ul>
        ) : (
          <p className="mt-4 text-[13.5px] text-(--ink-2)">{t("Nothing saved yet.")}</p>
        )}
      </section>
      <p className="mt-auto border-t border-(--line) pt-3 text-[12px] leading-relaxed text-(--ink-soft)">
        {t("Only preferences and standing rules are kept. Card, account, phone, and email details are refused.")}
      </p>
    </Sheet>
  );
}
