// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** The bag beside the conversation (cart, trip, order, held seats) and the pieces its lines use. */

import type { ReactNode } from "react";
import { plural } from "../format";
import { useT } from "../i18n";
import { Icon } from "../icons";
import { IconButton } from "../ui";
import { useStoreFrame } from "./frame";

/**
 * Header with the count, the lines, and a footer for totals and the primary action. The vertical
 * renders its own lines and footer; quantity and checkout go through the conversation as messages.
 */
export function BagPanel({
  title,
  count,
  empty,
  isEmpty,
  footer,
  children,
}: {
  title: string;
  /** "1 item", "2 bookings"; pops when it changes. */
  count: string;
  /** Shown in place of the lines while the bag is empty: the state, then what to ask. */
  empty: ReactNode;
  isEmpty: boolean;
  footer: ReactNode;
  children: ReactNode;
}) {
  const t = useT();
  const { closePanel } = useStoreFrame();
  return (
    <>
      <div className="flex items-center gap-2 border-b border-(--line) px-[18px] py-3.5">
        <h2 className="text-[15px] font-semibold tracking-[-0.01em] text-(--ink)">{title}</h2>
        <span
          key={count}
          data-cart-target
          className="ac-pop rounded-full bg-(--well) px-2 py-0.5 text-[12px] font-semibold tabular-nums text-(--ink-2)"
        >
          {count}
        </span>
        <IconButton icon="x" label={t("Close {title}", { title: title.toLowerCase() })} onClick={closePanel} className="ml-auto xl:hidden" />
      </div>
      <div className="panel-scroll min-h-0 flex-1 overflow-y-auto px-[18px] py-3.5">
        {isEmpty ? (
          <div className="mt-10 px-4 text-center text-[13.5px] leading-relaxed text-(--ink-soft)">{empty}</div>
        ) : (
          children
        )}
      </div>
      <div className="border-t border-(--line) px-[18px] pb-[18px] pt-3.5">{footer}</div>
    </>
  );
}

/** Subtotal row above the primary action. */
export function TotalRow({ label, value, note }: { label: string; value: string; note?: ReactNode }) {
  return (
    <div>
      <div className="flex items-baseline justify-between gap-3">
        <span className="text-[13.5px] text-(--ink-2)">{label}</span>
        <span className="text-[18px] font-bold tabular-nums tracking-[-0.01em] text-(--ink)">{value}</span>
      </div>
      {note ? <p className="mt-0.5 text-right text-[11.5px] text-(--ink-soft)">{note}</p> : null}
    </div>
  );
}

/** The hand-off under a panel's primary action or a card: sends one question. */
export function AskLink({ label, prompt }: { label: string; prompt: string }) {
  const { ask } = useStoreFrame();
  return (
    <button
      type="button"
      onClick={() => ask(prompt)}
      className="inline-flex items-center gap-1.5 text-[12.5px] font-semibold text-(--accent-ink) transition-colors hover:text-(--accent)"
    >
      <Icon name="spark" size={13} className="text-(--accent)" />
      {label}
    </button>
  );
}

/**
 * A line's quantity control. Each press is a message to the assistant, so it waits while a reply
 * streams; `unit` names what is counted when it is not the item itself ("night", "guest").
 */
export function Stepper({
  quantity,
  unit,
  itemTitle,
  onChange,
}: {
  quantity: number;
  unit?: string;
  itemTitle: string;
  /** Called with the new quantity; 0 means remove. */
  onChange: (quantity: number) => void;
}) {
  const t = useT();
  const busy = useStoreFrame().chat?.busy ?? false;
  return (
    <div className="flex items-center rounded-full border border-(--line-strong) bg-(--card)">
      <button
        type="button"
        disabled={busy}
        onClick={() => onChange(quantity - 1)}
        aria-label={unit ? t("Fewer {unit}s for {item}", { unit: t(unit), item: itemTitle }) : t("Decrease {item} quantity", { item: itemTitle })}
        className="px-2.5 py-0.5 text-sm text-(--ink-soft) hover:text-(--ink) disabled:opacity-40"
      >
        −
      </button>
      <span className="min-w-6 text-center text-[12.5px] font-semibold tabular-nums text-(--ink)">
        {unit ? plural(quantity, unit, undefined, t) : quantity}
      </span>
      <button
        type="button"
        disabled={busy}
        onClick={() => onChange(quantity + 1)}
        aria-label={unit ? t("More {unit}s for {item}", { unit: t(unit), item: itemTitle }) : t("Increase {item} quantity", { item: itemTitle })}
        className="px-2.5 py-0.5 text-sm text-(--ink-soft) hover:text-(--ink) disabled:opacity-40"
      >
        +
      </button>
    </div>
  );
}

export function RemoveLink({ itemTitle, onClick }: { itemTitle: string; onClick: () => void }) {
  const t = useT();
  const busy = useStoreFrame().chat?.busy ?? false;
  return (
    <button
      type="button"
      disabled={busy}
      onClick={onClick}
      aria-label={t("Remove {item}", { item: itemTitle })}
      className="text-[12px] text-(--ink-soft) underline-offset-2 hover:text-(--danger) hover:underline disabled:opacity-40"
    >
      {t("Remove")}
    </button>
  );
}

/** Once the assistant has staged a checkout, the primary action scrolls to that summary instead. */
export function CheckoutButton({ staged, disabled, prompt }: { staged: boolean; disabled: boolean; prompt: string }) {
  const t = useT();
  const { ask } = useStoreFrame();
  if (staged && !disabled) {
    return (
      <button
        type="button"
        onClick={() => {
          const cards = document.querySelectorAll("[data-checkout-card]");
          const card = cards[cards.length - 1];
          if (card) card.scrollIntoView({ behavior: "smooth", block: "center" });
          else ask(t("Show me the checkout summary again."));
        }}
        className="mt-3 w-full rounded-(--radius) border border-(--line-strong) bg-(--card) py-2.5 text-[14px] font-semibold text-(--ink) transition hover:border-(--accent)"
      >
        {t("View summary")}
      </button>
    );
  }
  return (
    <button type="button" onClick={() => ask(prompt)} disabled={disabled} className="btn-primary mt-3 w-full">
      {t("Check out")}
    </button>
  );
}
