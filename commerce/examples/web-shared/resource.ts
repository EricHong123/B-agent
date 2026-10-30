// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { type DependencyList, useEffect, useState } from "react";

/**
 * Loads one read and reloads when `deps` change. `data` keeps its last good value;
 * `failed` is true while the latest attempt returned nothing. A null `load` waits (nothing to
 * load yet, e.g. before the session exists).
 */
export function useResource<T>(load: (() => Promise<T | null>) | null, deps: DependencyList): { data: T | null; failed: boolean } {
  const [data, setData] = useState<T | null>(null);
  const [failed, setFailed] = useState(false);
  useEffect(() => {
    if (!load) return;
    let cancelled = false;
    void load().then((response) => {
      if (cancelled) return;
      if (response) setData(response);
      setFailed(!response);
    });
    return () => {
      cancelled = true;
    };
    // The caller's deps say when to reload; `load` is usually an inline closure.
  }, deps);
  return { data, failed };
}
