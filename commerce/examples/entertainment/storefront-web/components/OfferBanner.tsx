// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useState } from "react";
import { formatMoney, useCatalogIndex, useT } from "web-shared";
import { fetchProducts } from "@/lib/api";
import { countdownTone, formatCountdown } from "@/lib/format";
import { useCountdown, useLive, type TimedOffer } from "@/lib/live";
import { tPlural } from "@/lib/i18n-helpers";
import type { Product } from "@/lib/types";
import { CountdownArc } from "./generative/shared";

/** Exported for the showcase. */
export function OfferBannerInner({
  offer,
  product,
  onClaim,
}: {
  offer: TimedOffer;
  product?: Product;
  onClaim: () => void;
}) {
  const t = useT();
  const { offerWindowMinutes } = useLive();
  const seconds = useCountdown(offer.deadline);
  const attrs = product?.attributes ?? {};
  return (
    <div className="at-slide-down border-b border-(--ok)/40 bg-(--ok-soft) px-5 py-2.5">
      <div className="mx-auto flex max-w-3xl flex-wrap items-center gap-x-4 gap-y-1.5">
        <p className="min-w-0 flex-1 text-[13px] leading-snug text-(--ink)">
          <b className="text-(--ok)">{t("Your turn:")}</b>{" "}
          {tPlural(t, offer.quantity, "{n} returned ticket", "{n} returned tickets")}
          {attrs.event_name ? ` · ${attrs.event_name}` : ""}
          {attrs.tier ? ` · ${attrs.tier}` : ""}
          {product ? (
            <span className="text-(--ink-soft)">
              {" "}
              {t("at the original {price} all-in", { price: formatMoney(product.price) })}
            </span>
          ) : null}
        </p>
        <span className="at-mono flex shrink-0 items-center gap-1.5 text-[12px] text-(--ink-soft)">
          <CountdownArc
            fraction={(seconds ?? 0) / (offerWindowMinutes * 60)}
            tone={countdownTone(seconds)}
            size={14}
            strokeWidth={3.5}
          />
          {t("closes")}{" "}
          <b className="text-[13px]" style={{ color: countdownTone(seconds) }}>
            {formatCountdown(seconds ?? 0)}
          </b>
        </span>
        <button type="button" onClick={onClaim} className="btn-primary shrink-0 !py-1.5 !text-[11px]">
          {t("Claim seats")}
        </button>
      </div>
    </div>
  );
}

/** Shows the soonest-closing offer. */
export default function OfferBanner() {
  const { offers, claim, offerWindowMinutes } = useLive();
  const catalog = useCatalogIndex(fetchProducts);
  const [busy, setBusy] = useState(false);
  if (!offers.length) return null;
  const soonest = offers.reduce((a, b) => (a.deadline <= b.deadline ? a : b));
  return (
    <OfferBannerInner
      offer={soonest}
      product={catalog[soonest.product_id]}
      onClaim={() => {
        if (busy) return;
        setBusy(true);
        void claim(soonest.offer_id).finally(() => setBusy(false));
      }}
    />
  );
}
