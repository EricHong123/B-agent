// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { destinationGradientCss } from "@/lib/format";

/** Stands in for product photos; the catalog ships none. */
export function PostcardWindow({
  city,
  title,
  className = "",
}: {
  city?: string;
  title: string;
  className?: string;
}) {
  const label = city ?? title.split(/\s+/)[0] ?? "";
  // Container-query units scale the name to the window; longer names get a smaller size.
  const fontSize = `${Math.max(14, Math.min(34, Math.round(190 / Math.max(label.length, 1))))}cqw`;
  return (
    <div
      className={`al-postcard ${className}`}
      style={{ backgroundImage: destinationGradientCss(city, title) }}
      aria-hidden
    >
      <span className="al-postcard-city" style={{ fontSize }}>
        {label}
      </span>
    </div>
  );
}
