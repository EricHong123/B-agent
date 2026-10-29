// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** Renders disclosure. */

import { useEffect, useState } from "react";
import { evidenceLabel, useT } from "web-shared";
import { useCountUp } from "@/lib/motion";
import type { DisclosurePayload } from "@/lib/types";
import { Frame } from "./shared";

const SPEED_VALUE = /^([\d.]+) (Mbps|ms)$/;

const FULL_SCALE = { Mbps: 1000, ms: 100 } as const;

const GAUGE_STAGGER_MS = 450;

/** Must match the label get_disclosure authors. */
const ALL_IN_LABEL = "Estimated all-in";

function SpeedRow({
  row,
  gaugeIndex,
  filled,
}: {
  row: { label: string; value: string; note?: string };
  gaugeIndex: number;
  filled: boolean;
}) {
  const match = SPEED_VALUE.exec(row.value);
  const value = Number(match?.[1] ?? 0);
  const unit = (match?.[2] ?? "Mbps") as keyof typeof FULL_SCALE;
  const isLatency = unit === "ms";
  const animated = useCountUp(value, isLatency ? 250 : 600);
  const pct = Math.min((value / FULL_SCALE[unit]) * 100, 100);
  return (
    <>
      <div className="flex items-baseline justify-between gap-4">
        <p className="shrink-0 text-[13px] font-bold leading-snug text-(--ink)">{row.label}</p>
        <p className="am-mono min-w-0 text-right text-[13px] font-semibold text-(--ink)">
          {Math.round(animated)} {unit}
        </p>
      </div>
      <div className="am-gauge" aria-hidden>
        <span
          style={{
            width: filled ? `${pct}%` : "0%",
            transitionDelay: `${gaugeIndex * GAUGE_STAGGER_MS}ms`,
            transitionDuration: isLatency ? "220ms" : undefined,
          }}
        />
      </div>
      {row.note ? (
        <p className="mt-0.5 text-[11px] leading-snug text-(--ink-soft)">{row.note}</p>
      ) : null}
    </>
  );
}

export default function FactsBox({ payload }: { payload: DisclosurePayload }) {
  const t = useT();
  // Gauges fill one frame after mount so the width transition runs.
  const [filled, setFilled] = useState(false);
  useEffect(() => {
    const frame = requestAnimationFrame(() => setFilled(true));
    return () => cancelAnimationFrame(frame);
  }, []);
  let gaugeIndex = -1;

  return (
    <Frame component="disclosure" label={t("Service facts")}>
      <div className="mx-auto max-w-md border-x-2 border-(--ink) px-4 pb-3">
        <div className="am-rule-heavy pt-2">
          <h3 className="text-[22px] font-extrabold leading-tight tracking-tight text-(--ink)">
            {payload.title}
          </h3>
          <p className="am-mono mt-0.5 text-[11px] tracking-[0.08em] text-(--ink-soft)">
            {payload.product_id}
          </p>
        </div>

        <div className="am-rule-bold mt-2">
          {payload.rows.map((row, index) => {
            const isSpeed = SPEED_VALUE.test(row.value);
            if (isSpeed) gaugeIndex += 1;
            const isAllIn = row.label === ALL_IN_LABEL;
            return (
              <div
                key={`${row.label}-${index}`}
                className={`am-reveal-item py-2 ${
                  isAllIn ? "am-rule-heavy mt-1 pt-2.5" : index > 0 ? "am-rule" : ""
                }`}
                style={{ animationDelay: `${index * 50}ms` }}
              >
                {isSpeed ? (
                  <SpeedRow row={row} gaugeIndex={gaugeIndex} filled={filled} />
                ) : (
                  <>
                    <div className="flex items-baseline justify-between gap-4">
                      <p
                        className={`shrink-0 leading-snug text-(--ink) ${
                          isAllIn ? "text-[15px] font-extrabold" : "text-[13px] font-bold"
                        }`}
                      >
                        {row.label}
                      </p>
                      <p
                        className={`am-mono min-w-0 break-words text-right text-(--ink) ${
                          isAllIn ? "text-[17px] font-bold" : "text-[13px] font-semibold"
                        }`}
                      >
                        {row.value}
                      </p>
                    </div>
                    {row.note ? (
                      <p className="mt-0.5 text-[11px] leading-snug text-(--ink-soft)">
                        {row.note}
                      </p>
                    ) : null}
                  </>
                )}
              </div>
            );
          })}
        </div>

        {payload.footnotes?.length ? (
          <div className="am-rule-bold pt-2">
            {payload.footnotes.map((note, index) => (
              <p key={index} className="text-[11px] leading-snug text-(--ink-soft)">
                {note}
              </p>
            ))}
          </div>
        ) : null}

        {payload.sources?.length ? (
          <div className="am-rule mt-2 flex flex-wrap items-center gap-1.5 pt-2">
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
      </div>
    </Frame>
  );
}
