// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { Fragment, type ReactNode } from "react";

/** Fills `{name}` placeholders of an already translated string with elements, so markup can sit mid-sentence in either language. */
export function rich(text: string, nodes: Record<string, ReactNode>): ReactNode {
  return text.split(/\{(\w+)\}/).map((part, index) =>
    index % 2 === 1 ? <Fragment key={index}>{nodes[part] ?? `{${part}}`}</Fragment> : part,
  );
}
