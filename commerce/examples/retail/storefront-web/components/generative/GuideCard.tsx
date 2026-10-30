// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { evidenceLabel, useT } from "web-shared";
import type { GuidePayload } from "@/lib/types";
import ProductTile from "../ProductTile";

export default function GuideCard({ payload }: { payload: GuidePayload }) {
  const t = useT();
  return (
    <section className="rounded-2xl border border-(--line) bg-(--card) p-4 shadow-(--shadow-sm)">
      <h3 className="text-[15px] font-semibold text-(--ink)">{payload.title}</h3>
      <div className="mt-2 space-y-3">
        {(payload.sections ?? []).map((section, index) => (
          <div key={index}>
            <div className="text-[13px] font-bold uppercase tracking-wide text-(--ink)">{section.heading}</div>
            <p className="mt-0.5 text-[15px] leading-relaxed text-(--ink)">{section.body}</p>
          </div>
        ))}
      </div>
      {payload.related_products?.length ? (
        <div className="panel-scroll mt-3 flex gap-3 overflow-x-auto border-t border-(--line) pt-3">
          {payload.related_products.map((product) => (
            <ProductTile key={product.product_id} product={product} compact />
          ))}
        </div>
      ) : null}
      {payload.sources?.length ? (
        <p className="mt-3 break-all text-[11px] text-(--ink-soft)/80">{t("Sources: {sources}", { sources: payload.sources.join(" · ") })}</p>
      ) : null}
      {payload.evidence?.length ? (
        <p className="mt-1 break-all text-[11px] text-(--ink-soft)/80">
          {t("Terms in force")}: {payload.evidence.map((e) => evidenceLabel(e, t)).join(" · ")}
        </p>
      ) : null}
    </section>
  );
}
