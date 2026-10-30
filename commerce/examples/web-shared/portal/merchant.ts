// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

"use client";

import { useCallback, useRef } from "react";
import type { AgentApi } from "../api";
import type { AgentEvent, ChatItem } from "../protocol";
import { type AgentTurn, useAgentTurn } from "../turn";

export interface ChangeRef {
  change_id: string;
  status: string;
}

export type ChangeAction = "apply" | "discard";

/**
 * The API's answer to Approve or Dismiss: the change as it now stands when it moved or
 * expired, and the backend's reason, untranslated, when the action did not go through.
 */
export interface ChangeActionResult<TChange> {
  change: TChange | null;
  reason: string | null;
}

/** Null when the call itself failed; a retry may succeed. */
export type ChangeActionHandler<TChange> = (
  changeId: string,
  action: ChangeAction,
) => Promise<ChangeActionResult<TChange> | null>;

export interface MerchantChat<TChange extends ChangeRef> extends AgentTurn {
  /** Goes through the same gate as the agent's own apply/discard. */
  actOnChange: ChangeActionHandler<TChange>;
}

/** Chips written for the staged state go stale once the change moves on. */
function applyChangeUpdate(items: ChatItem[], change: ChangeRef): ChatItem[] {
  return items.map((item) => {
    if (item.kind !== "assistant" || !item.changeIds?.includes(change.change_id)) return item;
    return {
      ...item,
      suggestionsStale: item.suggestionsStale || change.status !== "staged",
      segments: item.segments.map((segment) =>
        segment.type === "ui" &&
        segment.block.component === "change_preview" &&
        (segment.block.payload as { change_id?: string }).change_id === change.change_id
          ? {
              ...segment,
              block: { ...segment.block, payload: { ...(segment.block.payload as object), change } },
            }
          : segment,
      ),
    };
  });
}

/** A change moving mid-turn refreshes the portal's widgets once the turn settles. */
export function useMerchantChat<TChange extends ChangeRef>(
  api: AgentApi,
  options: {
    sessionId: string | null;
    unreachable: string;
    onPortalRefresh: () => void;
  },
): MerchantChat<TChange> {
  const { onPortalRefresh } = options;
  const dirtyRef = useRef(false);
  const setItemsRef = useRef<AgentTurn["setItems"] | null>(null);

  const onEvent = useCallback((event: AgentEvent, turn: number) => {
    if ((event.type === "ui" || event.type === "ui_partial") && event.data.component === "change_preview") {
      const changeId = (event.data.payload as { change_id?: string } | undefined)?.change_id;
      if (!changeId) return;
      setItemsRef.current?.((items) =>
        items.map((item) =>
          item.kind === "assistant" && item.turn === turn && !item.changeIds?.includes(changeId)
            ? { ...item, changeIds: [...(item.changeIds ?? []), changeId] }
            : item,
        ),
      );
    } else if (event.type === "change_update") {
      dirtyRef.current = true;
      const change = event.data.change as ChangeRef | undefined;
      if (change?.change_id) setItemsRef.current?.((items) => applyChangeUpdate(items, change));
    }
  }, []);

  const onTurnEnd = useCallback(() => {
    if (!dirtyRef.current) return;
    dirtyRef.current = false;
    onPortalRefresh();
  }, [onPortalRefresh]);

  const turn = useAgentTurn(api, { ...options, onEvent, onTurnEnd });
  setItemsRef.current = turn.setItems;

  const actOnChange = useCallback(
    async (changeId: string, action: ChangeAction): Promise<ChangeActionResult<TChange> | null> => {
      const data = await api.post<{ change: TChange | null; reason?: string | null }>(
        `/changes/${encodeURIComponent(changeId)}/${action}`,
      );
      if (!data) return null;
      const change = data.change ?? null;
      if (change) {
        onPortalRefresh();
        turn.setItems((items) => applyChangeUpdate(items, change));
      }
      return { change, reason: data.reason ?? null };
    },
    [api, onPortalRefresh, turn.setItems],
  );

  return { ...turn, actOnChange };
}
