// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { evidenceLabel, useT } from "web-shared";
import type { GuidePayload } from "@/lib/types";
import { Stub } from "./shared";

export default function GuideCard({ payload }: { payload: GuidePayload }) {
  const t = useT();
  return (
    <Stub component="guide" label={payload.title}>
      <div className="space-y-3">
        {(payload.sections ?? []).map((section, index) => (
          <section key={index} className="at-reveal-item" style={{ animationDelay: `${index * 50}ms` }}>
            <h4 className="text-[16px] font-bold text-(--ink)">{section.heading}</h4>
            <p className="mt-1 text-[15px] leading-relaxed text-(--ink)">
              {section.body}
            </p>
          </section>
        ))}
      </div>
      {payload.sources?.length ? (
        <div className="mt-3 flex flex-wrap items-center gap-1.5 border-t border-(--line) pt-2">
          <span className="at-eyebrow">{t("Sources")}</span>
          {payload.sources.map((source) => (
            <span key={source} className="at-pill">
              {source}
            </span>
          ))}
        </div>
      ) : null}
      {payload.evidence?.length ? (
        <div className="mt-2 flex flex-wrap items-center gap-1.5">
          <span className="at-eyebrow">{t("Terms in force")}</span>
          {payload.evidence.map((e) => (
            <span key={e.policy_id} className="at-pill">
              {evidenceLabel(e, t)}
            </span>
          ))}
        </div>
      ) : null}
    </Stub>
  );
}
