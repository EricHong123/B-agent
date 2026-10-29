// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useEffect, useState } from "react";
import {
  ArrivingPanel,
  estimateOf,
  Greeting,
  greeting,
  HomeSection,
  type Order,
  type Starter,
  Starters,
  upcoming,
  useCatalogIndex,
  useLocale,
  useStoreFrame,
  useT,
} from "web-shared";
import { fetchProducts } from "@/lib/api";
import { NOUNS, OrderThumb } from "@/lib/orders";
import type { Product } from "@/lib/types";
import ProductTile from "../ProductTile";

const STARTERS: Starter[] = [
  { icon: "search", prompt: "A tent for a first family camping trip, under $250" },
  { icon: "home", prompt: "Set up a home office in a small spare room for about $800" },
  { icon: "tag", prompt: "Drip or espresso for busy weekday mornings?" },
  { icon: "edit", prompt: "Remember: small apartment, no outdoor storage, and a golden retriever" },
];

/** What the store is featuring: labelled bestseller or new, photographed ones first. */
function featured(catalog: Record<string, Product>): Product[] {
  return Object.values(catalog)
    .filter((product) => product.labels?.some((label) => label === "bestseller" || label === "new") && product.in_stock !== false)
    .sort((a, b) => Number(Boolean(b.image_url)) - Number(Boolean(a.image_url)))
    .slice(0, 4);
}

function Brief({ orders }: { orders: Order[] | null }) {
  const t = useT();
  if (!orders) return <>{t("Ask about a product, a project, an order, or a return.")}</>;
  const open = upcoming(orders);
  if (!open.length) return <>{t("Nothing on the way right now. Ask about a product, a project, or a return.")}</>;
  const late = open.filter((order) => order.status === "delayed");
  const next = estimateOf(open.find((order) => order.status !== "delayed") ?? open[0])?.date;
  const head = t(open.length === 1 ? "{count} order on the way" : "{count} orders on the way", { count: open.length });
  return (
    <>
      {next ? t("{head}; the next arrives {date}.", { head, date: next }) : t("{head}.", { head })}{" "}
      {late.length ? <span className="font-semibold text-(--warn)">{late.length === 1 ? t("One is running late.") : t("{count} are running late.", { count: late.length })}</span> : null}
    </>
  );
}

/** The clock is read after mount, so the prerendered page never disagrees with the browser's day. */
function useNow(): Date | null {
  const [now, setNow] = useState<Date | null>(null);
  useEffect(() => setNow(new Date()), []);
  return now;
}

export default function HomeView({
  shopperName,
  orders,
  ordersFailed,
  onSeeOrders,
}: {
  shopperName: string;
  orders: Order[] | null;
  ordersFailed: boolean;
  onSeeOrders: () => void;
}) {
  const t = useT();
  const { locale } = useLocale();
  const { ask } = useStoreFrame();
  const catalog = useCatalogIndex(fetchProducts);
  const picks = featured(catalog);
  const now = useNow();
  return (
    <div className="flex flex-col gap-4">
      <Greeting
        eyebrow={now ? now.toLocaleDateString(locale === "zh" ? "zh-CN" : "en-US", { weekday: "long", month: "long", day: "numeric" }) : "\u00a0"}
        title={<h1 className="text-[28px] font-semibold leading-tight tracking-[-0.02em] text-(--ink)">{t("{greeting}, {name}", { greeting: t(now ? greeting(now) : "Hello"), name: shopperName })}</h1>}
      >
        <Brief orders={orders} />
      </Greeting>
      <Starters items={STARTERS.map((starter) => ({ ...starter, prompt: t(starter.prompt) }))} />
      <ArrivingPanel orders={orders} failed={ordersFailed} nouns={NOUNS} thumb={(order) => <OrderThumb order={order} />} onSeeAll={onSeeOrders} />
      {picks.length ? (
        <HomeSection title={t("Popular right now")} subtitle={t("Bestsellers and new arrivals; open one to ask about it")}>
          <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {picks.map((product) => (
              <ProductTile key={product.product_id} product={product} fluid onOpen={(item) => ask(t("Tell me about the {title}.", { title: item.title }))} />
            ))}
          </div>
        </HomeSection>
      ) : null}
    </div>
  );
}
