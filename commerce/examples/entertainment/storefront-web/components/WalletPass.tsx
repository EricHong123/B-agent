// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useEffect, useRef, useState } from "react";
import { useStoreFrame, useT } from "web-shared";
import { Rich } from "@/lib/i18n-helpers";
import { useCountdown } from "@/lib/live";
import type { WalletTicket } from "@/lib/types";
import { transferAsk } from "@/lib/wallet";
import { CountdownArc } from "./generative/shared";

function seatTriplet(seat: string): { sec: string; row: string; seat: string } {
  const match = /Section\s+(\S+?),\s*Row\s+(\S+?),\s*Seat\s+(\S+)/i.exec(seat);
  if (match) return { sec: match[1], row: match[2], seat: match[3] };
  return { sec: "GA", row: "—", seat: "—" };
}

/** The ring asks for a wallet re-read at zero; the code changes only when the server sends one. */
function EntryCode({
  code,
  rotatesS,
  onExpired,
}: {
  code: string;
  rotatesS: number;
  onExpired?: () => void;
}) {
  const t = useT();
  // A zero or negative window would divide by zero below.
  const windowS = Math.max(1, rotatesS);
  const [deadline, setDeadline] = useState<number>(() => Date.now() + windowS * 1000);
  const [refreshedBeat, setRefreshedBeat] = useState(false);
  const previousCode = useRef(code);
  const askedRef = useRef(false);
  const seconds = useCountdown(deadline);

  useEffect(() => {
    if (previousCode.current === code) return;
    previousCode.current = code;
    setDeadline(Date.now() + windowS * 1000);
    askedRef.current = false;
    setRefreshedBeat(true);
    const timer = window.setTimeout(() => setRefreshedBeat(false), 2600);
    return () => window.clearTimeout(timer);
  }, [code, windowS]);

  useEffect(() => {
    // Re-read the wallet once per window.
    if (seconds === 0 && !askedRef.current) {
      askedRef.current = true;
      onExpired?.();
    }
  }, [seconds, onExpired]);

  return (
    <div className="min-w-0">
      <div className="flex items-center gap-2">
        <CountdownArc
          fraction={(seconds ?? 0) / windowS}
          tone="var(--ink-soft)"
          size={16}
          strokeWidth={3.5}
        />
        <p
          key={code}
          className="at-code-in at-mono truncate text-[13px] font-semibold tracking-[0.14em] text-(--ink)"
        >
          {code}
        </p>
      </div>
      <p
        className={`text-[11px] ${
          refreshedBeat ? "font-semibold text-(--ok)" : "text-(--ink-soft)"
        }`}
      >
        {refreshedBeat ? t("New code. The old one won't scan.") : t("The entry code refreshes on its own, so a screenshot won't scan.")}
      </p>
    </div>
  );
}

/** One ticket as it sits in the wallet; grouped by show, so it carries seat and code, not the event. */
export default function WalletPass({ ticket, onRefresh }: { ticket: WalletTicket; onRefresh?: () => void }) {
  const t = useT();
  const { ask } = useStoreFrame();
  const triplet = seatTriplet(ticket.seat);
  const pending = ticket.status === "transfer_pending";
  // Briefly strike the code through when a mounted pass goes transfer_pending.
  const previousStatus = useRef(ticket.status);
  const [voiding, setVoiding] = useState(false);
  useEffect(() => {
    const was = previousStatus.current;
    previousStatus.current = ticket.status;
    if (was === "active" && ticket.status === "transfer_pending") {
      setVoiding(true);
      const timer = window.setTimeout(() => setVoiding(false), 1900);
      return () => window.clearTimeout(timer);
    }
  }, [ticket.status]);

  return (
    <div className="overflow-hidden rounded-(--radius) border border-(--line) bg-(--well)/60">
      <div className="flex items-center justify-between gap-2 px-3 pt-2.5">
        <p className="at-eyebrow">{ticket.tier ?? t("Ticket")}</p>
        {pending ? <span className="at-pill at-pill--scarce">{t("Transfer pending")}</span> : null}
      </div>
      <div className="mx-3 mt-1.5 grid grid-cols-3 gap-2">
        {(
          [
            ["Sec", triplet.sec],
            ["Row", triplet.row],
            ["Seat", triplet.seat],
          ] as const
        ).map(([label, value]) => (
          <div key={label}>
            <p className="at-eyebrow">{t(label)}</p>
            <p className="at-mono text-[20px] font-bold leading-tight text-(--ink)">{value}</p>
          </div>
        ))}
      </div>
      <div className="at-perf mx-3 mt-2.5 flex items-center justify-between gap-2 pb-2.5 pt-2">
        {pending ? (
          <div className="min-w-0">
            {voiding ? (
              <p className="at-dissolve at-mono truncate text-[13px] font-semibold tracking-[0.14em] text-(--ink) line-through decoration-(--danger)/70">
                {ticket.entry_code}
              </p>
            ) : (
              <p className="at-mono text-[13px] font-semibold tracking-[0.3em] text-(--ink-soft)">
                ··········
              </p>
            )}
            <p className="text-[11px] leading-snug">
              <span className="text-(--ink-soft)">
                <Rich
                  text="{voided} and reissued to {recipient}. The new code is on their phone; this one won't scan."
                  vars={{
                    voided: (
                      <span className="at-mono font-bold uppercase tracking-[0.1em] text-(--danger)">{t("Voided")}</span>
                    ),
                    recipient: ticket.transfer_recipient ?? t("the recipient"),
                  }}
                />
              </span>
            </p>
          </div>
        ) : (
          <EntryCode
            code={ticket.entry_code}
            rotatesS={ticket.entry_code_rotates_s}
            onExpired={onRefresh}
          />
        )}
        {pending ? null : (
          <button
            type="button"
            onClick={() => ask(transferAsk(ticket, t))}
            className="at-btn-ghost shrink-0 !px-2.5 !py-1 !text-[11px]"
          >
            {t("Transfer")}
          </button>
        )}
      </div>
    </div>
  );
}
