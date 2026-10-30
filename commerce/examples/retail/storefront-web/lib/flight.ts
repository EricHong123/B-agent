// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** Presentation only; runs after the cart write has completed. */

import { productGlyph, productTileClass } from "./format";
import type { Product } from "./types";

const CART_TARGET_ATTRIBUTE = "data-cart-target";

export function flyToCart(product: Product, source: HTMLElement): void {
  if (typeof document === "undefined") return;
  if (window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  // The count that is on screen: the docked panel's, or the app bar's while the panel is a closed drawer.
  const target = [...document.querySelectorAll<HTMLElement>(`[${CART_TARGET_ATTRIBUTE}]`)].find((node) => {
    const rect = node.getBoundingClientRect();
    return rect.width > 0 && rect.left >= 0 && rect.right <= window.innerWidth;
  });
  if (!target) return;
  const from = source.getBoundingClientRect();
  const to = target.getBoundingClientRect();

  const ghost = document.createElement("div");
  ghost.textContent = productGlyph(product);
  ghost.setAttribute("aria-hidden", "true");
  ghost.className = `pointer-events-none fixed z-50 flex h-10 w-10 items-center justify-center rounded-lg text-xl shadow-md ${productTileClass(product.product_id)}`;
  ghost.style.left = `${from.left + from.width / 2 - 20}px`;
  ghost.style.top = `${from.top + from.height / 2 - 20}px`;
  (source.closest<HTMLElement>("[data-portal-host]") ?? document.body).appendChild(ghost);
  if (typeof ghost.animate !== "function") {
    ghost.remove();
    return;
  }

  const dx = to.left + to.width / 2 - (from.left + from.width / 2);
  const dy = to.top + to.height / 2 - (from.top + from.height / 2);
  // The midpoint keyframe rises above the straight line to make an arc.
  const lift = Math.min(90, Math.abs(dx) * 0.25 + 40);
  const animation = ghost.animate(
    [
      { transform: "translate(0, 0) scale(1)", opacity: 1 },
      {
        transform: `translate(${dx * 0.55}px, ${dy * 0.4 - lift}px) scale(0.85)`,
        opacity: 0.95,
        offset: 0.55,
      },
      { transform: `translate(${dx}px, ${dy}px) scale(0.4)`, opacity: 0.2 },
    ],
    { duration: 420, easing: "cubic-bezier(0.3, 0.7, 0.4, 1)" },
  );
  animation.onfinish = () => ghost.remove();
  animation.oncancel = () => ghost.remove();
}
