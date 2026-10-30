// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { CHANGE_STATUS, DigestList, DigestRow, formatMoney, formatNumber, GenCard, GenCardHeader, type IconName, plural, type Tone, type Translate, useT } from "web-shared";
import { INVENTORY_KINDS, inventoryPrompt } from "@/lib/kinds";
import type { DigestEntry, DigestPayload } from "@/lib/types";

const KINDS: Record<DigestEntry["kind"], { icon: IconName; tone: Tone }> = {
  low_stock: INVENTORY_KINDS.low_stock,
  slow_mover: INVENTORY_KINDS.slow_mover,
  order_issue: { icon: "calendar", tone: "danger" },
  metric: { icon: "chart", tone: "ok" },
  pending_change: { icon: "edit", tone: "violet" },
  note: { icon: "message", tone: "muted" },
};

/** Pending changes get no chip; approval stays on the change card. */
function triagePrompt(item: DigestEntry, t: Translate): { label: string; prompt: string } | null {
  const ref = item.listing ? `${item.listing.title} (${item.listing.listing_id})` : item.ref_id;
  switch (item.kind) {
    case "low_stock":
      return ref ? { label: t("Ask"), prompt: inventoryPrompt("low_stock", ref, t) } : null;
    case "slow_mover":
      return ref ? { label: t("Plan rates"), prompt: inventoryPrompt("slow_mover", ref, t) } : null;
    case "order_issue":
      return {
        label: t("Draft reply"),
        prompt: item.ref_id
          ? t("Help me handle booking {id}. {headline}.", { id: item.ref_id, headline: item.headline })
          : t("Help me handle this booking issue. {headline}.", { headline: item.headline }),
      };
    case "metric":
      return { label: t("Ask why"), prompt: t("What's driving this: {headline}?", { headline: item.headline }) };
    default:
      return null;
  }
}

function context(item: DigestEntry, t: Translate) {
  if (item.listing) {
    return (
      <span>
        {item.listing.listing_id} · {t("{count} available", { count: formatNumber(item.listing.stock) })} · {formatMoney(item.listing.price, "USD", { whole: true })}
      </span>
    );
  }
  if (item.change) {
    return (
      <span>
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
      <GenCardHeader title={payload.title ?? t("Needs attention")} aside={plural(items.length, "item", "items", t)} />
      <DigestList>
        {items.map((item, index) => {
          const triage = onPrefill ? triagePrompt(item, t) : null;
          const style = KINDS[item.kind] ?? KINDS.note;
          return (
            <DigestRow
              key={`${item.ref_id ?? item.headline}-${index}`}
              icon={style.icon}
              tone={style.tone}
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
