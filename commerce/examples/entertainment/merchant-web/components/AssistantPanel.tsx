// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { AssistantPanel as PanelShell, type MerchantChat, type Prefill, useT } from "web-shared";
import type { StagedChange } from "@/lib/types";
import GenerativeBlock from "./generative";

const COPY = {
  title: "Box-office assistant",
  intro: "Ask about pacing, holds, pricing, or campaigns.",
  starters: [
    "What needs my attention this morning?",
    "How is the Headliner Friday show pacing against comparable events?",
    "Which tiers are running behind their baseline?",
    "Where do we still have holds we could release?",
  ],
  label: "Message the box-office assistant",
  placeholder: "Ask about pacing, holds, pricing…",
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
  const copy = {
    title: t(COPY.title),
    intro: t(COPY.intro),
    starters: COPY.starters.map((starter) => t(starter)),
    label: t(COPY.label),
    placeholder: t(COPY.placeholder),
  };
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
