// Copyright 2026 Anthropic PBC
// SPDX-License-Identifier: Apache-2.0

/** Event shapes mirror commerce_common/streaming.py. */

export type AgentEventType =
  | "text_delta"
  | "tool_call"
  | "tool_result"
  | "ui"
  | "ui_partial"
  | "cart_update"
  | "change_update"
  | "progress"
  | "turn_complete"
  | "error";

export interface AgentEvent {
  type: AgentEventType;
  data: Record<string, unknown>;
}

/** `tool_call` data. `label` is the model's few words for the person waiting; presentation calls carry none. */
export interface ToolCallData {
  tool: string;
  id: string;
  input: Record<string, unknown>;
  label?: string;
}

/** Mirrors shopping_agent/types.py `Order`. */
export interface Order {
  order_id: string;
  status: string;
  placed_at: string;
  items: { product_id: string; title: string; quantity: number; price: number; option_values?: Record<string, string>; variant_of?: string | null }[];
  total: number;
  currency?: string;
  estimated_delivery?: string | null;
  tracking_url?: string | null;
}

export interface MemoryFact {
  key: string;
  value: string;
  category: string;
  updated_at?: string | null;
}

/** Each app narrows `payload` in its registry. */
export interface UIBlock {
  component: string;
  payload: unknown;
}

export interface TraceEntry {
  kind: "tool_call" | "tool_result" | "turn_complete" | "error";
  turn: number;
  label: string;
  detail?: string;
  isError?: boolean;
  /** "blocked" when a gate held the call; `reason` names the gate. */
  status?: string;
  reason?: string;
  /** tool_result only: the head of a long result, sent when `detail` is the "ok" summary. */
  excerpt?: string;
  /** performance.now() at arrival. */
  at: number;
  /** turn_complete only. */
  elapsedMs?: number;
}

/** `retrying`: the attempt failed validation; its last frame stays until a retry adopts it. */
export type UISlotStatus = "pending" | "partial" | "retrying" | "final";

export type AssistantSegment =
  | { type: "text"; text: string }
  | { type: "error"; text: string }
  | {
      type: "ui";
      block: UIBlock;
      slotKey: string;
      status: UISlotStatus;
    };

export type UISegment = Extract<AssistantSegment, { type: "ui" }>;

export interface UserChatItem {
  kind: "user";
  text: string;
}

export interface AssistantChatItem {
  kind: "assistant";
  turn: number;
  segments: AssistantSegment[];
  suggestions: string[];
  /** Merchant portals: changes previewed in this reply. */
  changeIds?: string[];
  suggestionsStale?: boolean;
  pending: boolean;
  tools: string[];
  /**
   * Status line for the call in flight; cleared when prose or a card lands, or when the
   * tool a progress line names returns.
   */
  activity?: string;
  /** The server's id for this reply (`turn_complete`), which votes and handoffs name. */
  turnId?: string;
  /** The user's vote on this reply. */
  rating?: "up" | "down";
  /** The support ticket a handoff from this reply opened. */
  ticket?: string;
  /** What that ticket carries for the person who takes it (`POST /handoff`). */
  handoff?: HandoffBrief;
  /** The terms versions this reply's reads returned as current (`evidence` on `tool_result`). */
  sources?: ReplySource[];
}

/** One current terms version a reply rested on. */
export interface ReplySource {
  source_id: string;
  version: string;
  effective_at: string;
}

/** Why the user asked for a person: the reason the operations log counts it under. */
export type HandoffReason = "user_requested" | "after_negative_feedback" | "after_error";

/** A ticket's brief, built by the API from the session's turns (`OperationsLog.brief`). */
export interface HandoffBrief {
  /** The customer's last request, identifier shapes masked and cut short. */
  request: string | null;
  tried: {
    /** Each tool the session called, with how its last call ended (`ok`, `error`, `blocked`). */
    tools: { name: string; status: string }[];
    /** Each call a gate held, with the gate. */
    held: { tool: string; reason: string }[];
    /** Why turns fell back (`terms_withheld`, `no_terms_match`, `gate_held:<gate>`). */
    fallbacks: string[];
  };
  /** Each terms version the session's reads returned or withheld. */
  evidence_versions: { source_id: string; version: string; status: string }[];
  /** The reason the operations log counts the handoff under. */
  reason: HandoffReason | "rule_triggered";
}

export type ChatItem = UserChatItem | AssistantChatItem;
