// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** Maps a `ui` event's component key to a card. */

import { type GenerativeBlockProps, UnknownBlock } from "web-shared";
import type {
  CheckoutPayload,
  ComparisonPayload,
  GuidePayload,
  ItineraryPayload,
  OrderStatusPayload,
  PlanPayload,
  ProductsPayload,
} from "@/lib/types";
import BoardingPass from "./BoardingPass";
import BookingStatusCard from "./BookingStatusCard";
import ComparisonSpread from "./ComparisonSpread";
import GuideCard from "./GuideCard";
import ItineraryTimeline from "./ItineraryTimeline";
import PlanChecklist from "./PlanChecklist";
import TravelCarousel from "./TravelCarousel";

export default function GenerativeBlock({ block, status }: GenerativeBlockProps) {
  const partial = status !== "final";
  const payload = block.payload;
  switch (block.component) {
    case "products":
      return (
        <TravelCarousel
          payload={payload as ProductsPayload}
          partial={partial}
        />
      );
    case "comparison":
      return (
        <ComparisonSpread
          payload={payload as ComparisonPayload}
          partial={partial}
        />
      );
    case "plan":
      return (
        <PlanChecklist
          payload={payload as PlanPayload}
          partial={partial}
        />
      );
    case "guide":
      return <GuideCard payload={payload as GuidePayload} />;
    case "order_status":
      if (partial) return null;
      return <BookingStatusCard payload={payload as OrderStatusPayload} />;
    case "checkout":
      if (partial) return null;
      return <BoardingPass payload={payload as CheckoutPayload} />;
    case "itinerary":
      // The extension streams partial frames too, so days assemble one by one.
      return (
        <ItineraryTimeline
          payload={payload as ItineraryPayload}
          partial={partial}
        />
      );
    default:
      return partial ? null : <UnknownBlock component={block.component} />;
  }
}
