// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** One entry per presentation tool; `pending` shows the bones until the event lands. */

import { type GenerativeBlockProps, UnknownBlock } from "web-shared";
import type {
  CheckoutPayload,
  ComparisonPayload,
  DisclosurePayload,
  GuidePayload,
  HoldPayload,
  OrderStatusPayload,
  PlanPayload,
  ProductsPayload,
  VenueMapPayload,
} from "@/lib/types";
import { ComponentBones } from "./Bones";
import CheckoutHold from "./CheckoutHold";
import EventCards from "./EventCards";
import FeeBreakdown from "./FeeBreakdown";
import GuideCard from "./GuideCard";
import OrderCard from "./OrderCard";
import PlanCard from "./PlanCard";
import TierComparison from "./TierComparison";
import VenueMap from "./VenueMap";

export default function GenerativeBlock({ block, status }: GenerativeBlockProps) {
  if (status === "pending") return <ComponentBones component={block.component} />;
  const partial = status !== "final";
  switch (block.component) {
    case "products":
      return (
        <EventCards
          payload={block.payload as ProductsPayload}
          partial={partial}
        />
      );
    case "comparison":
      return (
        <TierComparison
          payload={block.payload as ComparisonPayload}
          partial={partial}
        />
      );
    case "plan":
      return (
        <PlanCard
          payload={block.payload as PlanPayload}
          partial={partial}
        />
      );
    case "guide":
      return <GuideCard payload={block.payload as GuidePayload} />;
    case "order_status":
      if (partial) return null;
      return <OrderCard payload={block.payload as OrderStatusPayload} />;
    case "checkout":
      if (partial) return null;
      return <CheckoutHold payload={block.payload as CheckoutPayload} />;
    case "disclosure":
      if (partial) return null;
      return <FeeBreakdown payload={block.payload as DisclosurePayload} />;
    case "venue_map":
      // An extension card; it arrives as one final event.
      return <VenueMap payload={block.payload as VenueMapPayload} />;
    case "hold":
      // The checkout card without the purchase button.
      if (partial) return null;
      return <CheckoutHold payload={block.payload as HoldPayload} variant="hold" />;
    default:
      return partial ? null : <UnknownBlock component={block.component} />;
  }
}
