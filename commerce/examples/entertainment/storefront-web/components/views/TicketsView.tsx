// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { AskButton, formatDate, Notice, PageHeader, Panel, StorePage, useCatalogIndex, useStoreFrame, useT } from "web-shared";
import { fetchProducts } from "@/lib/api";
import { Rich, tPlural } from "@/lib/i18n-helpers";
import { useLive } from "@/lib/live";
import type { Product, WaitlistEntry } from "@/lib/types";
import { EMPTY_WALLET, shows, ticketAsk } from "@/lib/wallet";
import WalletPass from "../WalletPass";

/** One waitlist entry with its position ring. */
function WaitlistRow({ entry, product }: { entry: WaitlistEntry; product?: Product }) {
  const t = useT();
  const attrs = product?.attributes ?? {};
  const progress = 1 / Math.max(1, entry.position);
  return (
    <div className="flex items-center gap-3 rounded-(--radius) border border-(--line) bg-(--well)/60 p-3">
      <svg viewBox="0 0 36 36" className="h-9 w-9 shrink-0 -rotate-90" aria-hidden>
        <circle cx="18" cy="18" r="15" fill="none" stroke="var(--line)" strokeWidth="3" />
        <circle
          cx="18"
          cy="18"
          r="15"
          fill="none"
          stroke="var(--accent)"
          strokeWidth="3"
          strokeLinecap="round"
          strokeDasharray={`${Math.max(6, progress * 94.2)} 94.2`}
        />
      </svg>
      <div className="min-w-0">
        <p className="text-[13px] font-semibold text-(--ink)">
          <Rich
            text="You're {position} in line"
            vars={{ position: <span className="at-mono text-(--accent)">#{entry.position}</span> }}
          />
          <span className="at-mono ml-1.5 text-[11px] font-normal text-(--ink-soft)">× {entry.quantity}</span>
        </p>
        <p className="truncate text-[11.5px] text-(--ink-soft)">
          {attrs.event_name ?? entry.product_id}
          {attrs.tier ? ` · ${attrs.tier}` : ""}
        </p>
        <p className="text-[11px] text-(--ink-soft)/80">{t("Moves up on its own. When seats come back to you, a claim window opens at the top of the page.")}</p>
      </div>
    </div>
  );
}

export default function TicketsView() {
  const t = useT();
  const { ask } = useStoreFrame();
  const { tickets, waitlist, refreshTickets } = useLive();
  const catalog = useCatalogIndex(fetchProducts);
  const pending = tickets.filter((ticket) => ticket.status === "transfer_pending").length;
  const events = new Set(tickets.map((ticket) => ticket.event)).size;
  const subtitle = tickets.length
    ? pending
      ? t("{tickets} across {shows}, {transfers} pending. Ask ACME Assistant about a transfer, resale, or refund.", {
          tickets: tPlural(t, tickets.length, "{n} ticket", "{n} tickets"),
          shows: tPlural(t, events, "{n} show", "{n} shows"),
          transfers: tPlural(t, pending, "{n} transfer", "{n} transfers"),
        })
      : t("{tickets} across {shows}. Ask ACME Assistant about a transfer, resale, or refund.", {
          tickets: tPlural(t, tickets.length, "{n} ticket", "{n} tickets"),
          shows: tPlural(t, events, "{n} show", "{n} shows"),
        })
    : t(EMPTY_WALLET);
  return (
    <StorePage>
      <PageHeader title={t("Tickets")} subtitle={subtitle} />
      {waitlist.length ? (
        <Panel title={t("Waitlist")} subtitle={tPlural(t, waitlist.length, "{n} show", "{n} shows")}>
          <div className="space-y-2 px-[18px] pb-4">
            {waitlist.map((entry) => (
              <WaitlistRow key={`${entry.product_id}-${entry.position}`} entry={entry} product={catalog[entry.product_id]} />
            ))}
          </div>
        </Panel>
      ) : null}
      {tickets.length ? (
        shows(tickets).map(({ ticket: first, passes }) => (
          <Panel
            key={`${first.event}-${first.date}`}
            title={<span className="at-display text-[18px] uppercase">{first.event ?? t("Event")}</span>}
            subtitle={[first.date ? formatDate(first.date) : null, first.venue, tPlural(t, passes.length, "{n} ticket", "{n} tickets")].filter(Boolean).join(" · ")}
            action={<AskButton label={t("Ask about these tickets")} onClick={() => ask(ticketAsk(first, t))} />}
          >
            <div className="grid gap-3 px-[18px] pb-[18px] md:grid-cols-2">
              {passes.map((ticket) => (
                <WalletPass key={ticket.ticket_id} ticket={ticket} onRefresh={refreshTickets} />
              ))}
            </div>
          </Panel>
        ))
      ) : (
        <Notice>{t(EMPTY_WALLET)}</Notice>
      )}
    </StorePage>
  );
}
