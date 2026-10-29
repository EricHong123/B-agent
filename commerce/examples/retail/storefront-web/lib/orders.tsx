// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { type Order, ORDER_NOUNS, useCatalogIndex } from "web-shared";
import { ProductImage } from "@/components/ProductTile";
import { fetchProducts } from "./api";

export const NOUNS = ORDER_NOUNS;

/** The first line's photo, or its glyph tile when the catalog has no photo for it. */
export function OrderThumb({ order }: { order: Order }) {
  const catalog = useCatalogIndex(fetchProducts);
  const line = order.items[0];
  const product = catalog[line?.product_id ?? ""] ?? { product_id: line?.product_id ?? order.order_id, title: line?.title ?? "", price: 0 };
  return <ProductImage product={product} className="h-[42px] w-[42px] shrink-0 rounded-[9px] !text-xl" />;
}
