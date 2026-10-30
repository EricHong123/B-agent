// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { AskLink, BagPanel, CheckoutButton, formatMoney, TotalRow, useCatalogIndex, useT } from "web-shared";
import { fetchProducts } from "@/lib/api";
import { countdownTone, dateBlock, formatCountdown } from "@/lib/format";
import { tPlural } from "@/lib/i18n-helpers";
import { useCountdown, useLive, type TimedHold, type TimedOffer } from "@/lib/live";
import type { Product } from "@/lib/types";
import { CountdownArc, DateSquare } from "./generative/shared";

function HoldRow({
  hold,
  product,
  onRelease,
}: {
  hold: TimedHold;
  product?: Product;
  onRelease: () => void;
}) {
  const t = useT();
  const { holdMinutes } = useLive();
  const seconds = useCountdown(hold.deadline);
  const attrs = product?.attributes ?? {};
  const lineTotal = (product?.price ?? 0) * hold.quantity;
  return (
    <li className="py-3 first:pt-0">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <p className="truncate text-[14px] font-semibold text-(--ink)">
            {attrs.event_name ?? hold.product_id}
          </p>
          <p className="at-mono mt-0.5 text-[11px] text-(--ink-soft)">
            {attrs.tier ? `${attrs.tier} × ${hold.quantity}` : `× ${hold.quantity}`}
          </p>
        </div>
        <div className="shrink-0 text-right">
          <p className="at-mono text-[13px] font-semibold text-(--ink)">
            {formatMoney(lineTotal)}
          </p>
          <p
            className={`at-mono flex items-center justify-end gap-1.5 text-[13px] font-bold ${
              seconds != null && seconds <= 30 ? "at-urgent" : ""
            }`}
            style={{ color: countdownTone(seconds) }}
            title={t("Hold expires; the seats release to other buyers at 0:00")}
          >
            <CountdownArc
              fraction={(seconds ?? 0) / (holdMinutes * 60)}
              tone={countdownTone(seconds)}
              size={14}
              strokeWidth={3.5}
            />
            {formatCountdown(seconds ?? 0)}
          </p>
        </div>
      </div>
      <button
        type="button"
        onClick={onRelease}
        className="at-mono mt-1 text-[11px] text-(--ink-soft) underline-offset-2 hover:text-(--danger) hover:underline"
      >
        {t("Release now")}
      </button>
    </li>
  );
}

/** Shows the soonest-expiring hold. */
export function TonightStrip({
  product,
  quantity,
  total,
  deadline,
}: {
  product?: Product;
  quantity: number;
  total: number;
  deadline: number | null;
}) {
  const t = useT();
  const { holdMinutes } = useLive();
  const seconds = useCountdown(deadline);
  const attrs = product?.attributes ?? {};
  const date = dateBlock(attrs.event_date);
  return (
    <div className="flex items-center gap-3 rounded-(--radius) border border-(--accent)/40 bg-(--well)/70 p-3">
      {date ? <DateSquare {...date} /> : null}
      <div className="min-w-0 flex-1">
        <p className="at-display truncate text-[16px] uppercase leading-tight text-(--ink)">
          {attrs.event_name ?? product?.title ?? t("Tonight")}
        </p>
        <p className="truncate text-[11.5px] text-(--ink-soft)">
          {[attrs.venue, attrs.tier ? `${attrs.tier} × ${quantity}` : `× ${quantity}`]
            .filter(Boolean)
            .join(" · ")}
        </p>
        <p className="at-mono mt-0.5 text-[14px] font-bold text-(--ink)">
          {formatMoney(total)}
          <span className="at-eyebrow ml-1.5 font-normal">{t("all-in")}</span>
        </p>
      </div>
      <div className="shrink-0 text-right">
        <CountdownArc
          fraction={(seconds ?? 0) / (holdMinutes * 60)}
          tone={countdownTone(seconds)}
          size={30}
          strokeWidth={3}
          className="ml-auto"
        />
        <p
          className={`at-mono mt-0.5 text-[13px] font-bold ${
            seconds != null && seconds <= 30 ? "at-urgent" : ""
          }`}
          style={{ color: countdownTone(seconds) }}
        >
          {formatCountdown(seconds ?? 0)}
        </p>
      </div>
    </div>
  );
}

function OfferCard({
  offer,
  product,
  onClaim,
}: {
  offer: TimedOffer;
  product?: Product;
  onClaim: () => void;
}) {
  const t = useT();
  const seconds = useCountdown(offer.deadline);
  const attrs = product?.attributes ?? {};
  return (
    <div className="rounded-(--radius) border border-(--ok)/40 bg-(--ok-soft) p-3">
      <p className="at-eyebrow !text-(--ok)">{t("Return offer: your turn in line")}</p>
      <p className="mt-1 text-[13px] font-semibold leading-snug text-(--ink)">
        {tPlural(t, offer.quantity, "{n} ticket", "{n} tickets")} · {attrs.event_name ?? offer.product_id}
        {attrs.tier ? <span className="text-(--ink-soft)"> · {attrs.tier}</span> : null}
      </p>
      {product ? (
        <p className="mt-0.5 text-[11.5px] text-(--ink-soft)">
          {t("at the original {price} all-in", { price: formatMoney(product.price) })}
        </p>
      ) : null}
      <div className="mt-2 flex items-center justify-between gap-3">
        <span className="at-mono text-[12px] text-(--ink-soft)">
          {t("Claim window closes")}{" "}
          <b className={`text-[13px] ${seconds != null && seconds <= 60 ? "text-(--danger)" : "text-(--warn)"}`}>
            {formatCountdown(seconds ?? 0)}
          </b>
        </span>
        <button type="button" onClick={onClaim} className="btn-primary !py-1.5 !text-[11px]">
          {t("Claim seats")}
        </button>
      </div>
    </div>
  );
}

/** The held seats beside the conversation. Release and Claim act at once; checkout goes through the assistant. */
export default function NightPanel() {
  const t = useT();
  const { holds, offers, release, claim } = useLive();
  const catalog = useCatalogIndex(fetchProducts);
  const lineTotal = (hold: { product_id: string; quantity: number }) => (catalog[hold.product_id]?.price ?? 0) * hold.quantity;
  const total = holds.reduce((sum, hold) => sum + lineTotal(hold), 0);
  const heldTickets = holds.reduce((sum, hold) => sum + hold.quantity, 0);
  const soonest = holds.length ? holds.reduce((a, b) => (a.deadline <= b.deadline ? a : b)) : null;
  const later = holds.filter((hold) => hold !== soonest);

  return (
    <BagPanel
      title={t("Your night")}
      count={t("{n} held", { n: heldTickets })}
      isEmpty={holds.length === 0 && offers.length === 0}
      empty={
        <>
          {t("No seats held yet.")}
          <br />
          {t("Ask ACME Assistant to hold seats for 8 minutes while you decide.")}
        </>
      }
      footer={
        <>
          <TotalRow label={t("Held total, all-in")} value={formatMoney(total)} note={holds.length ? t("Nothing is charged until you check out.") : undefined} />
          <CheckoutButton staged={false} disabled={holds.length === 0} prompt={t("Check out my held seats.")} />
          {holds.length ? (
            <div className="mt-2.5 flex justify-center">
              <AskLink label={t("Ask about these seats")} prompt={t("Tell me about the seats I'm holding: the view, what's included, and the all-in price.")} />
            </div>
          ) : null}
        </>
      }
    >
      {soonest ? (
        <div className="mb-4">
          <TonightStrip product={catalog[soonest.product_id]} quantity={soonest.quantity} total={lineTotal(soonest)} deadline={soonest.deadline} />
          <button
            type="button"
            onClick={() => void release(soonest.hold_id)}
            className="at-mono mt-1.5 text-[11px] text-(--ink-soft) underline-offset-2 hover:text-(--danger) hover:underline"
          >
            {t("Release now")}
          </button>
        </div>
      ) : null}

      {/* Offers first: their claim windows are the shortest. */}
      {offers.length ? (
        <div className="mb-4 space-y-2">
          {offers.map((offer) => (
            <OfferCard key={offer.offer_id} offer={offer} product={catalog[offer.product_id]} onClaim={() => void claim(offer.offer_id)} />
          ))}
        </div>
      ) : null}

      {later.length ? (
        <>
          <p className="at-eyebrow mb-1">{t("Also held")}</p>
          <ul className="divide-y divide-(--line)">
            {later.map((hold) => (
              <HoldRow key={hold.hold_id} hold={hold} product={catalog[hold.product_id]} onRelease={() => void release(hold.hold_id)} />
            ))}
          </ul>
        </>
      ) : null}
    </BagPanel>
  );
}
