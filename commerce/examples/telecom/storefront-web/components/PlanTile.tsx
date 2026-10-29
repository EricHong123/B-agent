// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import type { ReactNode } from "react";
import { plateGlyph, plateTint } from "@/lib/format";
import type { Product } from "@/lib/types";

export default function PlanTile({
  product,
  note,
  trailing,
}: {
  product: Product;
  note?: string;
  trailing?: ReactNode;
}) {
  return (
    <div className="flex items-center gap-3">
      <div
        className="am-plate flex h-11 w-14 shrink-0 items-center justify-center"
        style={{ backgroundImage: undefined }}
      >
        <div className="absolute inset-0" style={{ background: plateTint(product) }} aria-hidden />
        <span className="am-plate-glyph !text-[15px]" style={{ position: "relative", transform: "none", left: "auto", top: "auto" }}>
          {plateGlyph(product)}
        </span>
      </div>
      <div className="min-w-0 flex-1">
        <p className="truncate text-[14px] font-semibold leading-tight text-(--ink)" title={product.title}>
          {product.title}
        </p>
        {note ? <p className="am-mono mt-0.5 text-[11.5px] text-(--ink-soft)">{note}</p> : null}
      </div>
      {trailing}
    </div>
  );
}
