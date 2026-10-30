// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** Maps a `ui` event's component key to its card. */

import { type GenerativeBlockProps, UnknownBlock } from "web-shared";
import type {
  AccountContext,
  CheckoutPayload,
  ComparisonPayload,
  DisclosurePayload,
  GuidePayload,
  OrderStatusPayload,
  PlanMatrixPayload,
  PlanPayload,
  Product,
  ProductsPayload,
} from "@/lib/types";
import ActivationTicket from "./ActivationTicket";
import ComparisonTable from "./ComparisonTable";
import FactsBox from "./FactsBox";
import LineStatusCard from "./LineStatusCard";
import PlanCarousel from "./PlanCarousel";
import PlanMatrix from "./PlanMatrix";
import SetupChecklist from "./SetupChecklist";
import TermsCard from "./TermsCard";

/** PlanMatrix draws its skeleton for zero plans. */
const EMPTY_MATRIX: PlanMatrixPayload = { plans: [], rows: [], annotations: [] };

export default function GenerativeBlock({
  block,
  status,
  onAdd,
  account,
}: GenerativeBlockProps & {
  onAdd?: (product: Product) => boolean | void | Promise<boolean | void>;
  account?: AccountContext | null;
}) {
  const partial = status !== "final";
  switch (block.component) {
    case "products":
      return (
        <PlanCarousel
          payload={block.payload as ProductsPayload}
          onAdd={onAdd}
          partial={partial}
          account={account}
        />
      );
    case "comparison":
      return (
        <ComparisonTable
          payload={block.payload as ComparisonPayload}
          partial={partial}
        />
      );
    case "plan":
      return (
        <SetupChecklist
          payload={block.payload as PlanPayload}
          partial={partial}
        />
      );
    case "guide":
      return <TermsCard payload={block.payload as GuidePayload} />;
    case "order_status":
      if (partial) return null;
      return <LineStatusCard payload={block.payload as OrderStatusPayload} />;
    case "checkout":
      if (partial) return null;
      return (
        <ActivationTicket
          payload={block.payload as CheckoutPayload}
          account={account}
        />
      );
    case "disclosure":
      if (partial) return null;
      return <FactsBox payload={block.payload as DisclosurePayload} />;
    case "plan_matrix":
      return (
        <PlanMatrix
          payload={status === "pending" ? EMPTY_MATRIX : (block.payload as PlanMatrixPayload)}
        />
      );
    default:
      return partial ? null : <UnknownBlock component={block.component} />;
  }
}
