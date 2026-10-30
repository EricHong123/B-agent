// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

import { Markdown } from "./Markdown";

export function UserBubble({ text }: { text: string }) {
  return (
    <div className="flex justify-end">
      <div className="user-bubble max-w-[72%] px-3.5 py-2 text-[14.5px] leading-normal">{text}</div>
    </div>
  );
}

export function AssistantText({ text, streaming }: { text: string; streaming?: boolean }) {
  if (!text && !streaming) return null;
  return (
    <div className={`leading-relaxed text-(--ink) ${streaming ? "streaming-caret" : ""}`}>
      <Markdown text={text} />
    </div>
  );
}

export function ErrorBubble({ text }: { text: string }) {
  return (
    <div
      role="alert"
      className="rounded-lg border border-(--danger)/40 bg-(--danger-soft) px-3 py-2 text-[13px] leading-relaxed text-(--danger)"
    >
      {text}
    </div>
  );
}
