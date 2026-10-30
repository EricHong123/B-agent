// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useMemo } from "react";
import { AssistantPanel as PanelShell, type MerchantChat, type Prefill, useT } from "web-shared";
import type { StagedChange } from "@/lib/types";
import GenerativeBlock from "./generative";

const COPY = {
  title: "Operations assistant",
  intro: "Ask about the subscriber base, churn, plan pricing, or campaigns.",
  starters: [
    "What needs my attention this morning?",
    "Where is churn rising across the base?",
    "Which plans are carrying the thinnest margin per line?",
    "How did last week's gross adds compare to the week before?",
  ],
  label: "Message the operations assistant",
  placeholder: "Ask about churn, plans, campaigns…",
};

export default function AssistantPanel({
  chat,
  prefill,
  onPrefill,
  ...shell
}: {
  chat: MerchantChat<StagedChange>;
  prefill: Prefill | null;
  onPrefill: (text: string) => void;
  newMemoryCount: number;
  onOpenActivity: () => void;
  onClose: () => void;
  fullscreen: boolean;
  onToggleFullscreen: () => void;
}) {
  const t = useT();
  const copy = useMemo(
    () => ({
      title: t(COPY.title),
      intro: t(COPY.intro),
      starters: COPY.starters.map((starter) => t(starter)),
      label: t(COPY.label),
      placeholder: t(COPY.placeholder),
    }),
    [t],
  );
  return (
    <PanelShell
      chat={chat}
      copy={copy}
      prefill={prefill}
      renderBlock={(segment) => (
        <GenerativeBlock
          block={segment.block}
          status={segment.status}
          onChangeAction={chat.actOnChange}
          onPrefill={onPrefill}
        />
      )}
      {...shell}
    />
  );
}
