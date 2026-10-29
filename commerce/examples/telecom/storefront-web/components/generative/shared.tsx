// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import type { ReactNode } from "react";
import { useT } from "web-shared";

const FIG_NUMBERS: Record<string, string> = {
  plan_matrix: "01",
  disclosure: "02",
  products: "03",
  comparison: "04",
  plan: "05",
  guide: "06",
  checkout: "07",
  order_status: "08",
};

function FigCaption({ component, label }: { component: string; label: string }) {
  const t = useT();
  return (
    <p className="am-fig mb-2 select-none">
      {t("FIG {n}", { n: FIG_NUMBERS[component] ?? "00" })} <b>·</b> {label}
    </p>
  );
}

export function Frame({
  component,
  label,
  children,
  flush,
}: {
  component: string;
  label: string;
  children: ReactNode;
  flush?: boolean;
}) {
  return (
    <section className="am-reveal mt-1">
      <FigCaption component={component} label={label} />
      <div className={`am-card overflow-hidden ${flush ? "" : "p-4 sm:p-5"}`}>{children}</div>
    </section>
  );
}

export function Rating({ rating, count }: { rating?: number | null; count?: number | null }) {
  if (rating == null) return null;
  return (
    <span className="am-mono text-[11.5px] text-(--ink-soft)">
      {rating.toFixed(1)} <span className="text-(--warn)">★</span>
      {count ? ` (${count.toLocaleString("en-US")})` : ""}
    </span>
  );
}
