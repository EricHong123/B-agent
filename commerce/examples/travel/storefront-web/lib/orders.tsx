// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

/** A trip is an order here: these are travel's words for the shared order pieces. */

import { useMemo } from "react";
import { isOpen, type Order, ORDER_NOUNS, type OrderNouns, useCatalogIndex, useT } from "web-shared";
import { PostcardWindow } from "@/components/PostcardWindow";
import { fetchProducts } from "./api";
import { productCity } from "./format";

/** The translated nouns for the current language; the shared order pieces read them as props. */
export function useNouns(): OrderNouns {
  const t = useT();
  return useMemo(
    () => ({
      ...ORDER_NOUNS,
      one: "trip",
      title: t("Trips"),
      cardTitle: t("Coming up"),
      noneOpen: t("No trips ahead"),
      openVerb: t("Starts"),
      closedWhen: (_order, date) => t("For {date}", { date }),
      statusLabels: {
        processing: t("Confirming"),
        shipped: t("Confirmed"),
        out_for_delivery: t("Confirmed"),
        delivered: t("Completed"),
        return_initiated: t("Refund requested"),
      },
      filters: [
        { id: "open", label: t("Upcoming"), match: isOpen },
        { id: "closed", label: t("Past"), match: (order) => !isOpen(order) },
      ],
      handoff(order) {
        const id = order.order_id;
        if (isOpen(order)) return { label: t("Ask"), prompt: t("What's the status of my trip {id}?", { id }) };
        if (order.status === "delivered") return { label: t("Plan it again"), prompt: t("Plan another trip like trip {id}.", { id }) };
        return { label: t("Ask"), prompt: t("What happened with trip {id}?", { id }) };
      },
    }),
    [t],
  );
}

/** The trip's destination: the city of its first stay, experience, or flight. */
export function TripThumb({ order }: { order: Order }) {
  const catalog = useCatalogIndex(fetchProducts);
  const product = order.items.map((item) => catalog[item.product_id]).find(Boolean);
  const city = product ? productCity(product) : undefined;
  return <PostcardWindow city={city} title={order.items[0]?.title ?? order.order_id} className="h-[42px] w-[60px] shrink-0" />;
}
