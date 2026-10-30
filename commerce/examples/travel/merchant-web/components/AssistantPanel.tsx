// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { AssistantPanel as PanelShell, type MerchantChat, type Prefill, useT } from "web-shared";
import type { StagedChange } from "@/lib/types";
import GenerativeBlock from "./generative";

const COPY = {
  title: "Supplier assistant",
  intro: "Ask about bookings, occupancy, rates, or campaigns.",
  starters: [
    "What needs my attention this morning?",
    "How are the Lisbon stays pacing for October?",
    "Which properties are running behind on bookings?",
    "Where should nightly rates move over the next month?",
  ],
  label: "Message the supplier assistant",
  placeholder: "Ask about bookings, rates, campaigns…",
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
    ...COPY,
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
