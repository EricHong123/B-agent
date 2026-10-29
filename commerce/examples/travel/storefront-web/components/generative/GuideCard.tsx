// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { evidenceLabel, useT } from "web-shared";
import type { GuidePayload } from "@/lib/types";
import {
  BODY,
  CARD,
  DISPLAY,
  META,
  MiniProductCard,
  display,
} from "./shared";

function SectionBody({ body }: { body: string }) {
  if (!body) return null;
  return (
    <p className="mt-1" style={{ fontFamily: BODY, fontSize: 15, lineHeight: 1.6, color: "var(--ink)" }}>
      <span
        style={{
          fontFamily: DISPLAY,
          fontWeight: 600,
          fontSize: 24,
          lineHeight: 1,
          marginRight: 1,
          color: "var(--ink)",
        }}
      >
        {body.charAt(0)}
      </span>
      {body.slice(1)}
    </p>
  );
}

export default function GuideCard({ payload }: { payload: GuidePayload }) {
  const t = useT();
  const sections = payload.sections ?? [];
  return (
    <section className="al-reveal" style={{ ...CARD, padding: 24 }}>
      <div className="flex items-baseline gap-2">
        <span aria-hidden style={{ color: "var(--accent)", fontSize: 14 }}>
          ◈
        </span>
        <h3 style={display(22, 600)}>{payload.title}</h3>
      </div>

      <div className="mt-3 space-y-4">
        {sections.map((section, i) => (
          <div
            key={i}
            className="al-reveal-item"
            style={{ animationDelay: `${i * 70}ms` }}
          >
            <div style={META}>{section.heading}</div>
            <SectionBody body={section.body} />
          </div>
        ))}
      </div>

      {payload.related_products?.length ? (
        <div
          className="mt-4 flex flex-wrap gap-2.5 border-t pt-4"
          style={{ borderColor: "var(--line)" }}
        >
          {payload.related_products.map((product) => (
            <MiniProductCard key={product.product_id} product={product} />
          ))}
        </div>
      ) : null}

      {payload.sources?.length ? (
        <p className="mt-3 break-all" style={{ fontFamily: BODY, fontSize: 11, color: "var(--ink-soft)" }}>
          {t("Sources:")}{" "}
          {payload.sources.map((source, i) => (
            <span key={source}>
              {i ? " · " : ""}
              {/^https?:\/\//.test(source) ? (
                <a
                  href={source}
                  target="_blank"
                  rel="noreferrer"
                  className="underline decoration-[rgba(31,61,51,0.3)] underline-offset-2"
                >
                  {source}
                </a>
              ) : (
                source
              )}
            </span>
          ))}
        </p>
      ) : null}
      {payload.evidence?.length ? (
        <p className="mt-1 break-all" style={{ fontFamily: BODY, fontSize: 11, color: "var(--ink-soft)" }}>
          {t("Terms in force")}: {payload.evidence.map((e) => evidenceLabel(e, t)).join(" · ")}
        </p>
      ) : null}
    </section>
  );
}
