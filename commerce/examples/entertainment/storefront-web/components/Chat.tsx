// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import type { ReactNode } from "react";
import { ActivityLine, type AgentTurn, type AssistantChatItem, Chat as ChatShell, useT } from "web-shared";
import GenerativeBlock from "./generative";
import { TextBones } from "./generative/Bones";

const WIDE = new Set(["venue_map", "comparison"]);

function Caption({ text }: { text: string }) {
  return <p className="at-stub-caption mb-2 animate-pulse">◉ {text}</p>;
}

function Pending({ item }: { item: AssistantChatItem }) {
  const t = useT();
  if (item.segments.some((segment) => segment.type === "ui" && segment.status === "pending")) {
    return null;
  }
  if (item.segments.length) return <ActivityLine item={item} />;
  return (
    <div role="status" aria-label={t("Working")} className="flex flex-col gap-2">
      {item.activity ? <Caption text={item.activity} /> : null}
      <TextBones />
    </div>
  );
}

export default function Chat({ chat, home }: { chat: AgentTurn; home: ReactNode }) {
  return (
    <ChatShell
      chat={chat}
      home={home}
      wide={WIDE}
      renderPending={(item) => <Pending item={item} />}
      renderBlock={(segment, item) => (
        <>
          {segment.status === "pending" && item.activity ? <Caption text={item.activity} /> : null}
          <GenerativeBlock block={segment.block} status={segment.status} />
        </>
      )}
    />
  );
}
