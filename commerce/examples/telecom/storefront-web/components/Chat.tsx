// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import type { ReactNode } from "react";
import { type AgentTurn, Chat as ChatShell } from "web-shared";
import { addToCart } from "@/lib/api";
import type { AccountContext, CartPayload } from "@/lib/types";
import GenerativeBlock from "./generative";

const WIDE = new Set(["plan_matrix", "comparison"]);

export default function Chat({ chat, home, account, onCartUpdate }: { chat: AgentTurn; home: ReactNode; account: AccountContext | null; onCartUpdate: (cart: CartPayload) => void }) {
  return (
    <ChatShell
      chat={chat}
      home={home}
      wide={WIDE}
      renderBlock={(segment) => (
        <GenerativeBlock
          block={segment.block}
          status={segment.status}
          account={account}
          onAdd={async (product) => {
            const cart = await addToCart(product.product_id);
            if (cart) onCartUpdate(cart);
            return cart !== null;
          }}
        />
      )}
    />
  );
}
