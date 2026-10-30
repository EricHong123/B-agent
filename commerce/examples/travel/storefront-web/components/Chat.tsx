// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import type { ReactNode } from "react";
import { type AgentTurn, Chat as ChatShell } from "web-shared";
import GenerativeBlock from "./generative";

const WIDE = new Set(["comparison", "itinerary"]);

export default function Chat({ chat, home }: { chat: AgentTurn; home: ReactNode }) {
  return <ChatShell chat={chat} home={home} wide={WIDE} renderBlock={(segment) => <GenerativeBlock block={segment.block} status={segment.status} />} />;
}
