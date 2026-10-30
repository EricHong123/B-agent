// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { createContext, useContext } from "react";
import type { AgentTurn } from "../turn";

/**
 * What everything inside `StoreShell` reads instead of taking props: the conversation, the
 * assistant's name, `ask` (send a message and bring the conversation into view), and
 * `closePanel` (the bag drawer below `xl`). The default lets a bag panel or home block render
 * outside the frame, as `/showcase` does.
 */
export interface StoreFrame {
  chat: AgentTurn | null;
  assistantName: string;
  ask: (message: string) => void;
  closePanel: () => void;
}

export const FrameContext = createContext<StoreFrame>({
  chat: null,
  assistantName: "ACME Assistant",
  ask: () => {},
  closePanel: () => {},
});

export function useStoreFrame(): StoreFrame {
  return useContext(FrameContext);
}
