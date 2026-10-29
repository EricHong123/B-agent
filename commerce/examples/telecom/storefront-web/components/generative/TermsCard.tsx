// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** Renders present_guide. */

import { evidenceLabel, useT } from "web-shared";
import PlanTile from "@/components/PlanTile";
import { formatPriceWithUnit } from "@/lib/format";
import type { GuidePayload } from "@/lib/types";
import { Frame } from "./shared";

export default function TermsCard({ payload }: { payload: GuidePayload }) {
  const t = useT();
  return (
    <Frame component="guide" label={payload.title}>
      <div className="space-y-3">
        {(payload.sections ?? []).map((section, index) => (
          <div
            key={index}
            className={`am-reveal-item ${index > 0 ? "am-rule pt-3" : ""}`}
            style={{ animationDelay: `${index * 70}ms` }}
          >
            <h3 className="am-meta !text-(--ink)">{section.heading}</h3>
            <p className="mt-1 text-[15px] leading-relaxed text-(--ink)">{section.body}</p>
          </div>
        ))}
      </div>

      {payload.related_products?.length ? (
        <div className="am-rule mt-4 space-y-2 pt-3">
          {payload.related_products.map((product) => (
            <PlanTile
              key={product.product_id}
              product={product}
              note={product.product_id}
              trailing={
                <span className="am-mono shrink-0 text-[13px] font-semibold text-(--ink)">
                  {formatPriceWithUnit(product)}
                </span>
              }
            />
          ))}
        </div>
      ) : null}

      {payload.sources?.length ? (
        <div className="am-rule mt-4 flex flex-wrap items-center gap-1.5 pt-2.5">
          <span className="am-meta">{t("Sources")}</span>
          {payload.sources.map((source) => (
            <span key={source} className="am-tag">
              {source}
            </span>
          ))}
        </div>
      ) : null}
      {payload.evidence?.length ? (
        <div className="am-rule mt-2 flex flex-wrap items-center gap-1.5 pt-2">
          <span className="am-meta">{t("Terms in force")}</span>
          {payload.evidence.map((e) => (
            <span key={e.policy_id} className="am-tag">
              {evidenceLabel(e, t)}
            </span>
          ))}
        </div>
      ) : null}
    </Frame>
  );
}
