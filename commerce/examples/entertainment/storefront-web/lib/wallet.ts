// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** The wallet as the home and the Tickets view group and word it. */

import type { Translate } from "web-shared";
import type { WalletTicket } from "./types";

export const EMPTY_WALLET = "Nothing in the wallet yet. Held seats become tickets when you check out.";

/** "my The Headliner tickets" reads wrong; the tour suffix goes too. */
function eventName(ticket: WalletTicket): string | null {
  return ticket.event ? ticket.event.replace(/\s+[—-]\s+.*$/, "") : null;
}

/** The wallet grouped by show, in wallet order. */
export function shows(tickets: WalletTicket[]): { ticket: WalletTicket; passes: WalletTicket[] }[] {
  const byShow = new Map<string, { ticket: WalletTicket; passes: WalletTicket[] }>();
  for (const ticket of tickets) {
    const key = `${ticket.event}|${ticket.date}`;
    const show = byShow.get(key) ?? { ticket, passes: [] };
    show.passes.push(ticket);
    byShow.set(key, show);
  }
  return [...byShow.values()];
}

export function ticketAsk(ticket: WalletTicket, t: Translate): string {
  const event = eventName(ticket);
  return event
    ? t("What are my options for my {event} tickets: transfer, resale, or a refund?", { event })
    : t("What are my options for my upcoming tickets: transfer, resale, or a refund?");
}

export function transferAsk(ticket: WalletTicket, t: Translate): string {
  return ticket.event
    ? t("Help me transfer my {event} tickets to a friend.", { event: ticket.event })
    : t("Help me transfer my upcoming tickets to a friend.");
}

