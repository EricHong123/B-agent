// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { AskLink, BagPanel, CheckoutButton, optionValuesLabel, RemoveLink, Stepper, TotalRow, useCatalogIndex, useStoreFrame, useT } from "web-shared";
import { fetchProducts } from "@/lib/api";
import { billAfterOrder, formatPrice, priceUnitOf, splitCart } from "@/lib/format";
import type { AccountContext, CartItem, CartPayload, Product } from "@/lib/types";
import PlanTile from "./PlanTile";

function asProduct(item: CartItem): Product {
  return { product_id: item.product_id, title: item.title, price: item.price, option_values: item.option_values };
}

/** "the ACME Phone 5 Pro (512 GB · graphite)": what a message to the assistant calls a line. */
function lineName(item: CartItem): string {
  const chosen = optionValuesLabel(item);
  return chosen ? `${item.title} (${chosen})` : item.title;
}

/** Plans and fiber lines are one service each; only devices and add-ons get a stepper. */
function isStockable(productId: string): boolean {
  return /-(DEV|ADD)-/.test(productId);
}

/** The order beside the conversation: monthly and due-today totals, and what the bill becomes. */
export default function OrderPanel({ cart, account }: { cart: CartPayload | null; account: AccountContext | null }) {
  const t = useT();
  const { ask } = useStoreFrame();
  const items = cart?.items ?? [];
  const count = cart?.item_count ?? 0;
  const catalog = useCatalogIndex(fetchProducts);
  const { monthly, today } = splitCart(items, catalog);
  const bill = items.length > 0 ? billAfterOrder(account, items, catalog) : null;
  const billDelta = bill ? Math.round((bill.after - bill.before) * 100) / 100 : 0;

  return (
    <BagPanel
      title={t("Order")}
      count={count === 1 ? t("{n} item", { n: count }) : t("{n} items", { n: count })}
      isEmpty={items.length === 0}
      empty={
        <>
          {t("Nothing in the order yet.")}
          <br />
          {t("Ask ACME Assistant about plans, phones, or home fiber.")}
        </>
      }
      footer={
        <>
          <TotalRow label={t("Monthly")} value={t("{price}/mo", { price: formatPrice(monthly) })} />
          <div className="mt-1">
            <TotalRow label={t("Due today")} value={formatPrice(today)} note={items.length ? t("Nothing is charged until you check out.") : undefined} />
          </div>
          {bill ? (
            <p className="am-mono mt-2 border-t border-(--line) pt-2 text-[12px] font-semibold text-(--ink)">
              {t("Your bill {before}/mo → {after}/mo", { before: formatPrice(bill.before), after: formatPrice(bill.after) })}{" "}
              <span className={billDelta < 0 ? "text-(--accent)" : "text-(--ink-soft)"}>
                ({billDelta === 0 ? t("no change") : t("{sign}{amount}/mo", { sign: billDelta > 0 ? "+" : "−", amount: formatPrice(Math.abs(billDelta)) })})
              </span>
            </p>
          ) : null}
          <CheckoutButton staged={false} disabled={items.length === 0} prompt={t("Check out my order.")} />
          {items.length ? (
            <div className="mt-2.5 flex justify-center">
              <AskLink label={t("Ask about this order")} prompt={t("Look over my order: is anything missing before I check out?")} />
            </div>
          ) : null}
        </>
      }
    >
      <ul>
        {items.map((item, index) => {
          const monthlyLine = priceUnitOf(item.product_id, catalog) === "per_month";
          const unitPrice = monthlyLine ? t("{price}/mo", { price: formatPrice(item.price) }) : formatPrice(item.price);
          return (
            <li key={item.product_id} className={`py-3 ${index > 0 ? "border-t border-(--line)" : "pt-0"}`}>
              <PlanTile
                product={asProduct(item)}
                note={`${optionValuesLabel(item) ? `${optionValuesLabel(item)} · ` : ""}${unitPrice} × ${item.quantity}`}
                trailing={
                  <span className="am-mono shrink-0 text-[14px] font-semibold text-(--ink)">
                    {formatPrice(item.line_total)}
                    {monthlyLine ? <span className="text-[11px] text-(--ink-soft)">{t("/mo")}</span> : null}
                  </span>
                }
              />
              <div className="mt-1.5 flex items-center gap-2 pl-[68px]">
                {isStockable(item.product_id) ? (
                  <Stepper
                    quantity={item.quantity}
                    itemTitle={lineName(item)}
                    onChange={(quantity) => ask(quantity < 1 ? t("Remove the {name} from my order.", { name: lineName(item) }) : t("Change the {name} quantity to {quantity}.", { name: lineName(item), quantity }))}
                  />
                ) : null}
                <RemoveLink itemTitle={lineName(item)} onClick={() => ask(t("Remove the {name} from my order.", { name: lineName(item) }))} />
              </div>
            </li>
          );
        })}
      </ul>
    </BagPanel>
  );
}
