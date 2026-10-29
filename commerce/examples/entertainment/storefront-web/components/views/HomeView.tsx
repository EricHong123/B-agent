// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { formatMoney, formatWeekday, Greeting, HomeSection, MoreLink, Panel, type Starter, Starters, useCatalogIndex, useStoreFrame, useT } from "web-shared";
import { fetchProducts } from "@/lib/api";
import { dateBlock } from "@/lib/format";
import { Rich, tPlural } from "@/lib/i18n-helpers";
import { useLive } from "@/lib/live";
import type { Product } from "@/lib/types";
import { EMPTY_WALLET, shows, ticketAsk } from "@/lib/wallet";
import { DateSquare } from "../generative/shared";

const STARTERS: Starter[] = [
  { icon: "ticket", prompt: "Two seated tickets for The Headliner on Friday" },
  { icon: "clock", prompt: "The Synth-Pop Act says sold out. What are my options?" },
  { icon: "tag", prompt: "What's included in the Lower Bowl price?" },
  { icon: "calendar", prompt: "What's on at ACME Amphitheater this summer?" },
];

interface EventTile {
  name: string;
  date: string | undefined;
  venue: string | undefined;
  from: number;
  soldOut: boolean;
}

/** One tile per show (event and night), cheapest all-in tier as the "from" price, soonest first. */
function events(catalog: Record<string, Product>): EventTile[] {
  const byEvent = new Map<string, EventTile>();
  for (const product of Object.values(catalog)) {
    const attrs = product.attributes ?? {};
    if (product.category !== "tickets" || !attrs.event_name) continue;
    const key = `${attrs.event_name}|${attrs.event_date}`;
    const tile = byEvent.get(key) ?? { name: attrs.event_name, date: attrs.event_date, venue: attrs.venue, from: Infinity, soldOut: true };
    tile.from = Math.min(tile.from, product.price);
    tile.soldOut = tile.soldOut && product.in_stock === false;
    byEvent.set(key, tile);
  }
  return [...byEvent.values()].sort((a, b) => (a.date ?? "").localeCompare(b.date ?? "")).slice(0, 4);
}

function Brief() {
  const t = useT();
  const { tickets, holds, waitlist, holdsLoaded } = useLive();
  const held = holds.reduce((sum, hold) => sum + hold.quantity, 0);
  const showCount = shows(tickets).length;
  if (!holdsLoaded || (!tickets.length && !held && !waitlist.length)) {
    return <>{t("Every price here is all-in. Ask what's on, or hold seats while you decide.")}</>;
  }
  return (
    <>
      {tickets.length
        ? `${t("{tickets} in your wallet for {shows}.", {
            tickets: tPlural(t, tickets.length, "{n} ticket", "{n} tickets"),
            shows: tPlural(t, showCount, "{n} show", "{n} shows"),
          })} `
        : ""}
      {held ? (
        <>
          <span className="font-semibold text-(--warn)">
            {t("{seats} held and counting down.", { seats: tPlural(t, held, "{n} seat", "{n} seats") })}
          </span>{" "}
        </>
      ) : null}
      {waitlist.length
        ? `${t("You're #{position} on {lists}.", {
            position: Math.min(...waitlist.map((entry) => entry.position)),
            lists: tPlural(t, waitlist.length, "a waitlist", "{n} waitlists"),
          })} `
        : ""}
      {t("Ask about any of it, or find the next night out.")}
    </>
  );
}

export default function HomeView({ fanName, onSeeTickets }: { fanName: string; onSeeTickets: () => void }) {
  const t = useT();
  const { ask } = useStoreFrame();
  const { tickets } = useLive();
  const catalog = useCatalogIndex(fetchProducts);
  const onSale = events(catalog);
  const wallet = shows(tickets).slice(0, 2);
  return (
    <div className="flex flex-col gap-4">
      <Greeting
        eyebrow={
          <span className="at-stub-caption">
            <b>●</b> {t("Box office open · {name}", { name: fanName })}
          </span>
        }
        title={
          <h1 className="at-display text-[clamp(30px,3.8vw,44px)] uppercase leading-[0.98] text-(--ink)">
            {t("The house lights are down.")}
            <br />
            <span className="text-(--accent)">{t("The fees are not hidden.")}</span>
          </h1>
        }
      >
        <Brief />
      </Greeting>
      <Starters items={STARTERS.map((starter) => ({ ...starter, prompt: t(starter.prompt) }))} />
      <Panel title={t("Your tickets")} subtitle={tickets.length ? tPlural(t, tickets.length, "{n} ticket", "{n} tickets") : undefined} action={<MoreLink label={t("All tickets")} onClick={onSeeTickets} />}>
        {wallet.length ? (
          <ul className="px-[18px] pb-2">
            {wallet.map(({ ticket, passes }) => {
              const date = dateBlock(ticket.date);
              const pending = passes.some((pass) => pass.status === "transfer_pending");
              return (
                <li key={`${ticket.event}-${ticket.date}`} className="flex items-center gap-3 border-t border-(--line) py-2.5 first:border-t-0">
                  {date ? <DateSquare {...date} /> : null}
                  <button type="button" onClick={() => ask(ticketAsk(ticket, t))} className="min-w-0 flex-1 text-left">
                    <span className="at-display block truncate text-[16px] uppercase leading-tight text-(--ink)">{ticket.event}</span>
                    <span className="block truncate text-[12px] text-(--ink-soft)">
                      {[ticket.venue, `${ticket.tier ?? ticket.seat} × ${passes.length}`].filter(Boolean).join(" · ")}
                    </span>
                  </button>
                  <span className={`at-pill ${pending ? "at-pill--scarce" : "at-pill--calm"}`}>{pending ? t("Transfer pending") : t("Issued")}</span>
                </li>
              );
            })}
          </ul>
        ) : (
          <p className="px-[18px] pb-4 text-[13.5px] text-(--ink-soft)">{t(EMPTY_WALLET)}</p>
        )}
      </Panel>
      {onSale.length ? (
        <HomeSection title={t("On sale")} subtitle={t("Open one to see what is left")}>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {onSale.map((event) => {
              const date = dateBlock(event.date);
              return (
                <button
                  key={`${event.name}-${event.date}`}
                  type="button"
                  onClick={() =>
                    ask(
                      event.date
                        ? t("What's still available for {name} on {date}?", { name: event.name, date: formatWeekday(event.date) })
                        : t("What's still available for {name}?", { name: event.name }),
                    )
                  }
                  className="at-card flex flex-col gap-2 p-3 text-left transition-colors hover:border-(--accent)"
                >
                  <div className="flex items-start gap-2.5">
                    {date ? <DateSquare {...date} /> : null}
                    <span className={`at-pill ml-auto ${event.soldOut ? "at-pill--out" : "at-pill--calm"}`}>{event.soldOut ? t("Sold out") : t("On sale")}</span>
                  </div>
                  <span className="at-display line-clamp-2 min-h-[34px] text-[16px] uppercase leading-[1.05] text-(--ink)">{event.name}</span>
                  <span className="truncate text-[11.5px] text-(--ink-soft)">{event.venue}</span>
                  <span className="at-mono text-[13px] font-semibold text-(--ink)">
                    <Rich
                      text="from {price} {suffix}"
                      vars={{ price: formatMoney(event.from), suffix: <span className="at-eyebrow font-normal">{t("all-in")}</span> }}
                    />
                  </span>
                </button>
              );
            })}
          </div>
        </HomeSection>
      ) : null}
    </div>
  );
}
