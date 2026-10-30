// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** One entry per shopping presentation tool. */

import { type GenerativeBlockProps, UnknownBlock } from "web-shared";
import type {
  CheckoutPayload,
  ComparisonPayload,
  GuidePayload,
  OrderStatusPayload,
  PlanPayload,
  Product,
  ProductsPayload,
} from "@/lib/types";
import CheckoutSummary from "./CheckoutSummary";
import ComparisonGrid from "./ComparisonGrid";
import GuideCard from "./GuideCard";
import OrderStatusCard from "./OrderStatusCard";
import PlanChecklist from "./PlanChecklist";
import ProductCarousel from "./ProductCarousel";

export default function GenerativeBlock({
  block,
  status,
  onAdd,
}: GenerativeBlockProps & {
  onAdd?: (product: Product) => boolean | void | Promise<boolean | void>;
}) {
  const partial = status !== "final";
  switch (block.component) {
    case "products":
      return <ProductCarousel payload={block.payload as ProductsPayload} onAdd={onAdd} partial={partial} />;
    case "comparison":
      return <ComparisonGrid payload={block.payload as ComparisonPayload} partial={partial} />;
    case "plan":
      return <PlanChecklist payload={block.payload as PlanPayload} onAdd={onAdd} partial={partial} />;
    case "guide":
      return <GuideCard payload={block.payload as GuidePayload} />;
    case "order_status":
      if (partial) return null;
      return <OrderStatusCard payload={block.payload as OrderStatusPayload} />;
    case "checkout":
      if (partial) return null;
      return <CheckoutSummary payload={block.payload as CheckoutPayload} />;
    default:
      return partial ? null : <UnknownBlock component={block.component} />;
  }
}
