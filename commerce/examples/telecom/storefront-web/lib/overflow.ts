// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useCallback, useEffect, useState, type RefObject } from "react";

export function useOverflow(
  ref: RefObject<HTMLElement | null>,
  /** Any value whose change may alter scrollWidth. */
  resyncKey: unknown,
): { overflow: { left: boolean; right: boolean }; sync: () => void } {
  const [overflow, setOverflow] = useState({ left: false, right: false });
  const sync = useCallback(() => {
    const node = ref.current;
    if (!node) return;
    setOverflow({
      left: node.scrollLeft > 4,
      right: node.scrollLeft + node.clientWidth < node.scrollWidth - 4,
    });
  }, [ref]);
  useEffect(() => {
    sync();
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(sync);
    observer.observe(node);
    return () => observer.disconnect();
  }, [sync, ref, resyncKey]);
  return { overflow, sync };
}
