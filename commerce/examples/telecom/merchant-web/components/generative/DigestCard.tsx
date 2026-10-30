// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { CHANGE_STATUS, DigestList, DigestRow, formatMoney, formatNumber, GenCard, GenCardHeader, type IconName, type Tone, type Translate, useT } from "web-shared";
import { count } from "@/lib/copy";
import { INVENTORY_KINDS, LINE_CATEGORIES } from "@/lib/kinds";
import type { DigestEntry, DigestPayload } from "@/lib/types";

const KINDS: Record<DigestEntry["kind"], { icon: IconName; tone: Tone }> = {
  low_stock: INVENTORY_KINDS.low_stock,
  slow_mover: INVENTORY_KINDS.slow_mover,
  order_issue: { icon: "inbox", tone: "danger" },
  metric: { icon: "chart", tone: "ok" },
  pending_change: { icon: "edit", tone: "violet" },
  note: { icon: "message", tone: "muted" },
};

/** Pending changes get no chip; approval stays on the change card. */
function triagePrompt(item: DigestEntry, t: Translate): { label: string; prompt: string } | null {
  const ref = item.listing ? `${item.listing.title} (${item.listing.listing_id})` : item.ref_id;
  switch (item.kind) {
    case "low_stock":
      return ref ? { label: t("Draft restock"), prompt: t("Draft a restock plan for {ref}.", { ref }) } : null;
    case "slow_mover":
      return ref ? { label: t("Ask"), prompt: t("{ref} is moving slowly. What would you propose?", { ref }) } : null;
    case "order_issue":
      return {
        label: t("Draft reply"),
        prompt: item.ref_id
          ? t("Help me handle order {id}: {headline}", { id: item.ref_id, headline: item.headline })
          : t("Help me handle this order issue: {headline}", { headline: item.headline }),
      };
    case "metric":
      return { label: t("Ask why"), prompt: t("What's driving this: {headline}?", { headline: item.headline }) };
    default:
      return null;
  }
}

function context(item: DigestEntry, t: Translate) {
  if (item.listing) {
    const lines = LINE_CATEGORIES.has(item.listing.category ?? "");
    return (
      <span className="am-mono">
        {item.listing.listing_id} · {formatNumber(item.listing.stock)} {lines ? t("lines") : t("left")} · {lines ? t("{price}/mo", { price: formatMoney(item.listing.price) }) : formatMoney(item.listing.price)}
      </span>
    );
  }
  if (item.change) {
    return (
      <span className="am-mono">
        {item.change.change_id} · {t(CHANGE_STATUS[item.change.status].label).toLowerCase()}
      </span>
    );
  }
  return null;
}

export default function DigestCard({ payload, onPrefill }: { payload: DigestPayload; onPrefill?: (text: string) => void }) {
  const t = useT();
  const items = payload.items ?? [];
  return (
    <GenCard>
      <GenCardHeader title={payload.title ?? t("Needs attention")} aside={count(t, items.length, "{n} item", "{n} items")} />
      <DigestList>
        {items.map((item, index) => {
          const triage = onPrefill ? triagePrompt(item, t) : null;
          const style = KINDS[item.kind] ?? KINDS.note;
          const soldOut = item.kind === "low_stock" && item.listing?.stock === 0;
          return (
            <DigestRow
              key={`${item.ref_id ?? item.headline}-${index}`}
              icon={style.icon}
              tone={soldOut ? "danger" : style.tone}
              headline={item.headline}
              why={item.why_it_matters}
              context={context(item, t)}
              action={triage ? { label: triage.label, onClick: () => onPrefill?.(triage.prompt) } : null}
            />
          );
        })}
      </DigestList>
    </GenCard>
  );
}
