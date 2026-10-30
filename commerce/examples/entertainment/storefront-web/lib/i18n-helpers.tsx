// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { Fragment, type ReactNode } from "react";
import { type Translate, useT } from "web-shared";

/** "1 ticket" or "3 tickets": the count picks between two English keys, each with an `{n}` placeholder. */
export function tPlural(t: Translate, count: number, one: string, many: string): string {
  return t(count === 1 ? one : many, { n: count });
}

/**
 * A translated sentence with elements in its placeholders. The table entry carries the word
 * order, so `{name}` positions can differ between English and Chinese.
 */
export function Rich({ text, vars }: { text: string; vars: Record<string, ReactNode> }) {
  const t = useT();
  return (
    <>
      {t(text)
        .split(/(\{\w+\})/)
        .map((part, index) => {
          const name = /^\{(\w+)\}$/.exec(part)?.[1];
          return name !== undefined && name in vars ? (
            <Fragment key={index}>{vars[name]}</Fragment>
          ) : (
            part
          );
        })}
    </>
  );
}
