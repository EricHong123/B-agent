// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { evidenceLabel, useT } from "web-shared";
import type { DisclosurePayload } from "@/lib/types";
import { Stub } from "./shared";

/** ms between row reveals. */
const PRINT_STAGGER_MS = 90;

export default function FeeBreakdown({ payload }: { payload: DisclosurePayload }) {
  const t = useT();
  const rows = payload.rows ?? [];
  const totalRow = rows.find((row) => row.label === "All-in price");
  const detailRows = rows.filter((row) => row !== totalRow);
  const stampDelayMs = detailRows.length * PRINT_STAGGER_MS + 140;

  return (
    <Stub component="disclosure" label={t("Price & terms")}>
      <div className="at-tape mx-auto w-full max-w-[360px]">
        <div className="pt-1 text-center">
          <h3 className="text-[15px] font-bold leading-snug text-(--ink)">
            {payload.title}
          </h3>
          <p className="at-mono mt-1 text-[11px] tracking-[0.14em] text-(--ink-soft)">
            {payload.product_id}
          </p>
        </div>

        <div className="mt-3">
          {detailRows.map((row, index) => (
            <div
              key={`${row.label}-${index}`}
              className="at-reveal-item py-1.5"
              style={{ animationDelay: `${index * PRINT_STAGGER_MS}ms` }}
            >
              <div className="flex items-baseline gap-2">
                <p className="shrink-0 whitespace-nowrap text-[13px] font-semibold leading-snug text-(--ink)">
                  {row.label}
                </p>
                <span className="at-dots" aria-hidden />
                <p className="at-mono min-w-0 max-w-[60%] text-right text-[14px] font-semibold leading-snug text-(--ink)">
                  {row.value}
                </p>
              </div>
              {row.note ? (
                <p className="mt-0.5 text-[11px] leading-snug text-(--ink-soft)">
                  {row.note}
                </p>
              ) : null}
            </div>
          ))}
        </div>

        {totalRow ? (
          <div
            className="at-stamp mt-3 border-t-2 border-dashed border-(--rule)/60 pb-1 pt-3 text-center"
            style={{ animationDelay: `${stampDelayMs}ms` }}
          >
            <p className="at-display text-[34px] leading-none tracking-tight text-(--accent)">
              {totalRow.value}
            </p>
            <p className="at-eyebrow mt-1.5 !text-(--ink)">
              {t("All-in price, no fees added later")}
            </p>
            {totalRow.note ? (
              <p className="mt-1 text-[11px] leading-snug text-(--ink-soft)">
                {totalRow.note}
              </p>
            ) : null}
          </div>
        ) : null}

        {payload.footnotes?.length ? (
          <div className="at-rule mt-2 pt-2">
            {payload.footnotes.map((note, index) => (
              <p key={index} className="text-[11px] leading-snug text-(--ink-soft)">
                {note}
              </p>
            ))}
          </div>
        ) : null}

        {payload.sources?.length ? (
          <div className="mt-2 flex flex-wrap items-center gap-1.5 pb-1 pt-1">
            <span className="at-eyebrow">{t("Sources")}</span>
            {payload.sources.map((source) => (
              <span key={source} className="at-pill">
                {source}
              </span>
            ))}
          </div>
        ) : null}
        {payload.evidence?.length ? (
          <div className="mt-1 flex flex-wrap items-center gap-1.5 pb-1">
            <span className="at-eyebrow">{t("Terms in force")}</span>
            {payload.evidence.map((e) => (
              <span key={e.policy_id} className="at-pill">
                {evidenceLabel(e, t)}
              </span>
            ))}
          </div>
        ) : null}
      </div>
    </Stub>
  );
}
